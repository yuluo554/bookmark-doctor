"""UIR（统一中间表示）构建与序列化（M2）。

规格出处：plan/03 §2、plan/04 §1.3、HANDOFF-M2 待办 #1；
字段冻结为 K 清单 K11（HANDOFF-M3 落盘时同步登记 plan/00）。

``tree.json`` 形态（schema ``bookmark-doctor.tree-v1``）::

    {
      "schema": "bookmark-doctor.tree-v1",
      "sources": [...],                     // 来源声明顺序
      "chrome_epoch_delta_us": 11644473600000000,  // K12 正本回显
      "bookmarks": [
        {
          "id": "sha1(source|seq) 前 12 位",   // K17：seq = 来源内 1 起序
          "title": "标题原文 | null",          // 缺失 null，不猜补
          "url": "URL 原文（永不改写）",
          "add_date": epoch 秒 int | null,     // 缺失/非法 null，不猜补
          "folder": ["文件夹路径", ...],
          "source": "来源标识"
        }
      ]
    }

序列化纪律（K18）：``sort_keys=True`` + ``ensure_ascii=False`` + 缩进 2 +
LF 行尾 + 结尾换行；无时间戳、无时钟、无随机——同输入逐字节一致。
"""

import hashlib
import json
from pathlib import Path

from bookmark_doctor.parse.chrome_json import parse_chrome_json
from bookmark_doctor.parse.errors import ParseError
from bookmark_doctor.parse.netscape import parse_netscape

SCHEMA_TREE = "bookmark-doctor.tree-v1"

# 冻结产物正本位置（K12）：Chrome 纪元换算常量的唯一数据源
_MANIFEST_REL = Path("data") / "fixtures" / "set-1" / "manifest.json"


def load_chrome_epoch_delta(repo_root):
    """从 fixtures manifest 正本读取 chrome_epoch_delta_us（K12 单点）。"""
    manifest_path = Path(repo_root) / _MANIFEST_REL
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ParseError("Chrome 纪元常量正本不可读 %s: %s" % (manifest_path, exc))
    value = manifest.get("chrome_epoch_delta_us")
    if not isinstance(value, int) or value <= 0:
        raise ParseError("正本 chrome_epoch_delta_us 缺失或非法: %s" % manifest_path)
    return value


def _entry_id(source, seq):
    """K17：id = sha1("source|seq") 前 12 位（确定性，无时钟）。"""
    return hashlib.sha1(("%s|%d" % (source, seq)).encode("utf-8")).hexdigest()[:12]


def build_bookmarks(parsed_entries, source):
    """单来源已解析条目 → UIR 条目列表（含确定性 id 与 source 标注）。"""
    bookmarks = []
    for seq, item in enumerate(parsed_entries, 1):
        bookmarks.append(
            {
                "id": _entry_id(source, seq),
                "title": item["title"],
                "url": item["url"],
                "add_date": item["add_date"],
                "folder": list(item["folder"]),
                "source": source,
            }
        )
    return bookmarks


def parse_input_file(path, source_name, epoch_delta_us):
    """按扩展名分派解析一份输入文件（读盘 + 解析）。

    - ``.json`` → Chrome/Edge Bookmarks JSON；``.html``/``.htm`` →
      Netscape HTML；其他扩展名 → ParseError（用法面错误提前暴露）；
    - 读盘/解码失败同样归一为 ParseError（文件级失败语义一致）。
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in (".json", ".html", ".htm"):
        raise ParseError("不支持的输入类型 %r（仅 .html/.htm/.json）: %s" % (suffix, path))
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ParseError("输入文件不可读 %s: %s" % (path, exc))
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ParseError("输入文件不是 UTF-8 文本: %s" % path)
    if suffix == ".json":
        try:
            obj = json.loads(text)
        except ValueError as exc:
            raise ParseError("JSON 解析失败 %s: %s" % (path, exc))
        return parse_chrome_json(obj, epoch_delta_us)
    return parse_netscape(text)


def build_tree(sources, repo_root):
    """多份输入 → 完整 UIR 字典（解析 + 逐源建条目 + 排序）。

    ``sources``：[{"path": Path, "source": 名称}, ...]（按命令行顺序）。
    任一文件失败 → ParseError（CLI 层 exit 2，不落半成品）。
    """
    epoch_delta_us = load_chrome_epoch_delta(repo_root)
    bookmarks = []
    source_names = []
    for spec in sources:
        parsed = parse_input_file(spec["path"], spec["source"], epoch_delta_us)
        bookmarks.extend(build_bookmarks(parsed, spec["source"]))
        source_names.append(spec["source"])
    # 条目顺序 = (来源声明顺序, 来源内文件序)——plan/04 §1.3 冻结口径；
    # 合并与导出都消费此序，不做二次全局排序（会打乱来源顺序语义）。
    return {
        "schema": SCHEMA_TREE,
        "sources": source_names,
        "chrome_epoch_delta_us": epoch_delta_us,
        "bookmarks": bookmarks,
    }


def serialize_tree(tree):
    """UIR → 确定性字节（K18：sort_keys + 无 CR + LF + 结尾换行）。"""
    return (
        json.dumps(tree, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        + b"\n"
    )


def merge_duplicates(bookmarks):
    """同 URL（原文精确匹配）跨来源合并 → (合并后列表, 重复组计数)。

    规则（plan/04 §1.3，M2 范围）：
    - 组内条目保留首条形态，``source`` 改记全部来源（保序去重）；
    - ``add_date`` 取**最早非空值**（None 不参与——未知不拖累已知）；
    - 首条 id 保留（可追溯其原始来源内序）；
    - 排序纪律保持 (source, url, id)。
    """
    groups = {}
    order = []
    for bm in bookmarks:
        key = bm["url"]
        if key not in groups:
            groups[key] = [bm]
            order.append(key)
        else:
            groups[key].append(bm)

    merged = []
    dup_groups = 0
    for key in order:
        members = groups[key]
        if len(members) == 1:
            merged.append(members[0])
            continue
        dup_groups += 1
        head = dict(members[0])
        seen = []
        for m in members:
            if m["source"] not in seen:
                seen.append(m["source"])
        head["source"] = seen
        dates = [m["add_date"] for m in members if m["add_date"] is not None]
        head["add_date"] = min(dates) if dates else None
        merged.append(head)
    return merged, dup_groups

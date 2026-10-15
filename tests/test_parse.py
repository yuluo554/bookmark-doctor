"""M2 解析层测试：解析器 / UIR / 合并 / CLI import / 往返一致。

口径（plan/04 §1、HANDOFF-M2 待办 #1–#6）：
- 双格式解析 → UIR → 最小导出 → 再解析：字段级相等（往返一致）；
- 合成集跨格式同构比对（folder 顶层为浏览器根差异，不比对——生成器
  把 4 个文件夹分放 Chrome 三棵根树，Netscape 全在根 DL，属数据面设计）；
- 坏文件（坏 HTML / 坏 JSON / 空文件 / 缺 roots / 非法 ADD_DATE）→
  ParseError；CLI 路径 exit 2 + 无半成品；
- 确定性：同输入两次 build_tree/serialize_tree 逐字节一致；
- 未知不猜补（K2）：缺 ADD_DATE / date_added="0" → null。
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from bookmark_doctor.export import export_netscape
from bookmark_doctor.model import (
    build_bookmarks,
    build_tree,
    load_chrome_epoch_delta,
    merge_duplicates,
    parse_input_file,
    serialize_tree,
)
from bookmark_doctor.parse.chrome_json import parse_chrome_json
from bookmark_doctor.parse.errors import ParseError
from bookmark_doctor.parse.netscape import parse_netscape

REPO_ROOT = Path(__file__).resolve().parent.parent
SET1 = REPO_ROOT / "data" / "fixtures" / "set-1"
HTML_PATH = SET1 / "bookmarks.netscape.html"
JSON_PATH = SET1 / "bookmarks.chrome.json"


# ---------------------------------------------------------------------------
# 解析器单元
# ---------------------------------------------------------------------------

def test_parse_netscape_fixture_27_entries():
    entries = parse_netscape(HTML_PATH.read_text(encoding="utf-8"))
    assert len(entries) == 27
    first = entries[0]
    assert first["url"] == "https://blocked-403.mock.invalid/article/1"
    assert first["title"] == "反爬样本-blocked-403"
    assert first["add_date"] == 1500086400
    assert first["folder"] == ["反爬场景"]


def test_parse_add_date_missing_and_invalid():
    text = (
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>\n<DL><p>\n"
        '<DT><A HREF="https://a.invalid/1">无时间</A>\n'
        '<DT><A HREF="https://a.invalid/2" ADD_DATE="">空串</A>\n'
        '<DT><A HREF="https://a.invalid/3" ADD_DATE="15x0">非法</A>\n'
        '<DT><A HREF="https://a.invalid/4" ADD_DATE="1500086400">正常</A>\n'
        "</DL><p>\n"
    )
    entries = parse_netscape(text)
    assert [e["add_date"] for e in entries] == [None, None, None, 1500086400]


def test_parse_netscape_entities_decoded():
    text = (
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>\n<DL><p>\n"
        '<DT><A HREF="https://a.invalid/x?u=1&amp;v=2" ADD_DATE="1">'
        "标题&lt;一&gt;号 &amp; more</A>\n</DL><p>\n"
    )
    (entry,) = parse_netscape(text)
    assert entry["url"] == "https://a.invalid/x?u=1&v=2"
    assert entry["title"] == "标题<一>号 & more"


def test_parse_netscape_bad_structure():
    with pytest.raises(ParseError):
        parse_netscape("")  # 空文件
    with pytest.raises(ParseError):
        parse_netscape('<DL><p><DT><A>无 HREF</A></DL><p>')
    with pytest.raises(ParseError):
        parse_netscape("<DL><p><DT><H3>悬空文件夹</H3>\n")  # H3 后无 DL
    with pytest.raises(ParseError):
        parse_netscape("</DL><p>")  # DL 下溢


def test_parse_chrome_json_fixture_27_entries():
    delta = load_chrome_epoch_delta(REPO_ROOT)
    obj = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    entries = parse_chrome_json(obj, delta)
    assert len(entries) == 27
    by_url = {e["url"]: e for e in entries}
    target = by_url["https://blocked-403.mock.invalid/article/1"]
    # 生成器换算口径：epoch 秒 * 1e6 + delta；1500086400 → 1500086400000000 + 11644473600000000
    assert target["add_date"] == 1500086400
    assert target["folder"][-1] == "反爬场景"
    # date_added="0"（生成器对缺时间条目的写法）→ null
    assert by_url["https://gone-404-b.mock.invalid/no-date"]["add_date"] is None


def test_parse_chrome_json_requires_roots():
    with pytest.raises(ParseError):
        parse_chrome_json({"no_roots": 1}, 11644473600000000)
    with pytest.raises(ParseError):
        parse_chrome_json([1, 2], 11644473600000000)
    with pytest.raises(ParseError):
        # url 节点缺 url 字段 → 不可用
        parse_chrome_json(
            {"roots": {"bookmark_bar": {"type": "folder", "children": [{"type": "url", "name": "x"}]}}},
            11644473600000000,
        )


# ---------------------------------------------------------------------------
# UIR 构建 / 合并 / 序列化
# ---------------------------------------------------------------------------

def _build_single(path, name):
    return build_tree([{"path": path, "source": name}], REPO_ROOT)


def test_build_tree_shape_and_ids():
    tree = _build_single(HTML_PATH, "bookmarks.netscape.html")
    assert tree["schema"] == "bookmark-doctor.tree-v1"
    assert tree["sources"] == ["bookmarks.netscape.html"]
    assert len(tree["bookmarks"]) == 27
    ids = [b["id"] for b in tree["bookmarks"]]
    assert len(set(ids)) == 27, "id 必须唯一（sha1(source|seq) 前 12 位）"
    bm = tree["bookmarks"][0]
    assert set(bm) == {"id", "title", "url", "add_date", "folder", "source"}


def test_build_tree_deterministic_bytes():
    t1 = serialize_tree(_build_single(JSON_PATH, "bookmarks.chrome.json"))
    t2 = serialize_tree(_build_single(JSON_PATH, "bookmarks.chrome.json"))
    assert t1 == t2
    assert b"\r" not in t1  # LF 纪律
    assert t1.endswith(b"\n")


def test_merge_duplicates_across_sources():
    tree = build_tree(
        [
            {"path": HTML_PATH, "source": "bookmarks.netscape.html"},
            {"path": JSON_PATH, "source": "bookmarks.chrome.json"},
        ],
        REPO_ROOT,
    )
    assert len(tree["bookmarks"]) == 54
    merged, dup_groups = merge_duplicates(tree["bookmarks"])
    assert dup_groups == 27  # 双格式同条目逐一对合并
    assert len(merged) == 27
    by_url = {b["url"]: b for b in merged}
    head = by_url["https://blocked-403.mock.invalid/article/1"]
    assert head["source"] == ["bookmarks.netscape.html", "bookmarks.chrome.json"]
    assert head["add_date"] == 1500086400


def test_merge_keeps_earliest_non_null_date():
    bms = [
        {"id": "a1", "title": "x", "url": "https://u.invalid/1", "add_date": 200, "folder": [], "source": "s1"},
        {"id": "b1", "title": "x", "url": "https://u.invalid/1", "add_date": None, "folder": [], "source": "s2"},
        {"id": "c1", "title": "x", "url": "https://u.invalid/1", "add_date": 100, "folder": [], "source": "s3"},
    ]
    merged, dup_groups = merge_duplicates(bms)
    assert dup_groups == 1 and len(merged) == 1
    assert merged[0]["add_date"] == 100  # 最早非空
    assert merged[0]["source"] == ["s1", "s2", "s3"]


# ---------------------------------------------------------------------------
# 往返一致（合成集回归，plan/04 §1.4）
# ---------------------------------------------------------------------------

def _roundtrip(path, name):
    """解析 → UIR → 最小导出 → 再解析，返回两条目列表。"""
    tree = _build_single(path, name)
    exported = export_netscape(tree["bookmarks"])
    reparsed = parse_netscape(exported.decode("utf-8"))
    key = lambda e: (tuple(e["folder"]), e["url"], e["title"], e["add_date"])
    return sorted(map(key, tree["bookmarks"])), sorted(map(key, reparsed))


def test_roundtrip_netscape():
    before, after = _roundtrip(HTML_PATH, "bookmarks.netscape.html")
    assert before == after


def test_roundtrip_chrome():
    before, after = _roundtrip(JSON_PATH, "bookmarks.chrome.json")
    assert before == after


def test_cross_format_same_entries():
    """双格式解析结果同构（folder 顶层为浏览器根差异，不比对）。"""
    html_entries = parse_netscape(HTML_PATH.read_text(encoding="utf-8"))
    delta = load_chrome_epoch_delta(REPO_ROOT)
    json_entries = parse_chrome_json(json.loads(JSON_PATH.read_text(encoding="utf-8")), delta)
    key = lambda e: (e["folder"][-1] if e["folder"] else "", e["url"], e["title"], e["add_date"])
    assert sorted(map(key, html_entries)) == sorted(map(key, json_entries))


def test_parse_input_file_dispatch():
    entries = parse_input_file(HTML_PATH, "x", load_chrome_epoch_delta(REPO_ROOT))
    assert len(entries) == 27
    with pytest.raises(ParseError):
        parse_input_file(REPO_ROOT / "README.md", "x", load_chrome_epoch_delta(REPO_ROOT))


# ---------------------------------------------------------------------------
# CLI import：退出码契约 + 无半成品
# ---------------------------------------------------------------------------

def _run_cli(*argv):
    env = {"PYTHONPATH": str(REPO_ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    import os

    env.update({k: v for k, v in os.environ.items() if k in ("SYSTEMROOT", "WINDIR", "PATH", "COMSPEC")})
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "bookmark_doctor"] + list(argv),
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_cli_import_stdout_and_summary():
    proc = _run_cli("import", str(HTML_PATH), "--out", "-")
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    summary = json.loads(proc.stdout.decode("utf-8").strip().splitlines()[0])
    assert summary["bookmarks_total"] == 27
    assert summary["add_date_null"] == 1
    assert summary["duplicate_groups_merged"] == 0


def test_cli_import_writes_tree(tmp_path):
    out = tmp_path / "tree.json"
    proc = _run_cli("import", str(JSON_PATH), "--out", str(out))
    assert proc.returncode == 0
    tree = json.loads(out.read_text(encoding="utf-8"))
    assert tree["schema"] == "bookmark-doctor.tree-v1"
    assert len(tree["bookmarks"]) == 27
    # 确定性：再跑一遍逐字节一致
    data1 = out.read_bytes()
    proc = _run_cli("import", str(JSON_PATH), "--out", str(out))
    assert proc.returncode == 0
    assert out.read_bytes() == data1


def test_cli_import_merge_two_files(tmp_path):
    out = tmp_path / "tree.json"
    proc = _run_cli("import", str(HTML_PATH), str(JSON_PATH), "--out", str(out))
    assert proc.returncode == 0
    summary = json.loads(proc.stdout.decode("utf-8").strip().splitlines()[0])
    assert summary["bookmarks_total"] == 27
    assert summary["duplicate_groups_merged"] == 27
    tree = json.loads(out.read_text(encoding="utf-8"))
    assert tree["sources"] == ["bookmarks.netscape.html", "bookmarks.chrome.json"]


@pytest.mark.parametrize(
    "content, filename",
    [
        (b"not json at all", "bad.json"),
        (b"", "empty.html"),
        (b"<DL><p><DT><A>no-href</A></DL><p>", "badstruct.html"),
        (b'{"roots": "not-a-dict"}', "badroots.json"),
    ],
)
def test_cli_import_bad_file_exit2_no_artifact(tmp_path, content, filename):
    bad = tmp_path / filename
    bad.write_bytes(content)
    out = tmp_path / "tree.json"
    proc = _run_cli("import", str(bad), "--out", str(out))
    assert proc.returncode == 2
    assert not out.exists(), "解析失败不得落半成品"
    stderr = proc.stderr.decode("utf-8", "replace")
    assert "解析失败" in stderr


def test_cli_import_missing_file_exit2(tmp_path):
    out = tmp_path / "tree.json"
    proc = _run_cli("import", str(tmp_path / "nope.html"), "--out", str(out))
    assert proc.returncode == 2
    assert not out.exists()


def test_cli_import_mixed_good_bad_no_artifact(tmp_path):
    """多文件输入中一份坏 → 整体 exit 2，好文件也不落盘。"""
    out = tmp_path / "tree.json"
    proc = _run_cli("import", str(HTML_PATH), str(tmp_path / "nope.json"), "--out", str(out))
    assert proc.returncode == 2
    assert not out.exists()


def test_build_bookmarks_add_date_null_passthrough():
    """未知不猜补（K2）：解析层 null → UIR null，不得出现 0/1970 兜底。"""
    parsed = [{"title": None, "url": "https://u.invalid/1", "add_date": None, "folder": ["f"]}]
    bms = build_bookmarks(parsed, "s")
    assert bms[0]["add_date"] is None
    assert bms[0]["title"] is None
    assert bms[0]["id"] == "ea2a2059343d"  # sha1("s|1")[:12]——确定性抽查

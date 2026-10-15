"""Chrome/Edge Bookmarks JSON 解析器（M2）。

规格（plan/04 §1.2、HANDOFF-M2 待办 #3、冻结口径 K12/K16）：
- ``roots`` 三树（bookmark_bar / other / synced）递归；``type`` 区分
  folder / url；
- ``date_added``：Chrome 纪元（1601 起微秒）字符串，显式换算为 epoch 秒；
  **换算常量不由本模块持有**——唯一正本在 fixtures manifest 的
  ``chrome_epoch_delta_us``（K12），由调用方传入 ``epoch_delta_us``；
  缺失 / "0" / 非法 → ``None``（未知不猜补，K2）；
- ``name`` 缺失 → ``None``；``url`` 缺失或非 str → :class:`ParseError`
  （书签无 URL 即不可用）；
- 纯函数：输入已反序列化的对象，输出条目列表，不触盘、无时钟。
"""

from bookmark_doctor.parse.errors import ParseError

_ROOT_KEYS = ["bookmark_bar", "other", "synced"]


def _parse_date_added(raw, epoch_delta_us):
    """Chrome date_added 字符串 → epoch 秒；"0"/缺失/非法/负 → None。"""
    if raw is None:
        return None
    if isinstance(raw, int):
        value = raw
    else:
        if not isinstance(raw, str):
            return None
        raw = raw.strip()
        if not raw:
            return None
        try:
            value = int(raw)
        except ValueError:
            return None
    if value <= 0:
        return None
    if value < epoch_delta_us:
        return None  # 早于 Unix 纪元的值换算必为负——记为未知，不猜补
    return (value - epoch_delta_us) // 1000000


def _walk(node, folder_path, epoch_delta_us, out, errors):
    if not isinstance(node, dict):
        return
    node_type = node.get("type")
    name = node.get("name")
    if not isinstance(name, str) or not name:
        name = None
    if node_type == "folder":
        children = node.get("children")
        if isinstance(children, list):
            child_path = folder_path + ([name] if name else [])
            for child in children:
                _walk(child, child_path, epoch_delta_us, out, errors)
    elif node_type == "url":
        url = node.get("url")
        if not isinstance(url, str) or not url:
            errors.append("url 节点缺少 url 字段（name=%r）" % (name,))
            return
        out.append(
            {
                "title": name,
                "url": url,
                "add_date": _parse_date_added(node.get("date_added"), epoch_delta_us),
                "folder": folder_path,
            }
        )
    # 其余 type（如 Chrome 偶见的空 type）：跳过，不猜


def parse_chrome_json(obj, epoch_delta_us):
    """解析 Chrome Bookmarks JSON 对象 → 条目列表。

    ``obj`` 为已 ``json.loads`` 的对象；``epoch_delta_us`` 为 Chrome 纪元
    差值常量（**必传**，正本见 K12——本模块不写第二份常量）。
    结构坏 → :class:`ParseError`。
    """
    if not isinstance(obj, dict):
        raise ParseError("顶层不是 JSON 对象（不是有效的 Chrome Bookmarks 文件）")
    roots = obj.get("roots")
    if not isinstance(roots, dict):
        raise ParseError("缺少 roots 节点（不是有效的 Chrome Bookmarks 文件）")
    out = []
    errors = []
    for key in _ROOT_KEYS:
        root = roots.get(key)
        if root is None:
            continue
        if not isinstance(root, dict):
            raise ParseError("roots.%s 不是对象" % key)
        _walk(root, [], epoch_delta_us, out, errors)
    if errors:
        raise ParseError("；".join(errors))
    return out

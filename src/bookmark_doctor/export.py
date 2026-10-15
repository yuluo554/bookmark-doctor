"""最小 Netscape HTML 导出（M2，仅为往返一致性测试服务）。

完整导回（含 --apply-dedupe / --exclude-dead / 浏览器实测验收）在 M5；
本模块 M2 只做一件事：UIR 条目 → 合规 Netscape HTML 字节，作为
"解析 → 导出 → 再解析" 往返一致性测试的 B 面（plan/04 §1.4）。

转义纪律（plan/04 §4.3 预热）：标题/URL 中 ``& < > "`` 转义；中文原样。
文件夹分组按 UIR folder 路径重建一级结构即可（往返测试只比较条目，
不比较树形——merge 已声明跨源不合并目录树）。
"""

from bookmark_doctor.parse.netscape import parse_netscape  # noqa: F401  (往返测试同用)


def _escape_html(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _nested_groups(bookmarks):
    """按完整 folder 路径嵌套分组（保序：首次出现顺序）。

    返回 (子文件夹列表, 直接书签列表)；子文件夹递归同构。
    """
    sub_index = {}
    subs = []  # [(name, nested), ...] 保序
    direct = []
    for bm in bookmarks:
        if bm["folder"]:
            name = bm["folder"][0]
            child = dict(bm)
            child["folder"] = bm["folder"][1:]
            if name not in sub_index:
                sub_index[name] = []
                subs.append((name, sub_index[name]))
            sub_index[name].append(child)
        else:
            direct.append(bm)
    return subs, direct


def _render_folder(items, indent, lines):
    subs, direct = _nested_groups(items)
    for bm in direct:
        lines.append(_render_bookmark(bm, indent))
    for name, children in subs:
        lines.append("%s<DT><H3>%s</H3>" % (indent, _escape_html(name)))
        lines.append("%s<DL><p>" % indent)
        _render_folder(children, indent + "    ", lines)
        lines.append("%s</DL><p>" % indent)


def _render_bookmark(bm, indent):
    if bm.get("add_date") is not None:
        return (
            "%s<DT><A HREF=\"%s\" ADD_DATE=\"%d\">%s</A>"
            % (
                indent,
                _escape_html(bm["url"]),
                bm["add_date"],
                _escape_html(bm["title"] or ""),
            )
        )
    return (
        "%s<DT><A HREF=\"%s\">%s</A>"
        % (indent, _escape_html(bm["url"]), _escape_html(bm["title"] or ""))
    )


def export_netscape(bookmarks):
    """UIR 条目列表 → Netscape HTML 字节（UTF-8、LF、结尾换行）。"""
    lines = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        "<!-- This is an automatically generated file. -->",
        "<META HTTP-EQUIV=\"Content-Type\" CONTENT=\"text/html; charset=UTF-8\">",
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
        "<DL><p>",
    ]
    _render_folder(bookmarks, "    ", lines)
    lines.append("</DL><p>")
    return ("\n".join(lines) + "\n").encode("utf-8")

"""Netscape HTML 导出/导回（M2 最小形态 → M5 完整，plan/04 §4.3）。

M2 起：UIR 条目 → 合规 Netscape HTML 字节，作为"解析 → 导出 → 再解析"
往返一致性测试的 B 面（plan/04 §1.4）；M5 扩展：
- ``filter_bookmarks``：按 dedupe/check 既有结论过滤（**只消费判定，不判定**）；
- 默认**不删不改**（全量导回）；``--apply-dedupe`` / ``--exclude-dead``
  为显式可选动作（用户确认后才生效）。

转义纪律（plan/04 §4.3）：标题/URL 中 ``& < > "`` 转义；中文原样。
文件夹分组按 UIR folder 路径重建嵌套结构（往返测试只比较条目，
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


def filter_bookmarks(bookmarks, dedupe_payload=None, check_payload=None,
                     apply_dedupe=False, exclude_dead=False):
    """按既有判定过滤导出集（只消费 check/dedupe 结论，零第二份判定）。

    - ``apply_dedupe=True``：重复组中**非建议保留项**的成员被剔除；
      未进任何重复组的书签原样保留（"合并"只作用于组内，不波及全量）；
    - ``exclude_dead=True``：剔除 check 结论为 ``dead`` 的条目；
    - 两个开关默认 False（默认不删不改，全量导回）。
    返回过滤后的 UIR 条目列表（原条目 dict 引用，不改写任何字段）。
    """
    result = bookmarks
    if apply_dedupe and dedupe_payload:
        drop_ids = set()
        for group in dedupe_payload.get("duplicate_groups", []):
            keep = group.get("keep", {})
            keep_id = keep.get("id")
            for member in group.get("members", []):
                member_id = member.get("id")
                if member_id and member_id != keep_id:
                    drop_ids.add(member_id)
        result = [bm for bm in result if bm["id"] not in drop_ids]
    if exclude_dead and check_payload:
        dead_urls = {
            item["url"]
            for item in check_payload.get("results", [])
            if item.get("verdict") == "dead"
        }
        result = [bm for bm in result if bm["url"] not in dead_urls]
    return result


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

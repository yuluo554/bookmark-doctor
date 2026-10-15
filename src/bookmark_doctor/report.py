"""单文件 HTML 报告渲染（M5，plan/04 §4.2）。

单一渲染源雏形（plan/04 §4.4 红线）：**渲染层零判定逻辑**——只消费
check.json / dedupe.json / aging 画像的既有结论，不做任何二次判定；
一切 verdict/reason/分组原样呈现。"未探测项" 只是 tree ∖ check 的
集合差呈现（未知不猜补，不参与三态计数）。

资源零外链硬断言（plan/04 §4.2）：无 ``<link>``、外链 ``<script src>``、
外链 ``<img>``、``@import``、外部字体；CSS 全内联；数据中的 URL 仅作为
``<a href>`` 文本/链接呈现（点击行为属功能，不算资源外链）——断网可开。

确定性（K18 纪律）：无时钟、无随机；``render_report`` 输出逐字节一致。
HTML 转义纪律与 export.py 同源：标题/URL 中 ``& < > "`` 转义，中文原样。
"""

_ESCAPE_ORDER = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
)

# 资源零外链硬断言的禁用词面（开标签/指令形态；大小写不敏感）
_FORBIDDEN_RESOURCE_PATTERNS = (
    "<link",
    "<script src=",
    "<img",
    "@import",
    "url(http",
    "url(//",
    "@font-face",
)

_PAGE_CSS = """\
body{font-family:system-ui,'Microsoft YaHei',sans-serif;margin:2rem;color:#1a1a1a;background:#fafafa}
h1{font-size:1.5rem}h2{font-size:1.15rem;border-bottom:1px solid #ccc;padding-bottom:.3rem;margin-top:2rem}
table{border-collapse:collapse;width:100%;margin:.6rem 0}
th,td{border:1px solid #bbb;padding:.35rem .5rem;text-align:left;word-break:break-all}
th{background:#eee}
.badge{display:inline-block;padding:.1rem .5rem;border-radius:.6rem;font-size:.85rem;color:#fff}
.dead{background:#c0392b}.review{background:#d68910}.alive{background:#27ae60}
.noprobe{background:#7f8c8d}.unknown{background:#7f8c8d}
.muted{color:#666;font-size:.9rem}
.section-note{background:#fffbe6;border:1px solid #e6d976;padding:.5rem .8rem;font-size:.9rem}
"""


def _escape_html(text):
    for raw, escaped in _ESCAPE_ORDER:
        text = text.replace(raw, escaped)
    return text


def _rows(cells, tag="td"):
    return "<tr>%s</tr>" % "".join(
        "<%s>%s</%s>" % (tag, _escape_html(str(cell)), tag) for cell in cells
    )


def _url_cell(url):
    # URL 作为链接呈现属功能行为，不算资源外链（plan/04 §4.2 口径）。
    return '<a href="%s">%s</a>' % (_escape_html(url), _escape_html(url))


def _section(title, body, note=None):
    parts = ["<h2>%s</h2>" % _escape_html(title)]
    if note:
        parts.append('<p class="section-note">%s</p>' % note)
    parts.append(body)
    return "\n".join(parts)


def assert_no_external_resources(html):
    """资源零外链硬断言：命中禁用词面 → AssertionError（测试常驻）。"""
    lowered = html.lower()
    for pattern in _FORBIDDEN_RESOURCE_PATTERNS:
        if pattern in lowered:
            raise AssertionError("报告出现外链/外采资源词面: %r" % pattern)
    return html


def render_report(check_payload, dedupe_payload=None, aging_profile=None,
                  tree_bookmarks=None):
    """check/dedupe 载荷 + 画像 + UIR 条目 → 完整 HTML 文档字节（七节 + 未探测分区）。

    纯渲染：三个载荷任一可缺（对应节呈现"无数据"），不做任何判定补算。
    """
    tree_bookmarks = tree_bookmarks or []
    results = check_payload.get("results", [])
    summary = check_payload.get("summary", {})
    verdict_counts = summary.get("verdict_counts", {})
    total = summary.get("total", len(results))

    # 标题映射与未探测集合：纯集合差呈现（渲染层零判定）
    titles_by_url = {}
    for bm in tree_bookmarks:
        titles_by_url[bm["url"]] = bm.get("title") or ""
    probed_urls = {item["url"] for item in results}
    unprobed = [bm for bm in tree_bookmarks if bm["url"] not in probed_urls]

    def title_of(url):
        return titles_by_url.get(url, "")

    dead = [item for item in results if item.get("verdict") == "dead"]
    review = [item for item in results if item.get("verdict") == "review"]
    alive_count = verdict_counts.get("alive", 0)
    other_verdicts = {
        key: value
        for key, value in sorted(verdict_counts.items())
        if key not in ("dead", "review", "alive")
    }
    groups = (dedupe_payload or {}).get("duplicate_groups", [])

    sections = []

    # 1. 摘要
    summary_rows = [
        _rows(["探测总数", total]),
        _rows(["alive（存活）", alive_count]),
        _rows(["dead（失效）", len(dead)]),
        _rows(["review（待复核）", len(review)]),
    ]
    for verdict, count in other_verdicts.items():
        summary_rows.append(_rows([verdict, count]))
    summary_rows.append(_rows(["重复组", len(groups)]))
    if aging_profile is not None:
        unknown_n = aging_profile["unknown_add_date"]["count"]
        tier_summary = "，".join(
            "%s %d" % (tier["tier"], tier["count"]) for tier in aging_profile["tiers"]
        )
        summary_rows.append(
            _rows(["长期未访问（%s；添加时间未知 %d）" % (tier_summary, unknown_n),
                   aging_profile["as_of_date"]])
        )
    summary_rows.append(_rows(["未探测条目", len(unprobed)]))
    sections.append(_section("摘要", "<table>%s</table>" % "\n".join(summary_rows)))

    # 2. 失效清单（dead）
    if dead:
        body = "<table>\n%s\n</table>" % "\n".join(
            [_rows(["标题", "URL", "reason"], tag="th")]
            + [_rows([title_of(item["url"]) or "（无标题）", _url_cell(item["url"]),
                      item["reason"]])
               for item in dead]
        )
    else:
        body = "<p>无失效条目。</p>"
    sections.append(_section("失效清单（dead）", body))

    # 3. 待复核清单（review）
    if review:
        body = "<table>\n%s\n</table>" % "\n".join(
            [_rows(["标题", "URL", "reason", "rule_id", "conflict"], tag="th")]
            + [_rows([title_of(item["url"]) or "（无标题）", _url_cell(item["url"]),
                      item["reason"], item.get("rule_id") or "—",
                      str(item.get("conflict") or "—")])
               for item in review]
        )
    else:
        body = "<p>无待复核条目。</p>"
    sections.append(
        _section("待复核清单（review）", body,
                 note="待复核 ≠ 失效：需人工打开确认；判定为辅助参考。")
    )

    # 4. 重复清单
    if groups:
        rows = [_rows(["组", "成员数", "建议保留项", "成员 URL / 仅锚点不同标记"], tag="th")]
        for group in groups:
            members = group.get("members", [])
            keep = group.get("keep", {})
            rows.append(_rows([
                group.get("group_id", ""),
                len(members),
                _url_cell(keep.get("url", "")) if keep.get("url") else "—",
                "；".join(
                    "%s%s" % (m["url"], "（仅锚点不同）" if m.get("fragment_variant") else "")
                    for m in members
                ),
            ]))
        body = "<table>\n%s\n</table>" % "\n".join(rows)
    else:
        body = "<p>未发现重复书签。</p>"
    sections.append(
        _section("重复清单", body,
                 note="默认不删除任何书签；合并需在导回时显式传 --apply-dedupe。")
    )

    # 5. 长期未访问画像
    if aging_profile is not None:
        rows = [_rows(["分档", "阈值（天）", "条数"], tag="th")]
        for tier in aging_profile["tiers"]:
            rows.append(_rows([tier["tier"], tier["min_days"], tier["count"]]))
        rows.append(_rows([aging_profile["within"]["tier"], "—",
                           aging_profile["within"]["count"]]))
        rows.append(_rows(["添加时间未知", "—",
                           aging_profile["unknown_add_date"]["count"]]))
        body = "<table>\n%s\n</table>\n<p class=muted>%s</p>" % (
            "\n".join(rows), _escape_html(aging_profile["note"]),
        )
    else:
        body = "<p>未生成画像（无 aging 数据）。</p>"
    sections.append(_section("长期未访问画像", body))

    # 5b. 未探测条目（独立分区；未知不猜补）
    if unprobed:
        body = "<table>\n%s\n</table>" % "\n".join(
            [_rows(["标题", "URL"], tag="th")]
            + [_rows([bm.get("title") or "（无标题）", _url_cell(bm["url"])])
               for bm in unprobed]
        )
    else:
        body = "<p>无未探测条目。</p>"
    sections.append(
        _section("未探测条目", body,
                 note="未探测条目不计入任何三态（未知不猜补）。")
    )

    # 6. 建议清理清单（策略说明 + 待确认条目；不自动执行）
    cleanup_rows = []
    for item in dead:
        cleanup_rows.append(_rows(["失效", title_of(item["url"]) or "（无标题）",
                                   _url_cell(item["url"]), item["reason"]]))
    for group in groups:
        members = group.get("members", [])
        keep = group.get("keep", {})
        cleanup_rows.append(_rows(
            ["重复", "组 %s（%d 条）" % (group.get("group_id", ""), len(members)),
             _url_cell(keep.get("url", "")) if keep.get("url") else "—",
             "保留 1 条，其余待确认合并"],
        ))
    if cleanup_rows:
        body = "<table>\n%s\n</table>" % "\n".join(
            [_rows(["类型", "对象", "建议动作对象", "说明"], tag="th")] + cleanup_rows
        )
    else:
        body = "<p>无需清理项。</p>"
    sections.append(
        _section("建议清理清单", body,
                 note="本报告不自动删除/合并任何书签；确认后在导回时用显式开关执行。")
    )

    # 7. 口径与免责
    disclaimer = [
        "<ul>",
        "<li>三态定义：alive=存活；dead=失效（确定性信号）；review=待复核"
        "（不确定或需规则确认）。</li>",
        "<li>判定为辅助参考，最终以浏览器实际打开为准。</li>",
        "<li>数据来源：check/dedupe 产物 + ruleset（版本 %s / 修订 %s）；"
        "探测日期 %s。</li>" % (
            _escape_html(str(check_payload.get("ruleset_version", "—"))),
            _escape_html(str(check_payload.get("ruleset_revision", "—"))),
            _escape_html(str(check_payload.get("probe_date", "—"))),
        ),
        "<li>长期未访问口径：以添加时间近似未访问；浏览器不导出真实访问记录。</li>",
        "<li>未探测条目不计入任何三态（未知不猜补）。</li>",
        "</ul>",
    ]
    sections.append(_section("口径与免责", "\n".join(disclaimer)))

    html = (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<title>收藏夹体检报告</title>\n"
        "<style>\n%s</style>\n</head>\n<body>\n"
        "<h1>收藏夹体检报告</h1>\n%s\n</body>\n</html>\n"
    ) % (_PAGE_CSS, "\n".join(sections))
    return assert_no_external_resources(html).encode("utf-8")

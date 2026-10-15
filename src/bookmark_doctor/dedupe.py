"""去重引擎（M3）——比较键分组 + 建议保留项。

规格出处：plan/04 §3.1/§3.2 [冻结草案落地]、HANDOFF-M3 待办 #4。

口径：
- 比较键 = ``normalize_url(url)``；``check.json`` 有 ``final_url`` 时
  **优先**用 ``normalize(final_url)``（plan/04 §3.1 第 6 步后半）；
- 保留策略（固定、可复现）：https 优先 > 无追踪参数 > add_date 最早 >
  文件序最早（UIR 条目序即 (来源声明顺序, 来源内文件序)，K17）；
- **绝不自动删**：只出清单，``export --apply-dedupe`` 为 M5 显式开关；
- 仅 fragment 不同的成员归入同组，组附 ``fragment_variant`` 标记；
- 未收录短链不猜（normalize 不做映射，``shortlink_known`` 缺省空）。
"""

from urllib.parse import parse_qsl, urlsplit

from bookmark_doctor.normalize import fragment_of, normalize_url

# 追踪参数判定（保留策略"无追踪参数优先"消费 tracked_query_params 名单）
REASON_FRAGMENT_VARIANT = "fragment_variant"


def _has_tracked_param(url, tracked_params):
    exact = set(tracked_params.get("exact", []))
    prefixes = tuple(tracked_params.get("prefixes", []))
    query = urlsplit(url).query
    if not query:
        return False
    for name, _ in parse_qsl(query, keep_blank_values=True):
        if name in exact or name.startswith(prefixes):
            return True
    return False


def _keep_score(bookmark, tracked_params):
    """保留优先级键：越小越优先保留（plan/04 §3.2 固定策略）。

    1. https 优先（scheme == https 记 0）；
    2. 无追踪参数优先；
    3. add_date 最早（None 视为最大——未知不与已知争，K14 未知不猜补）；
    4. 文件序最早 = UIR 列表序（元组比较天然由 index 兜底）。
    """
    scheme_https = 0 if urlsplit(bookmark["url"]).scheme.lower() == "https" else 1
    tracked = 1 if _has_tracked_param(bookmark["url"], tracked_params) else 0
    add_date = bookmark.get("add_date")
    date_rank = add_date if add_date is not None else float("inf")
    return (scheme_https, tracked, date_rank)


def build_duplicate_groups(bookmarks, tracked_params, check_records=None):
    """UIR 条目 + 规则包参数 → 重复组清单（dedupe.json ``duplicate_groups``）。

    ``check_records``：check.json ``results``（可选）——有 ``final_url``
    时比较键优先用 normalize(final_url)。
    比较键相同但**原文 URL 完全一致**的合并条目（M2 import 已合并多来源）
    不会在此重复出现；本函数按"原文不同、比较键相同"分组。

    绝不修改输入条目；输出仅清单（绝不自动删）。
    """
    final_by_url = {}
    for record in check_records or []:
        final = record.get("final_url")
        if final:
            final_by_url[record.get("url")] = final

    groups = {}
    order = []
    for index, bm in enumerate(bookmarks):
        url = bm["url"]
        # 比较键：final_url 优先（探测后真实落点），否则原文
        key_source = final_by_url.get(url, url)
        key = normalize_url(key_source, tracked_params)
        if key not in groups:
            groups[key] = {"index": [], "fragments": set()}
            order.append(key)
        groups[key]["index"].append(index)
        frag = fragment_of(url)
        if frag:
            groups[key]["fragments"].add(frag)

    duplicate_groups = []
    for group_id, key in enumerate(order, 1):
        members_index = groups[key]["index"]
        if len(members_index) < 2:
            continue
        members = [bookmarks[i] for i in members_index]
        # fragment_variant：存在"仅 fragment 不同"的成员——以规范化键为基
        # （追踪参数/尾斜杠/scheme 差异已被流水线吸收），fragment 互异才算
        # （plan/04 §3.1 第 5 步：两条 URL 仅 fragment 不同 → 合并 + 标记）
        bases = {normalize_url(bm["url"], tracked_params) for bm in members}
        fragments = set()
        for bm in members:
            fragments.add(fragment_of(bm["url"]) or "")
        fragment_variant = len(bases) == 1 and len(fragments) > 1
        # 建议保留项：固定策略（https > 无追踪参数 > add_date 最早 > 文件序最早）
        keeper = min(members, key=lambda bm: _keep_score(bm, tracked_params))
        duplicate_groups.append(
            {
                "group_id": "dup-%04d" % group_id,
                "key": key,
                "fragment_variant": fragment_variant,
                "members": [
                    {"id": bm["id"], "url": bm["url"], "title": bm.get("title")}
                    for bm in members
                ],
                "keep": {"id": keeper["id"], "url": keeper["url"]},
            }
        )
    return duplicate_groups

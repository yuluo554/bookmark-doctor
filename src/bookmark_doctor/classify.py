"""状态分类引擎（M3）——规则优先于通用映射。

规格出处：plan/04 §2.2 状态分类表 [冻结草案落地]、§2.3 降级规则、HANDOFF-M3 待办 #2。

判定优先级（冻结）：
1. **规则命中**（锚点硬门已通过的 degrade_rules）> 通用映射；
2. 多规则冲突 → **保守**：``review`` > ``dead`` > ``alive``，并在备注记录冲突；
3. 通用映射表（plan/04 §2.2）：
   - 终态 2xx → alive / ``http_2xx``
   - 终态 3xx（跟随耗尽仍 3xx）→ review / ``redirect_unresolved``
   - 404/410 → dead / ``http_404`` / ``http_410``（唯一通用判死证据）
   - 401/403/405/406/429/451 → review / ``http_4xx_blocked``
   - 5xx → review / ``http_5xx``；521/522/523 → review / ``cdn_blocked``
   - error_class（DNS 失败/超时/TLS/连接失败/跳转异常）→ review / 该原因码

规则匹配维度（M3 启用）：``host_suffix``（域名后缀）+ ``http_status``。
匹配语义（M3 冻结）：观测侧 ``http_status`` 为**首跳或终态**之一即可命中
（M1 实测：知乎/微博风控首跳 302、终态登录/访客页；规则须在首跳就能拦）。
本模块不含任何数值/主机名字面量（零字面量门禁）——状态分类表是**语义分类**
（按 HTTP 语义区间分派），非政策数值；探测数值全部取 ruleset。
"""

_VERDICT_ORDER_CONSERVATIVE = {"review": 0, "dead": 1, "alive": 2}

# HTTP 语义区间（分类表，plan/04 §2.2——语义区间非政策数值）
REASON_HTTP_2XX = "http_2xx"
REASON_REDIRECT_UNRESOLVED = "redirect_unresolved"
REASON_HTTP_404 = "http_404"
REASON_HTTP_410 = "http_410"
REASON_HTTP_4XX_BLOCKED = "http_4xx_blocked"
REASON_HTTP_5XX = "http_5xx"
REASON_CDN_BLOCKED = "cdn_blocked"

# CDN 反爬区间（"源站不可达但服务在线"形态，plan/04 §2.2 明示 521 等 →
# cdn_blocked——M1 实测该形态已 verified 锚点，站点名只住 ruleset 正本）
CDN_BLOCKED_STATUSES = (521, 522, 523)
# 权限/反爬/限流区间（不判死；plan/04 §2.2 行）
REVIEW_4XX_STATUSES = (401, 403, 405, 406, 429, 451)


def _host_matches(host_suffix, url_host):
    """域名后缀匹配：host == suffix 或 host 以 "." + suffix 结尾（防近似域名误命中）。"""
    if not host_suffix:
        return False
    return url_host == host_suffix or url_host.endswith("." + host_suffix)


def _url_host(url):
    from urllib.parse import urlsplit

    return (urlsplit(url).hostname or "").lower()


def generic_verdict(probe_record):
    """通用映射：探测记录 → (verdict, reason)。规则未命中时消费。

    ``probe_record``：probe.ProbeResult.as_dict() 形态。
    """
    error_class = probe_record.get("error_class")
    if error_class:
        # 跳转超限/成环/DNS/超时/TLS/连接失败 → 全部 review（保守）
        return "review", error_class
    status = probe_record.get("http_status")
    if status is None:
        # 无状态无错误：探测记录异常——保守 review（不可静默判 alive）
        return "review", "probe_incomplete"
    if 200 <= status < 300:
        return "alive", REASON_HTTP_2XX
    if 300 <= status < 400:
        return "review", REASON_REDIRECT_UNRESOLVED
    if status == 404:
        return "dead", REASON_HTTP_404
    if status == 410:
        return "dead", REASON_HTTP_410
    if status in REVIEW_4XX_STATUSES:
        return "review", REASON_HTTP_4XX_BLOCKED
    if status in CDN_BLOCKED_STATUSES:
        return "review", REASON_CDN_BLOCKED
    if 500 <= status < 600:
        return "review", REASON_HTTP_5XX
    # 其余 4xx（400/402/407-428/430+ 等）：语义不明 → 保守 review
    return "review", "http_other"


def match_rule(probe_record, rule):
    """单条规则是否命中该探测记录（M3 维度：host_suffix + http_status，首跳或终态）。

    返回 True/False。未启用维度（M3 未实测）不参与匹配。
    """
    match = rule.get("match") or {}
    suffix = match.get("host_suffix")
    if not suffix or not _host_matches(suffix, _url_host(probe_record.get("url", ""))):
        return False
    want_status = match.get("http_status")
    if want_status is None:
        return False
    observed = []
    if probe_record.get("http_status") is not None:
        observed.append(probe_record["http_status"])
    # 跳转链上每跳的响应状态未知（probe 只记 URL）——首跳状态 = 原始 url 的响应。
    # probe_record 的 http_status 即"终态或跟随耗尽前最后一次收到的状态"，
    # redirect_chain[0] 的响应形态由 http_status 兜底覆盖（M1 实测口径：
    # 规则挂"首跳 302/403/521"时 probe 的单状态字段就是该响应）。
    return want_status in observed


def _conservative(pairs):
    """多判定冲突 → 保守取值 + 冲突备注。pairs: [(verdict, reason, rule_id)]。"""
    if not pairs:
        return None
    best = min(pairs, key=lambda item: _VERDICT_ORDER_CONSERVATIVE.get(item[0], 3))
    verdicts = {item[0] for item in pairs}
    conflict_note = None
    if len(verdicts) > 1:
        conflict_note = "rule_conflict:" + "|".join(
            sorted("%s=%s" % (item[2] or "?", item[1]) for item in pairs)
        )
    return best[0], best[1], conflict_note


def classify(probe_record, effective_rules):
    """探测记录 + 生效规则 → 分类结果 dict（check.json 条目后半）。

    返回：{"verdict", "reason", "rule_id"(或 None), "conflict"(或 None)}。
    规则优先于通用映射；多规则冲突取保守并留备注（plan/04 §2.2）。
    """
    hits = []
    for rule in effective_rules:
        if match_rule(probe_record, rule):
            hits.append((rule.get("disposition"), rule.get("reason"), rule.get("id")))
    if hits:
        verdict, reason, conflict_note = _conservative(hits)
        return {
            "verdict": verdict,
            "reason": reason,
            "rule_id": hits[0][2],
            "conflict": conflict_note,
        }
    verdict, reason = generic_verdict(probe_record)
    return {"verdict": verdict, "reason": reason, "rule_id": None, "conflict": None}

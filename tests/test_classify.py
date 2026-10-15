"""M3 classify（状态分类 + 规则引擎）测试——plan/04 §2.2/§2.3 落地对账。

含规则驱动层的"不该命中"反向样例（plan/04 §5.2）：host_suffix 边界、
状态不匹配、规则优先于通用映射、多规则冲突保守取值。
"""

import pytest

from bookmark_doctor.classify import classify, generic_verdict, match_rule

_RULE_403 = {
    "id": "R-TEST-403",
    "match": {"host_suffix": "example.com", "http_status": 403},
    "disposition": "review",
    "reason": "http_403_botguard",
}
_RULE_DEAD = {
    "id": "R-TEST-DEAD",
    "match": {"host_suffix": "example.com", "http_status": 403},
    "disposition": "dead",
    "reason": "rule_dead",
}


@pytest.mark.parametrize(
    "status,verdict,reason",
    [
        (200, "alive", "http_2xx"),
        (204, "alive", "http_2xx"),
        (302, "review", "redirect_unresolved"),
        (404, "dead", "http_404"),
        (410, "dead", "http_410"),
        (403, "review", "http_4xx_blocked"),
        (401, "review", "http_4xx_blocked"),
        (429, "review", "http_4xx_blocked"),
        (451, "review", "http_4xx_blocked"),
        (521, "review", "cdn_blocked"),
        (523, "review", "cdn_blocked"),
        (500, "review", "http_5xx"),
        (503, "review", "http_5xx"),
    ],
)
def test_generic_mapping_table(status, verdict, reason):
    assert generic_verdict({"http_status": status, "error_class": None}) == (verdict, reason)


@pytest.mark.parametrize(
    "error_class",
    [
        "dns_failure",
        "connect_timeout",
        "read_timeout",
        "tls_error",
        "connection_error",
        "redirect_loop",
        "too_many_redirects",
    ],
)
def test_error_class_always_review(error_class):
    # 网络不可达 ≠ 失效（FR-12）：error_class 一律 review，绝不判死
    verdict, reason = generic_verdict({"http_status": None, "error_class": error_class})
    assert verdict == "review"
    assert reason == error_class


def test_rule_beats_generic():
    rec = {"url": "https://www.example.com/q", "http_status": 403, "error_class": None}
    out = classify(rec, [_RULE_403])
    assert (out["verdict"], out["reason"], out["rule_id"]) == (
        "review",
        "http_403_botguard",
        "R-TEST-403",
    )


def test_host_suffix_boundary_positive():
    assert match_rule(
        {"url": "https://www.example.com/x", "http_status": 403}, _RULE_403
    )
    assert match_rule({"url": "https://example.com/x", "http_status": 403}, _RULE_403)


def test_host_suffix_boundary_negative():
    # 反向样例：后缀拼接近似域名不命中（防 mysite-example.com 误判）
    rec = {"url": "https://evil-example.com/x", "http_status": 403}
    assert not match_rule(rec, _RULE_403)
    # 状态不同不命中
    rec2 = {"url": "https://example.com/x", "http_status": 404}
    assert not match_rule(rec2, _RULE_403)
    # 通用映射兜底
    out = classify(rec2, [_RULE_403])
    assert out["verdict"] == "dead" and out["rule_id"] is None


def test_conflict_conservative_review_wins():
    out = classify(
        {"url": "https://example.com/q", "http_status": 403, "error_class": None},
        [_RULE_403, _RULE_DEAD],
    )
    assert out["verdict"] == "review"
    assert out["conflict"] and "R-TEST-DEAD" in out["conflict"] and "R-TEST-403" in out["conflict"]


def test_conflict_dead_beats_alive():
    alive_rule = {
        "id": "R-A",
        "match": {"host_suffix": "example.com", "http_status": 200},
        "disposition": "alive",
        "reason": "r_a",
    }
    dead_rule = {
        "id": "R-B",
        "match": {"host_suffix": "example.com", "http_status": 200},
        "disposition": "dead",
        "reason": "r_b",
    }
    out = classify(
        {"url": "https://example.com/q", "http_status": 200, "error_class": None},
        [alive_rule, dead_rule],
    )
    assert out["verdict"] == "dead"
    assert out["conflict"]


def test_no_rules_falls_to_generic():
    out = classify({"url": "https://example.com/x", "http_status": 404}, [])
    assert (out["verdict"], out["rule_id"]) == ("dead", None)


def test_probe_incomplete_conservative():
    # 无状态无错误的异常记录：不静默判 alive
    assert generic_verdict({"http_status": None, "error_class": None}) == (
        "review",
        "probe_incomplete",
    )

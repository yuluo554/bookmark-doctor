"""M3 normalize（URL 规范化）测试——plan/04 §3.1 六步流水线，每步配双向样例。"""

import pytest

from bookmark_doctor.normalize import fragment_of, normalize_url

_TRACKED = {
    "exact": ["share_token", "spm", "scm", "fbclid", "gclid", "igshid"],
    "prefixes": ["utm_", "share_"],
}


def test_scheme_http_to_https():
    assert normalize_url("http://example.com/a", _TRACKED) == "https://example.com/a"


def test_host_lowercase_and_default_port():
    assert normalize_url("https://EXAMPLE.com:443/a", _TRACKED) == "https://example.com/a"
    assert normalize_url("http://EXAMPLE.com:80/a", _TRACKED) == "https://example.com/a"


def test_non_default_port_kept():
    # 8080 非 https 默认端口 → 保留（不该合并的对照样例）
    assert (
        normalize_url("https://example.com:8080/a", _TRACKED)
        == "https://example.com:8080/a"
    )


def test_path_trailing_slash_and_collapsing():
    assert normalize_url("https://example.com/a/", _TRACKED) == "https://example.com/a"
    assert normalize_url("https://example.com//a///b", _TRACKED) == "https://example.com/a/b"
    # 根路径尾斜杠保留（不剥根）
    assert normalize_url("https://example.com/", _TRACKED) == "https://example.com/"


def test_path_distinct_not_merged():
    # 不该合并的对照：不同路径
    assert normalize_url("https://example.com/a", _TRACKED) != normalize_url(
        "https://example.com/b", _TRACKED
    )


def test_tracked_params_stripped_exact_and_prefix():
    assert (
        normalize_url("https://example.com/p?utm_source=x&id=2", _TRACKED)
        == "https://example.com/p?id=2"
    )
    assert (
        normalize_url("https://example.com/p?share_token=abc&id=2", _TRACKED)
        == "https://example.com/p?id=2"
    )
    assert (
        normalize_url("https://example.com/p?spm=a&scm=b&id=2", _TRACKED)
        == "https://example.com/p?id=2"
    )


def test_query_params_sorted():
    assert normalize_url("https://example.com/p?b=2&a=1", _TRACKED) == normalize_url(
        "https://example.com/p?a=1&b=2", _TRACKED
    )


def test_non_tracked_param_not_merged():
    # 不该合并的对照：非追踪参数不同 → 不同比较键
    assert normalize_url("https://example.com/p?a=1", _TRACKED) != normalize_url(
        "https://example.com/p?a=2", _TRACKED
    )


def test_fragment_stripped():
    assert normalize_url("https://example.com/p#x", _TRACKED) == normalize_url(
        "https://example.com/p", _TRACKED
    )


def test_shortlink_mapping_applied():
    mapping = {"https://s.cn/abc": "https://example.com/real"}
    assert normalize_url("https://s.cn/abc", _TRACKED, mapping) == "https://example.com/real"


def test_unknown_shortlink_not_guessed():
    # 未收录短链不猜：不映射、保持原形（M2 语义——不可跨形态猜合）
    assert normalize_url("https://s.cn/unknown", _TRACKED, {}) == "https://s.cn/unknown"


def test_tracked_list_from_ruleset_shape():
    # 名单必须来自 ruleset 节——空名单时 utm 不剥（防第二份名单）
    empty = {"exact": [], "prefixes": []}
    assert normalize_url("https://example.com/p?utm_source=x", empty) == (
        "https://example.com/p?utm_source=x"
    )


def test_fragment_of():
    assert fragment_of("https://example.com/p#frag") == "frag"
    assert fragment_of("https://example.com/p") is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("http://Example.com:80", "https://example.com"),
        ("https://example.com/a/b/", "https://example.com/a/b"),
        ("http://example.com/x?utm_source=1&keep=2#z", "https://example.com/x?keep=2"),
    ],
)
def test_pipeline_combined(raw, expected):
    assert normalize_url(raw, _TRACKED) == expected

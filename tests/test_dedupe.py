"""M3 dedupe（去重引擎）测试——plan/04 §3.2 保留策略 + fragment_variant。

真值样例与合成集 truth.json 的 duplicate_groups 形态对账
（utm/share_token 剥离合并 + fragment 变体标记）。
"""

import json

from bookmark_doctor.dedupe import build_duplicate_groups

_REPO_TRUTH = None


def _truth():
    global _REPO_TRUTH
    if _REPO_TRUTH is None:
        import pathlib

        root = pathlib.Path(__file__).resolve().parent.parent
        _REPO_TRUTH = json.loads(
            (root / "data" / "fixtures" / "set-1" / "truth.json").read_text(encoding="utf-8")
        )["expect"]
    return _REPO_TRUTH


_TRACKED = {
    "exact": ["share_token", "spm", "scm", "fbclid", "gclid", "igshid"],
    "prefixes": ["utm_", "share_"],
}


def _bm(bid, url, add_date=100, source="s.html"):
    return {
        "id": bid,
        "title": bid,
        "url": url,
        "add_date": add_date,
        "folder": [],
        "source": source,
    }


def test_tracking_variant_group_merged():
    groups = build_duplicate_groups(
        [
            _bm("a", "https://x.com/posts/1?utm_source=share&utm_medium=link", 100),
            _bm("b", "https://x.com/posts/1/?share_token=abc4", 200),
        ],
        _TRACKED,
    )
    assert len(groups) == 1
    assert groups[0]["key"] == "https://x.com/posts/1"
    assert [m["id"] for m in groups[0]["members"]] == ["a", "b"]


def test_fragment_variant_marked():
    groups = build_duplicate_groups(
        [
            _bm("a", "https://x.com/p/1"),
            _bm("b", "https://x.com/p/1#daily"),
        ],
        _TRACKED,
    )
    assert len(groups) == 1
    assert groups[0]["fragment_variant"] is True


def test_fragment_same_not_marked():
    groups = build_duplicate_groups(
        [
            _bm("a", "https://x.com/p/1#daily"),
            _bm("b", "https://x.com/p/1#daily"),
        ],
        _TRACKED,
    )
    assert groups[0]["fragment_variant"] is False


def test_keep_prefers_https():
    groups = build_duplicate_groups(
        [
            _bm("h", "http://x.com/p", 50),  # 更早但是 http
            _bm("s", "https://x.com/p", 100),
        ],
        _TRACKED,
    )
    assert groups[0]["keep"]["id"] == "s"


def test_keep_prefers_no_tracked_param():
    groups = build_duplicate_groups(
        [
            _bm("t", "https://x.com/p?utm_source=x", 50),  # 更早但带追踪参数
            _bm("c", "https://x.com/p", 100),
        ],
        _TRACKED,
    )
    assert groups[0]["keep"]["id"] == "c"


def test_keep_prefers_earliest_add_date_then_file_order():
    groups = build_duplicate_groups(
        [
            _bm("late", "https://x.com/p", 200),
            _bm("early", "https://x.com/p", 50),
        ],
        _TRACKED,
    )
    assert groups[0]["keep"]["id"] == "early"
    # add_date 双 None → 文件序兜底
    groups = build_duplicate_groups(
        [_bm("x", "https://x.com/q", None), _bm("y", "https://x.com/q/", None)],
        _TRACKED,
    )
    assert groups[0]["keep"]["id"] == "x"


def test_unique_urls_no_groups():
    groups = build_duplicate_groups(
        [_bm("a", "https://x.com/1"), _bm("b", "https://x.com/2")], _TRACKED
    )
    assert groups == []


def test_final_url_takes_priority():
    # 探测后 final_url 落点相同 → 原文不同的两条合并（plan/04 §3.1 第 6 步）
    groups = build_duplicate_groups(
        [_bm("a", "https://short.cn/abc"), _bm("b", "https://x.com/real")],
        _TRACKED,
        check_records=[
            {"url": "https://short.cn/abc", "final_url": "https://x.com/real"},
        ],
    )
    assert len(groups) == 1


def test_never_modifies_input():
    bms = [_bm("a", "https://x.com/p/1?utm_source=x"), _bm("b", "https://x.com/p/1/")]
    original_urls = [bm["url"] for bm in bms]
    build_duplicate_groups(bms, _TRACKED)
    assert [bm["url"] for bm in bms] == original_urls


def test_truth_fixture_duplicate_groups_all_matched():
    """合成集真值：duplicate_groups 组员按比较键全命中（真值驱动对账）。"""
    truth = _truth()
    # 用真值的成员 URL 重建输入（成员顺序与真值一致）
    bms = []
    for i, group in enumerate(truth["duplicate_groups"]):
        for j, url in enumerate(group["members"]):
            bms.append(_bm("t%d_%d" % (i, j), url, 100 + j))
    groups = build_duplicate_groups(bms, _TRACKED)
    assert len(groups) == len(truth["duplicate_groups"])
    keys = {g["key"] for g in groups}
    for group in truth["duplicate_groups"]:
        from bookmark_doctor.normalize import normalize_url

        assert normalize_url(group["expect_merge_to"], _TRACKED) in keys

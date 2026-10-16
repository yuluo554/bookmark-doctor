"""M4 基准测试——退出码三语义 + 探活（端到端打 bench 真实入口）+ mock 重写机制。

plan/05 §4.4：探活打**端到端入口**（bench.py 真返回非 0），不止函数层；
退出码 0 达标 / 1 未达标（含空分母 not_enabled）/ 2 用法与未知名，全部锁进测试。
subprocess 真跑 tools/bench.py（全程 loopback，离线）。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _parse_report(stdout_bytes):
    """从 bench stdout 提取首个完整 JSON 文档（其后还有 [bench] 摘要行）。"""
    text = stdout_bytes.decode("utf-8", "replace")
    start = text.find("{")
    if start < 0:
        raise AssertionError("bench stdout 无 JSON 报告:\n%s" % text[-800:])
    depth = 0
    in_str = False
    esc = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : idx + 1])
    raise AssertionError("bench stdout JSON 不完整:\n%s" % text[-800:])


def _run_bench(args, timeout=240):
    env = {
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "PATH": os.environ.get("PATH", ""),
        "TEMP": os.environ.get("TEMP", ""),
        "TMP": os.environ.get("TMP", ""),
    }
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(REPO_ROOT / "tools" / "bench.py")] + args,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


@pytest.fixture(scope="module")
def bench_green():
    """全量基准一次跑（复用：多断言共享一次运行，缩短测试时长）。"""
    proc = _run_bench(["--report", ".tmp/bench-test-green.json"])
    report = None
    report_path = REPO_ROOT / ".tmp" / "bench-test-green.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
    return proc, report


def test_bench_green_exit0_all_suites_pass(bench_green):
    """基准常态：B1–B6 全绿 → exit 0（plan/05 §4.4 退出码语义 0）。"""
    proc, report = bench_green
    assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")[-2000:]
    assert report is not None and report["all_passed"] is True
    suites = {s["suite"] for s in report["suites"]}
    assert suites == {"B1", "B2", "B3", "B4", "B5", "B6"}


def test_bench_false_dead_zero_hard_gate(bench_green):
    """false_dead=0 硬门：B1/B2 误判 dead 数为 0（plan/04 §5.2）。"""
    _, report = bench_green
    metrics = {s["suite"]: s["metrics"] for s in report["suites"]}
    assert metrics["B1"]["false_dead"] == 0
    assert metrics["B2"]["false_dead"] == 0


def test_bench_false_alive_zero_hard_gate(bench_green):
    """false_alive=0 硬门：B1 反爬样本不得被判 alive（风控 302→登录页链）。"""
    _, report = bench_green
    metrics = {s["suite"]: s["metrics"] for s in report["suites"]}
    assert metrics["B1"]["false_alive"] == 0


def test_bench_b1_samples_hit_real_rules(bench_green):
    """样本真经规则库：B1 反爬样本命中真实规则 id（非纯通用映射）。"""
    _, report = bench_green
    # 从落盘报告读不到逐条结果，改用函数层：直接跑一次流水线检查 rule_id
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    try:
        import bench as bench_mod

        chrome_obj, netscape_text, truth_obj, manifest = bench_mod.load_fixtures()
        ruleset, effective_rules, _ = bench_mod.load_ruleset()
        alias_rules = bench_mod.build_mock_alias_rules(effective_rules)
        # 真实规则全部被桥接（4 条里 3 条有 mock 主机别名）
        aliased_ids = {r["id"] for r in alias_rules}
        assert aliased_ids == {"R-ZHIHU-403", "R-WEIBO-302", "R-CSDN-521"}, aliased_ids
        # 别名只改 host_suffix，其余语义沿用真实规则
        by_id = {r["id"]: r for r in effective_rules}
        for alias in alias_rules:
            real = by_id[alias["id"]]
            assert alias["match"]["http_status"] == real["match"]["http_status"]
            assert alias["disposition"] == real["disposition"]
            assert alias["reason"] == real["reason"]
            assert alias["match"]["host_suffix"].endswith(".mock.invalid")
    finally:
        sys.path.pop(0)


def test_bench_alias_bridge_drops_rule_when_real_missing():
    """桥接可证伪：真实 302 规则不存在 → 无别名 → 样本落通用映射（可判 alive）。

    证明"样本经规则库判定"是真命题：规则消失则基准失去保护（B1 false_alive 面）。
    """
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    try:
        import bench as bench_mod

        without_weibo = [{"id": "R-ZHIHU-403",
                          "match": {"host_suffix": "zhihu.com", "http_status": 403},
                          "disposition": "review", "reason": "http_403_botguard"}]
        aliases = bench_mod.build_mock_alias_rules(without_weibo)
        assert {r["id"] for r in aliases} == {"R-ZHIHU-403"}, aliases
        # risk-302 主机无规则可依 → 302→200 链终态 200 落 alive
        rec = {"url": "https://risk-302.mock.invalid/x", "http_status": 200,
               "first_hop_status": 302, "error_class": None}
        from bookmark_doctor.classify import classify
        assert classify(rec, aliases)["verdict"] == "alive"
    finally:
        sys.path.pop(0)


def test_bench_b1_302_sample_forms_real_redirect_chain(bench_green):
    """302 样本经 mock 真实跳转链（首跳 302 → 终态 200）——非合成 http_status。

    缺陷 2 修复面：bench mock 须发 Location 头，样本须真经规则引擎（首跳 302
    命中规则）而非被直接喂 http_status=302 绕过 probe。
    """
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    try:
        import bench as bench_mod

        chrome_obj, netscape_text, truth_obj, manifest = bench_mod.load_fixtures()
        ruleset, effective_rules, _ = bench_mod.load_ruleset()
        alias_rules = bench_mod.build_mock_alias_rules(effective_rules)
        bookmarks = bench_mod.build_uir(chrome_obj, netscape_text)
        server, mock_base_url = bench_mod.start_mock_server()
        try:
            unreachable_port = bench_mod._find_free_port()
            mock_base = type("MB", (), {"port": bench_mod._url_port(mock_base_url)})()
            host_map = bench_mod.build_host_map(manifest, mock_base, unreachable_port)
            payload, _ = bench_mod.run_probe_and_classify(
                bookmarks, ruleset, effective_rules, host_map, alias_rules=alias_rules)
        finally:
            server.shutdown()
            server.server_close()
        # 302 样本：重写后 host 为 loopback、原文主机名不进 URL（命名空间段 /bN），
        # 故按规则 id 识别（别名规则 R-WEIBO-302 仅挂 risk-302.mock.invalid）
        risk = [r for r in payload["results"] if r["rule_id"] == "R-WEIBO-302"]
        assert risk, "未找到 302 反爬样本"
        sample = risk[0]
        assert sample["first_hop_status"] == 302, "首跳状态未记录（缺陷 1 回归）"
        assert sample["http_status"] == 200, "终态应跟随跳转到 200"
        assert sample["redirect_chain"], "跳转链为空——mock 未发 Location 头"
        assert sample["verdict"] == "review"
    finally:
        sys.path.pop(0)


def test_bench_defect_302_first_hop_ignored_exit1(bench_green):
    """探活（可证伪）：规则匹配忽略首跳 → 风控 302→200 链判 alive → B1 红 + exit 1。

    这是"招牌功能空转"（缺陷 1）的基准级探活：修复前该缺陷真实存在于实现中。
    """
    proc = _run_bench(["--inject-defect", "302-first-hop-ignored", "--only", "B1"])
    assert proc.returncode == 1, "302 首跳缺陷未被基准抓到（基准失真）"
    payload = _parse_report(proc.stdout)
    b1 = [s for s in payload["suites"] if s["suite"] == "B1"][0]
    assert b1["passed"] is False
    assert b1["metrics"]["false_alive"] >= 1
    assert payload["injected_defect"] == "302-first-hop-ignored"


def test_bench_thresholds_from_manifest_not_code(bench_green):
    """门槛是数据非代码：suite 阈值与 manifest should_cover 一致（plan/05 §4.2）。"""
    _, report = bench_green
    manifest = json.loads(
        (REPO_ROOT / "data" / "fixtures" / "set-1" / "manifest.json").read_text(encoding="utf-8")
    )
    coverage = manifest["coverage"]
    metrics = {s["suite"]: s["metrics"] for s in report["suites"]}
    assert metrics["B1"]["threshold"] == coverage["review_not_dead"]["should_cover"]
    assert metrics["B2"]["threshold"] == coverage["unreachable_not_dead"]["should_cover"]
    assert metrics["B3"]["threshold"] == coverage["dead_hit"]["should_cover"]
    assert metrics["B5"]["threshold"] == coverage["duplicate_merge"]["should_cover"]


def test_bench_rewrite_all_loopback(bench_green):
    """防偷跑外网：mock 重写映射的目标全部为 loopback（plan/05 §4.3）。"""
    _, report = bench_green
    for host, entry in report["mock_rewrite"].items():
        assert host.endswith(".invalid")
        netloc = entry[2]
        assert netloc.startswith("127.0.0.1:"), "非 loopback 重写: %s -> %s" % (host, netloc)


def test_bench_defect_403_dead_exit1(bench_green):
    """探活（可证伪，端到端）：403 通用映射改 dead → B1 红 + exit 1（plan/04 §5.2）。"""
    proc = _run_bench(["--inject-defect", "403-dead", "--only", "B1"])
    assert proc.returncode == 1, "探活缺陷未被基准抓到（基准失真）"
    payload = _parse_report(proc.stdout)
    b1 = [s for s in payload["suites"] if s["suite"] == "B1"][0]
    assert b1["passed"] is False
    assert b1["metrics"]["false_dead"] >= 1
    assert payload["injected_defect"] == "403-dead"


def test_bench_unknown_only_exit2():
    """未知名 --only → exit 2（用法错误语义）。"""
    proc = _run_bench(["--only", "B9"])
    assert proc.returncode == 2
    assert "未知套件名" in proc.stderr.decode("utf-8", "replace")


def test_bench_subset_only_runs_requested():
    """--only 子集：只跑指定套件；全绿则 exit 0。"""
    proc = _run_bench(["--only", "B4,B6"])
    assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")[-2000:]
    payload = _parse_report(proc.stdout)
    assert {s["suite"] for s in payload["suites"]} == {"B4", "B6"}


def test_bench_empty_denominator_not_enabled():
    """空分母 = not_enabled + exit 1（不冒充通过；plan/04 §5.2）。

    直接消费套件函数层（构造空真值集场景；端到端形态由探活测试覆盖）。
    """
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    try:
        import bench as bench_mod

        result = bench_mod._review_not_dead_suite(
            "BX", set(), {}, {"should_cover": 3}
        )
        assert result.passed is False
        assert result.not_enabled is True
    finally:
        sys.path.pop(0)


def test_bench_b4_rule_driven_reverse_samples(bench_green):
    """B4 断言数含反向样例（每规则多状态 × 多 host），正向=规则数。"""
    _, report = bench_green
    b4 = [s for s in report["suites"] if s["suite"] == "B4"][0]
    ruleset = json.loads(
        (REPO_ROOT / "data" / "rules" / "ruleset.json").read_text(encoding="utf-8")
    )
    enabled = len(ruleset["degrade_rules"])  # 仓库正本全 verified（M1 冻结）
    assert b4["metrics"]["enabled_rules"] == enabled
    # 反向样例体量：assertions 明显大于正向规则数（全组合展开）
    assert b4["metrics"]["assertions"] > enabled * 10

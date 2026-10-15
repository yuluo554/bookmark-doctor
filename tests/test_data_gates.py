"""M1 数据资产守门测试。

- 锚点硬门（K4）预览：ruleset 每条规则的 anchor 必须解析到
  ``check_status=verified`` 的观测；pending/缺锚点 → 不生效 + 原因列出；
  另含"pending 观测不得支撑任何规则"的反向断言（B站/掘金 pending 差异登记）；
- 冻结产物位级门（K5）：两个生成器 ``--check`` 必须全绿（子进程真跑）；
- data/** 无 CR 门：EOL 归一化不得改写冻结区字节（.gitattributes data/** -text）。
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RULESET_PATH = REPO_ROOT / "data" / "rules" / "ruleset.json"
OBSERVATIONS_PATH = REPO_ROOT / "data" / "measurements" / "observations.json"
OBSERVATIONS_MD_PATH = REPO_ROOT / "data" / "measurements" / "observations.md"
DATA_DIR = REPO_ROOT / "data"
TOOLS_DIR = REPO_ROOT / "tools"


def _load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _ruleset_loader_preview(ruleset, observations):
    """锚点硬门预览 loader（M3 正式引擎前的最小实现）。

    返回 (enabled_rules, disabled)：disabled 每项带规则 id 与原因。
    """
    by_id = {obs["id"]: obs for obs in observations["observations"]}
    enabled, disabled = [], []
    for rule in ruleset["degrade_rules"]:
        anchor = rule.get("anchor") or {}
        obs_id = anchor.get("observation_id")
        obs = by_id.get(obs_id)
        if obs is None:
            disabled.append({"id": rule["id"], "reason": "anchor_missing", "observation_id": obs_id})
        elif obs["check_status"] != "verified":
            disabled.append(
                {
                    "id": rule["id"],
                    "reason": "anchor_not_verified",
                    "observation_id": obs_id,
                    "check_status": obs["check_status"],
                }
            )
        else:
            enabled.append(rule)
    return enabled, disabled


def test_anchor_gate_all_rules_enabled():
    ruleset = _load_json(RULESET_PATH)
    observations = _load_json(OBSERVATIONS_PATH)
    assert ruleset["degrade_rules"], "ruleset 不应没有规则"
    enabled, disabled = _ruleset_loader_preview(ruleset, observations)
    assert disabled == [], "存在锚点未通过的规则: %s" % disabled
    assert len(enabled) == len(ruleset["degrade_rules"])


def test_pending_observations_support_no_rule():
    """pending 观测（B站/掘金差异登记）不得被任何规则引用（K4 反向断言）。"""
    ruleset = _load_json(RULESET_PATH)
    observations = _load_json(OBSERVATIONS_PATH)
    pending_ids = {
        obs["id"]
        for obs in observations["observations"]
        if obs["check_status"] != "verified"
    }
    assert pending_ids, "台账应存在 pending 差异登记（诚实口径）"
    for rule in ruleset["degrade_rules"]:
        used = rule["anchor"]["observation_id"]
        assert used not in pending_ids, "规则 %s 引用了 pending 观测 %s" % (rule["id"], used)


def test_anchor_gate_rejects_pending_in_synthetic_case():
    """锚点硬门可证伪性：构造 pending 锚点 → 预览 loader 必须判不生效并给出原因。"""
    ruleset = _load_json(RULESET_PATH)
    observations = _load_json(OBSERVATIONS_PATH)
    pending_id = next(
        obs["id"]
        for obs in observations["observations"]
        if obs["check_status"] == "pending"
    )
    synthetic = {
        "degrade_rules": [
            {
                "id": "R-SYNTHETIC",
                "anchor": {"observation_id": pending_id, "check_status": "verified"},
            },
            {
                "id": "R-SYNTHETIC-NO-ANCHOR",
                "anchor": {"observation_id": "OBS-00000000-not-exist", "check_status": "verified"},
            },
        ]
    }
    enabled, disabled = _ruleset_loader_preview(synthetic, observations)
    assert enabled == []
    reasons = {item["id"]: item["reason"] for item in disabled}
    assert reasons["R-SYNTHETIC"] == "anchor_not_verified"
    assert reasons["R-SYNTHETIC-NO-ANCHOR"] == "anchor_missing"


def _run_generator(script):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(script), "--check"],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out = (proc.stdout + proc.stderr).decode("utf-8", "replace")
    return proc.returncode, out


def test_gen_ruleset_check_bit_identical():
    code, out = _run_generator(TOOLS_DIR / "gen_ruleset.py")
    assert code == 0, "gen_ruleset --check 未通过:\n%s" % out


def test_gen_fixtures_check_bit_identical():
    code, out = _run_generator(TOOLS_DIR / "gen_fixtures.py")
    assert code == 0, "gen_fixtures --check 未通过:\n%s" % out


def test_data_files_have_no_cr():
    """data/** 全部文件不得含 CR（冻结区字节保护；.gitattributes 已标 -text）。"""
    bad = []
    for path in sorted(DATA_DIR.rglob("*")):
        if not path.is_file():
            continue
        if b"\r" in path.read_bytes():
            bad.append(str(path.relative_to(REPO_ROOT)))
    assert bad == [], "data/ 下含 CR 的文件: %s" % bad


def test_observation_ledger_sha256_registered():
    """台账 sha256 登记闭环（plan/05 §2）：两份正本的哈希登记在
    data/measurements/checksums.txt（sha256sum 格式），测试实算并断言一致；
    台账变更 → 测试红 → 重算登记（同提交内完成）。checksums.txt 自身不在
    登记范围（文件含自身哈希永不收敛的自指问题）。"""
    ck_path = OBSERVATIONS_MD_PATH.parent / "checksums.txt"
    assert ck_path.exists(), "缺少 data/measurements/checksums.txt"
    registered = {}
    for line in ck_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        digest, _, name = line.partition("  ")
        digest = digest.strip()
        name = name.strip().replace("\\", "/")
        assert re.fullmatch(r"[0-9a-f]{64}", digest), "checksums.txt 哈希格式异常: %r" % line
        registered[name] = digest
    assert set(registered) == {"data/measurements/observations.json", "data/measurements/observations.md"}, (
        "checksums.txt 登记文件集不符: %s" % sorted(registered)
    )
    for name, digest in sorted(registered.items()):
        path = REPO_ROOT / name
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == digest, (
            "%s 的 sha256 登记值漂移：登记 %s，实算 %s（重算登记后同提交落盘）"
            % (name, digest, actual)
        )

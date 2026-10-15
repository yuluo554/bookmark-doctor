"""ruleset.json 加载 + 锚点硬门（M3 正式引擎）。

规格出处：plan/03 §9（单点口径）、plan/04 §2.3（锚点硬门）、HANDOFF-M2 待办 #2。

职责：
- 从仓库正本读取 ruleset.json（``--rules`` 可覆盖）与观测台账
  （data/measurements/observations.json）；
- 锚点硬门（K4，判定顺序与 M1 预览 loader / tests/test_data_gates.py 一致——
  先解析观测台账，再过滤规则）：每条 ``degrade_rules`` 规则的
  ``anchor.observation_id`` 必须解析到台账中 ``check_status=verified`` 的观测；
  否则该规则**拒绝加载**，连同原因进"未启用清单"；
- "未启用清单"必须随每次 check 运行输出（stderr + check.json 汇总）——
  防"承诺可追溯、实际静默照判"（plan/04 §2.3）。

本模块不含任何探测数值 / 平台主机名字面量（零字面量门禁，plan/03 §9）。
"""

import json
from pathlib import Path

RULESET_REL = Path("data") / "rules" / "ruleset.json"
OBSERVATIONS_REL = Path("data") / "measurements" / "observations.json"

# 锚点硬门原因码（与 M1 预览 loader 同名，测试锁定）
REASON_ANCHOR_MISSING = "anchor_missing"
REASON_ANCHOR_NOT_VERIFIED = "anchor_not_verified"


class RulesetError(Exception):
    """规则包/台账文件级失败（不可读/坏 JSON）——CLI 归一 exit 2，不落半成品。"""


def load_ruleset(repo_root, rules_path=None):
    """读取 ruleset（``rules_path`` 覆盖位；缺省仓库正本）。

    不可读/坏 JSON → RulesetError（文件级失败，CLI exit 2）。
    """
    path = Path(rules_path) if rules_path else Path(repo_root) / RULESET_REL
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RulesetError("规则包不可用 %s: %s" % (path, exc))


def load_observations(repo_root):
    """读取观测台账正本（锚点硬门判定顺序第一步：先台账，K4）。

    不可读/坏 JSON → RulesetError。
    """
    path = Path(repo_root) / OBSERVATIONS_REL
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RulesetError("观测台账不可用 %s: %s" % (path, exc))


def apply_anchor_gate(ruleset, observations):
    """锚点硬门 → (enabled_rules, disabled)。

    disabled 每项：{"id", "reason", "observation_id", "check_status"?}——
    结构与 tests/test_data_gates.py 的 M1 预览 loader 一致（不得分叉语义）。
    """
    by_id = {}
    for obs in observations.get("observations", []):
        by_id[obs.get("id")] = obs
    enabled, disabled = [], []
    for rule in ruleset.get("degrade_rules", []):
        anchor = rule.get("anchor") or {}
        obs_id = anchor.get("observation_id")
        obs = by_id.get(obs_id)
        if obs is None:
            disabled.append(
                {"id": rule["id"], "reason": REASON_ANCHOR_MISSING, "observation_id": obs_id}
            )
        elif obs.get("check_status") != "verified":
            disabled.append(
                {
                    "id": rule["id"],
                    "reason": REASON_ANCHOR_NOT_VERIFIED,
                    "observation_id": obs_id,
                    "check_status": obs.get("check_status"),
                }
            )
        else:
            enabled.append(rule)
    return enabled, disabled


def load_effective_rules(repo_root, rules_path=None):
    """一步到位：读 ruleset + 台账 → 过锚点硬门 → (ruleset, enabled_rules, disabled)。

    ruleset / 台账正本不可读或坏 JSON → RulesetError（文件级失败 → CLI exit 2）。
    """
    ruleset = load_ruleset(repo_root, rules_path)
    observations = load_observations(repo_root)
    enabled, disabled = apply_anchor_gate(ruleset, observations)
    return ruleset, enabled, disabled

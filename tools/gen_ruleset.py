"""生成 / 校验 data/rules/ruleset.json（冻结产物，禁手改）。

纪律（plan/05 §3、既定口径 K3/K4/K5）：
- 全部阈值与规则数值只在本文件定义一次，输出为 ruleset.json 单点；
- 无系统时钟、无随机数、输出键经显式 sort，写盘 UTF-8 字节、LF 行尾；
- ``--check``：重新生成到内存 → 与仓库现有文件逐字节比对，不一致 exit 1；
- 每条降级规则的锚点必须在 data/measurements/observations.json 解析到
  ``check_status=verified`` 的观测，否则生成阶段即失败（K4 锚点硬门在生成端前置）；
- ruleset 版本号 = 内容哈希派生（对除 version 外的规范负载取 sha256 前 12 位）。

用法（仓库根运行）：
    PYTHONPATH=src py -X utf8 tools/gen_ruleset.py           # 生成/覆写
    PYTHONPATH=src py -X utf8 tools/gen_ruleset.py --check   # 位级一致性校验
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from bookmark_doctor._encoding import ensure_utf8_stdio

REPO_ROOT = Path(__file__).resolve().parent.parent
RULESET_PATH = REPO_ROOT / "data" / "rules" / "ruleset.json"
OBSERVATIONS_PATH = REPO_ROOT / "data" / "measurements" / "observations.json"

SCHEMA = "bookmark-doctor.ruleset/1"
REVISION = 1

# ---- 单点数值口径（只在此处定义；引擎/基准/测试/文档只引用不重写） ----

PROBE = {
    "timeout_s": 10,
    "retry_max": 1,
    "delay_s": 0.5,
    "redirect_max": 5,
    "user_agent": "BookmarkDoctor-Observation/0.1 (single-shot status check; +local measurement)",
}

# 每条规则的 anchor.observation_id 必须解析到 verified 观测（生成时校验）
DEGRADE_RULES = [
    {
        "id": "R-ZHIHU-403",
        "match": {"host_suffix": "zhihu.com", "http_status": 403},
        "disposition": "review",
        "reason": "http_403_botguard",
        "note": "非浏览器请求返回 403（bot 拦截）；浏览器可正常打开，反爬非失效",
        "anchor": {"observation_id": "OBS-20261015-zhihu-question-403", "check_status": "verified"},
    },
    {
        "id": "R-ZHIHU-302",
        "match": {"host_suffix": "zhihu.com", "http_status": 302},
        "disposition": "review",
        "reason": "http_302_login_redirect",
        "note": "非登录态访问 302 → /signin 登录跳转；跟随终态为登录页非内容页，不判失效（首跳/终态匹配语义 M3 冻结）",
        "anchor": {"observation_id": "OBS-20261015-zhihu-home-302", "check_status": "verified"},
    },
    {
        "id": "R-WEIBO-302",
        "match": {"host_suffix": "weibo.com", "http_status": 302},
        "disposition": "review",
        "reason": "http_302_visitor_risk",
        "note": "非登录态访问 302 → passport visitor 风控跳转链；跟随终态为访客页非原页内容，不判失效（跳转链含动态 _rand，运行时以实际链为准）",
        "anchor": {"observation_id": "OBS-20261015-weibo-home-302-visitor", "check_status": "verified"},
    },
    {
        "id": "R-CSDN-521",
        "match": {"host_suffix": "csdn.net", "http_status": 521},
        "disposition": "review",
        "reason": "cdn_blocked",
        "note": "非浏览器请求返回 521（CDN 反爬拦截）；浏览器可正常打开，非失效",
        "anchor": {"observation_id": "OBS-20261015-csdn-blog-521", "check_status": "verified"},
    },
]

# B站 301/302、掘金 521 观测为 pending → 不设规则（K4：锚点 pending 不生效）。
# 复核升级 verified 后，在此追加规则并整目录重生成。

TRACKED_QUERY_PARAMS = {
    "exact": ["share_token", "spm", "scm", "fbclid", "gclid", "igshid"],
    "prefixes": ["utm_", "share_"],
}

AGING = {
    "tiers_days": [365, 730, 1095],
}

SIMILARITY = {
    "threshold": 0.9,
}


def _canonical_bytes(payload) -> bytes:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, separators=(",", ": "))
    return (text + "\n").encode("utf-8")


def build_ruleset() -> bytes:
    observations = json.loads(OBSERVATIONS_PATH.read_text(encoding="utf-8"))
    by_id = {obs["id"]: obs for obs in observations["observations"]}

    for rule in DEGRADE_RULES:
        anchor = rule["anchor"]
        obs = by_id.get(anchor["observation_id"])
        if obs is None:
            raise SystemExit("锚点解析失败: %s 不在 observations.json" % anchor["observation_id"])
        if obs["check_status"] != "verified":
            raise SystemExit(
                "锚点未复核: %s check_status=%s（pending 不支撑规则生效）"
                % (anchor["observation_id"], obs["check_status"])
            )
        anchor["check_status"] = obs["check_status"]

    payload = {
        "schema": SCHEMA,
        "revision": REVISION,
        "probe": PROBE,
        "degrade_rules": DEGRADE_RULES,
        "tracked_query_params": TRACKED_QUERY_PARAMS,
        "aging": AGING,
        "similarity": SIMILARITY,
    }
    version = hashlib.sha256(_canonical_bytes(payload)).hexdigest()[:12]
    payload["version"] = version
    return _canonical_bytes(payload)


def main(argv=None) -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="生成 / 校验 data/rules/ruleset.json（冻结产物）")
    parser.add_argument("--check", action="store_true", help="重新生成并与现有文件逐字节比对（不覆写）")
    args = parser.parse_args(argv)

    data = build_ruleset()
    if args.check:
        if not RULESET_PATH.exists():
            print("[gen_ruleset] 缺少 %s" % RULESET_PATH, file=sys.stderr)
            return 1
        current = RULESET_PATH.read_bytes()
        if current != data:
            print("[gen_ruleset] 位级不一致：ruleset.json 与生成器输出不符（禁手改，请整目录重生成）", file=sys.stderr)
            return 1
        print("[gen_ruleset] --check 通过：位级一致")
        return 0

    RULESET_PATH.write_bytes(data)
    print("[gen_ruleset] 已写入 %s" % RULESET_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

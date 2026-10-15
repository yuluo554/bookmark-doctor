"""内置基准 runner（M4）——植入真值对账 + 规则驱动断言 + 探活。

规格出处：plan/04 §5.2、plan/05 §4、HANDOFF-M4 待办。

两条独立层（plan/04 §5.2）：
- **样本驱动**：合成集 set-1 真喂引擎（parse → probe → classify / dedupe），
  与 truth.json 对账（不是"比对两份预计算答案"）；
- **规则驱动**（B4）：不读真值库——遍历 ruleset 每条生效规则与通用映射
  全组合喂 classify，断言"该命中/不该命中"（含反向样例：不同 host / 不同
  状态不得命中）。

套件（plan/05 §4.2）：
  B1 分类·反爬类   样本驱动：403/302/521 → review，误判 dead 计数
  B2 分类·不可达类 样本驱动：DNS 失败/超时 → review，误判 dead 计数
  B3 分类·死链类   样本驱动：404/410 → dead，漏判计数
  B4 分类·规则驱动 规则驱动：规则×通用映射全组合 + 反向样例
  B5 去重类        样本驱动：真值重复组全合并且无误合并
  B6 一致性        样本驱动：同输入两次运行 check.json 逐字节一致

门槛（manifest 下发，门槛是数据非代码）：
  false_dead = 0 硬门（B1/B2）；命中率 ≥ manifest.coverage 的 should_cover
  对应件数门槛；B4 100% 断言；B5 合并率 100% + 误合并 0；B6 位级一致。
  manifest 缺门槛节 → 配置错误 exit 2。

mock 重写机制（plan/05 §4.3）：
  *.mock.invalid 主机运行时解析到 127.0.0.1 + 动态端口（对照表 =
  manifest.mock_host_scenarios → mock 站点路径场景）；unreachable →
  未监听端口；hang → /hang 挂起路径。端口不进任何冻结产物字节。
  探测前断言重写后 URL 全部 loopback，任一真实外网 URL → exit 2。

退出码三语义（锁进测试）：
  0 = 全部套件达标；1 = 任一未达标（含空分母 not_enabled——不冒充通过）；
  2 = 用法错误 / 未知名 --only / 数据资产缺失（不落半成品）。

探活（可证伪）：--inject-defect <name> 注入缺陷（如 403 通用映射改 dead），
基准必须 exit 1——作为常驻测试（tests/test_bench.py 端到端打真实入口）。

用法（仓库根运行）：
    PYTHONPATH=src py -X utf8 tools/bench.py [--only B1,B3] [--inject-defect 403-dead]
    PYTHONPATH=src py -X utf8 tools/bench.py --report out.json   # 指标落盘
全程离线（仅 loopback mock），断网可复跑。
"""

import argparse
import json
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from bookmark_doctor._encoding import ensure_utf8_stdio

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

FIXTURES_DIR = REPO_ROOT / "data" / "fixtures" / "set-1"
LOOPBACK_HOST = "127.0.0.1"
# manifest 覆盖节键名（门槛是数据非代码：读取自 manifest，不在本文件内联门槛值）
COVERAGE_KEYS = ("review_not_dead", "unreachable_not_dead", "dead_hit", "duplicate_merge")
SUITE_IDS = ("B1", "B2", "B3", "B4", "B5", "B6")
# 探活缺陷清单（--inject-defect 白名单；未知名 exit 2）
DEFECTS = ("403-dead",)


# ---------------------------------------------------------------------------
# mock 站点（进程内，仅 loopback；响应表与 tools/mock_site.py 同语义）
# ---------------------------------------------------------------------------


class _MockHandler(BaseHTTPRequestHandler):
    """按路径脚本化响应；hang 路径阻塞至客户端断开。

    路由（bench 专用命名空间段防跨主机去重键碰撞——不同 mock 主机的
    场景码可能相同，如 200 场景的 alive-page 与 content-page；路径必须
    保留主机可区分性，否则去重对账失真）：
    - ``/b<i>/status/<code>`` → 对应状态码（i = 主机命名空间序号）；
    - ``/b<i>/hang`` → 挂起（读取超时场景）。
    """

    def _respond(self, code, extra_headers=None):
        body = ("mock: %d\n" % code).encode("ascii")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=ascii")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0].strip("/")
        parts = path.split("/") if path else []
        # 原路径语义段重写：/b<i>/<orig>/status/<code>（去重键尾段保留原页 ID）
        # 或 /b<i>/<orig>/hang（挂起）。场景段取倒数第二段。
        if len(parts) >= 3 and parts[-2] == "status" and parts[-1].isdigit():
            self._respond(int(parts[-1]))
            return
        if len(parts) >= 3 and parts[-1] == "hang":
            try:
                while self.rfile.readline(64):
                    pass
            except (ConnectionError, OSError):
                pass
            return
        self._respond(404)

    do_HEAD = do_GET

    def log_message(self, fmt, *args):  # 静默：不刷屏，避免输出时序依赖
        pass


def start_mock_server():
    """起 mock 站点 → (base_url, port)。端口运行时分配，不进冻结产物。"""
    server = ThreadingHTTPServer((LOOPBACK_HOST, 0), _MockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, "http://%s:%d" % (LOOPBACK_HOST, server.server_address[1])


# ---------------------------------------------------------------------------
# mock 主机重写（plan/05 §4.3）
# ---------------------------------------------------------------------------


def build_host_map(manifest, mock_base, unreachable_port):
    """manifest.mock_host_scenarios + mock base → {原 host: (path_prefix, scenario)}。

    - 200/404/410/403/302/521 等 HTTP 场景 → mock 站点（命名空间路径前缀
      ``/b<i>`` + 场景码，重写为 ``/b<i>/status/<scenario>``）；
    - hang → mock 站点（重写为 ``/b<i>/hang`` 挂起路径，触发读取超时）；
    - unreachable → 127.0.0.1 上**未监听**的端口（拒绝连接场景）。
    命名空间段 i 按主机名排序分配——不同场景主机即使场景码相同（如两个
    200 场景主机）路径也互异，保住"不同源站不合并"的对账前提。
    """
    host_map = {}
    namespace = 0
    for host, scenario in sorted(manifest.get("mock_host_scenarios", {}).items()):
        if scenario == "unreachable":
            host_map[host] = (None, scenario, "%s:%d" % (LOOPBACK_HOST, unreachable_port))
        else:
            namespace += 1
            prefix = "/b%d" % namespace
            host_map[host] = (prefix, scenario, "%s:%d" % (LOOPBACK_HOST, mock_base.port))
    return host_map


def rewrite_url(url, host_map):
    """URL 原文的 *.mock.invalid host → loopback mock 场景（场景驱动重写）。

    - host → loopback host:port（mock 站点 / unreachable 端口）；
    - scheme 同步 http 化：mock 站点仅 HTTP（loopback 无 TLS）——保留 https
      会全部落 tls_error → review，基准失真；
    - HTTP 场景路径改写为 ``/<ns>/status/<scenario>``（场景码由 mock 响应表
      提供；命名空间段 = 原路径首段，保住主机与页内区分度——同场景码不同
      主机不塌缩成同键，同主机不同页也不塌缩）；hang 场景改写为
      ``/<ns>/hang``（挂起路径）。
    端口/路径映射运行时构造，不进任何冻结产物字节。
    """
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    entry = host_map.get(host)
    if entry is None:
        return url
    prefix, scenario, netloc = entry
    # 完整原路径前插命名空间段（主机区分度）+ 后缀场景段（页 ID 保留在
    # 中段——同场景码不同主机、同主机不同页的去重键都不塌缩，B5 对账前提）
    orig = "/".join(seg for seg in parts.path.split("/") if seg) or "root"
    if scenario == "hang":
        path = "%s/%s/hang" % (prefix, orig)
    elif scenario == "unreachable":
        path = parts.path  # 场景主机在未监听端口——连接即拒，路径无语义
    else:
        path = "%s/%s/status/%s" % (prefix, orig, scenario)
    return urlunsplit(("http", netloc, path, parts.query, parts.fragment))


def assert_all_loopback(urls):
    """基准防偷跑外网：URL host 必须为 loopback 或 RFC 2606 保留域（.invalid）。

    *.mock.invalid 已被重写为 loopback；*.invalid 假域是刻意的 DNS 失败场景
    （保留域永不解析，离线可复现）。其余真实域名 → BenchConfigError。
    """
    for url in urls:
        host = _url_host(url)
        if not _is_loopback(host) and not host.endswith(".invalid"):
            raise BenchConfigError("基准 URL 集含非 loopback/非保留域（禁止偷跑外网）: %s" % url)


def _url_host(url):
    from urllib.parse import urlsplit

    return (urlsplit(url).hostname or "").lower()


def _url_port(url):
    from urllib.parse import urlsplit

    return urlsplit(url).port


def _is_loopback(host):
    if host == "::1" or host.endswith(".localhost"):
        return True
    parts = host.split(".")
    return len(parts) == 4 and parts[0] == "127"


def _find_free_port():
    # 找一个当前未监听的端口（unreachable 场景用；有极小竞态窗口，见 _assert_unreachable）
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((LOOPBACK_HOST, 0))
        return sock.getsockname()[1]


def _assert_unreachable(port):
    """确认端口确实拒绝连接（unreachable 场景的前提，防端口复用假象 E-15）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        code = sock.connect_ex((LOOPBACK_HOST, port))
    if code == 0:
        raise BenchConfigError("端口 %d 实际在监听——unreachable 场景前提不成立" % port)


# ---------------------------------------------------------------------------
# 配置错误（文件级失败 → exit 2）
# ---------------------------------------------------------------------------


class BenchConfigError(Exception):
    """基准数据资产缺失/非法（manifest 门槛缺失、fixture 不可读等）→ exit 2。"""


# ---------------------------------------------------------------------------
# 探活缺陷注入
# ---------------------------------------------------------------------------


def apply_defect(generic_fn, defect):
    """注入探活缺陷 → 新的通用映射函数（原函数不被修改）。

    ``403-dead``：把 403 通用映射改成 dead——B1 必须报未达标（false_dead 硬门红）。
    """
    if defect == "403-dead":

        def _poisoned(probe_record):
            verdict, reason = generic_fn(probe_record)
            if reason == "http_4xx_blocked" and probe_record.get("http_status") == 403:
                return "dead", reason
            return verdict, reason

        return _poisoned
    raise BenchConfigError("未知探活缺陷: %r（可用: %s）" % (defect, ", ".join(DEFECTS)))


# ---------------------------------------------------------------------------
# 引擎装配（真喂引擎：parse → probe → classify / dedupe）
# ---------------------------------------------------------------------------


def load_fixtures():
    """读合成集 + truth + manifest（不可读 → BenchConfigError）。"""
    paths = {
        "chrome": FIXTURES_DIR / "bookmarks.chrome.json",
        "netscape": FIXTURES_DIR / "bookmarks.netscape.html",
        "truth": FIXTURES_DIR / "truth.json",
        "manifest": FIXTURES_DIR / "manifest.json",
    }
    try:
        chrome_obj = json.loads(paths["chrome"].read_text(encoding="utf-8"))
        netscape_text = paths["netscape"].read_text(encoding="utf-8")
        truth = json.loads(paths["truth"].read_text(encoding="utf-8"))
        manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BenchConfigError("合成集不可读 %s: %s" % (FIXTURES_DIR, exc))
    return chrome_obj, netscape_text, truth, manifest


def load_ruleset():
    """读 ruleset 正本 + 锚点硬门 → (ruleset, enabled, disabled)。"""
    from bookmark_doctor.ruleset import load_effective_rules

    return load_effective_rules(REPO_ROOT, None)


def build_uir(chrome_obj, netscape_text):
    """真喂解析引擎（不走 import CLI——bench 直接消费解析器，同契约）。"""
    from bookmark_doctor.model import build_bookmarks, load_chrome_epoch_delta
    from bookmark_doctor.parse.chrome_json import parse_chrome_json
    from bookmark_doctor.parse.netscape import parse_netscape

    epoch = load_chrome_epoch_delta(REPO_ROOT)
    bookmarks = []
    bookmarks.extend(build_bookmarks(parse_chrome_json(chrome_obj, epoch), "bookmarks.chrome.json"))
    bookmarks.extend(build_bookmarks(parse_netscape(netscape_text), "bookmarks.netscape.html"))
    return bookmarks


def run_probe_and_classify(bookmarks, ruleset, effective_rules, host_map, probe_cfg_overrides=None):
    """重写 URL → loopback 断言 → 真喂探测 + 分类（复刻 CLI check 流水线语义）。

    返回 (check_payload, results_by_url)。分类函数可被探活缺陷包装
    （``classify_fn`` 经 ``--inject-defect`` 换入）。
    """
    from bookmark_doctor.classify import classify, generic_verdict
    from bookmark_doctor.probe import probe_bookmarks

    probe_cfg = dict(ruleset["probe"])
    if probe_cfg_overrides:
        probe_cfg.update(probe_cfg_overrides)

    id_by_url = {}
    urls = []
    for bm in bookmarks:
        rewritten = rewrite_url(bm["url"], host_map)
        id_by_url.setdefault(rewritten, []).append(bm["id"])
        urls.append(rewritten)
    assert_all_loopback(urls)

    classify_fn = classify
    if bench_state.defect:
        poisoned_generic = apply_defect(generic_verdict, bench_state.defect)

        def classify_fn(record, rules):  # noqa: F811 — 探活包装（缺陷注入路径）
            hits = [rule for rule in rules if _rule_matches(record, rule)]
            if hits:
                return classify(record, rules)
            verdict, reason = poisoned_generic(record)
            return {"verdict": verdict, "reason": reason, "rule_id": None, "conflict": None}

    # 唯一目标探测：重写后同 URL（跨来源重复收藏）只探一次，结果扇回
    # 全部同名 URL 书签——语义不变（同 URL 同响应），省去重复挂起/不可达
    # 场景的成倍探测耗时。
    unique_urls = sorted(set(urls))
    unique_records = probe_bookmarks(unique_urls, probe_cfg)
    record_by_url = {r["url"]: r for r in unique_records}
    records = [record_by_url[url] for url in urls]
    results = []
    for record in records:
        outcome = classify_fn(record, effective_rules)
        results.append(
            {
                "id": id_by_url[record["url"]][0],
                "url": record["url"],
                "final_url": record["final_url"],
                "redirect_chain": record["redirect_chain"],
                "http_status": record["http_status"],
                "error_class": record["error_class"],
                "verdict": outcome["verdict"],
                "reason": outcome["reason"],
                "rule_id": outcome["rule_id"],
                "conflict": outcome["conflict"],
            }
        )
    payload = {
        "schema": "bookmark-doctor.check-v1",
        "summary": {"total": len(results)},
        "results": results,
    }
    return payload, {r["url"]: r for r in results}


def _rule_matches(record, rule):
    from bookmark_doctor.classify import match_rule

    return match_rule(record, rule)


# ---------------------------------------------------------------------------
# 套件结果记账
# ---------------------------------------------------------------------------


class SuiteResult(object):
    def __init__(self, suite_id, metrics, passed, not_enabled=False, detail=None):
        self.suite_id = suite_id
        self.metrics = metrics
        self.passed = passed
        self.not_enabled = not_enabled
        self.detail = detail

    def as_dict(self):
        return {
            "suite": self.suite_id,
            "passed": self.passed,
            "not_enabled": self.not_enabled,
            "metrics": self.metrics,
            "detail": self.detail,
        }


def _rate_hits(hits, denominator):
    """命中率（分母 0 → None，由调用方按 not_enabled 处理）。"""
    if denominator == 0:
        return None
    return hits / denominator


def _threshold_from_manifest(manifest, key):
    """manifest 覆盖节取门槛（should_cover）；缺失/非法 → BenchConfigError。

    门槛是数据非代码：不在基准里内联默认值（plan/05 §4.2）。
    """
    coverage = manifest.get("coverage")
    if not isinstance(coverage, dict):
        raise BenchConfigError("manifest.coverage 缺失（门槛必须由 manifest 下发）")
    entry = coverage.get(key)
    if not isinstance(entry, dict) or not isinstance(entry.get("should_cover"), int):
        raise BenchConfigError("manifest.coverage.%s.should_cover 缺失（门槛缺失）" % key)
    if entry["should_cover"] < 0:
        raise BenchConfigError("manifest.coverage.%s.should_cover 非法（负数）" % key)
    return entry


# ---------------------------------------------------------------------------
# 样本驱动套件（B1/B2/B3/B5/B6）
# ---------------------------------------------------------------------------


def suite_b1_anti_crawl(truth_obj, results_by_id, manifest):
    """B1：反爬类（403/302/521）应 review，不得 dead。门槛 = manifest review_not_dead。"""
    entry = _threshold_from_manifest(manifest, "review_not_dead")
    ids = set(truth_obj["expect"]["review_reason_class"]["anti_crawl"])
    return _review_not_dead_suite("B1", ids, results_by_id, entry)


def suite_b2_unreachable(truth_obj, results_by_id, manifest):
    """B2：不可达类（DNS/超时）应 review，不得 dead。门槛 = manifest unreachable_not_dead。"""
    entry = _threshold_from_manifest(manifest, "unreachable_not_dead")
    ids = set(truth_obj["expect"]["review_reason_class"]["network_unreachable"])
    ids |= set(truth_obj["expect"]["review_reason_class"]["dns_failure"])
    return _review_not_dead_suite("B2", ids, results_by_id, entry)


def _review_not_dead_suite(suite_id, ids, results_by_id, entry):
    if not ids:
        return SuiteResult(suite_id, {"hits": 0, "false_dead": 0, "rate": None},
                           passed=False, not_enabled=True,
                           detail="空分母：真值集无该类样本（not_enabled，不冒充通过）")
    hits = sum(1 for i in ids if results_by_id.get(i, {}).get("verdict") == "review")
    false_dead = sum(1 for i in ids if results_by_id.get(i, {}).get("verdict") == "dead")
    metrics = {
        "total": len(ids),
        "hits": hits,
        "false_dead": false_dead,
        "rate": _rate_hits(hits, len(ids)),
        "threshold": entry["should_cover"],
    }
    passed = false_dead == 0 and hits >= entry["should_cover"]
    return SuiteResult(suite_id, metrics, passed=passed)


def suite_b3_dead(truth_obj, results_by_id, manifest):
    """B3：死链类（404/410）应 dead，漏判（alive/review）计数。门槛 = manifest dead_hit。"""
    entry = _threshold_from_manifest(manifest, "dead_hit")
    ids = set(truth_obj["expect"]["dead"])
    if not ids:
        return SuiteResult("B3", {"hits": 0, "missed": 0, "rate": None},
                           passed=False, not_enabled=True,
                           detail="空分母：真值集无死链样本（not_enabled）")
    hits = sum(1 for i in ids if results_by_id.get(i, {}).get("verdict") == "dead")
    missed = len(ids) - hits
    metrics = {
        "total": len(ids),
        "hits": hits,
        "missed": missed,
        "rate": _rate_hits(hits, len(ids)),
        "threshold": entry["should_cover"],
    }
    return SuiteResult("B3", metrics, passed=hits >= entry["should_cover"])


def suite_b5_dedupe(bookmarks, check_payload, truth_obj, ruleset, manifest, host_map):
    """B5：真值重复组全部合并且无误合并。门槛 = manifest duplicate_merge。"""
    from bookmark_doctor.dedupe import build_duplicate_groups

    entry = _threshold_from_manifest(manifest, "duplicate_merge")
    tracked = ruleset.get("tracked_query_params") or {}
    groups = build_duplicate_groups(
        bookmarks, tracked, check_payload.get("results", [])
    )

    # 真值成员 URL（原文）→ 去重键=normalize；真值组以 expect_merge_to 为组标识。
    # 植入的重复组均为 *.mock.invalid 原文形态（未重写即可比较——
    # normalize 比较键与端口无关的成员间相对关系成立：成员经同一 host_map
    # 重写后比较键同变。这里用"重写后的书签原文"参与分组，真值成员 URL
    # 同步重写后对账，口径一致）。
    truth_groups = truth_obj["expect"]["duplicate_groups"]

    # 引擎分组视角：{member 原文 URL: group_key}
    engine_group_of = {}
    for group in groups:
        for member in group["members"]:
            engine_group_of[member["url"]] = group["key"]

    merged = 0
    misses = []
    for tgroup in truth_groups:
        members = [rewrite_url(u, host_map) for u in tgroup["members"]]
        keys = {engine_group_of.get(m) for m in members}
        if len(keys) == 1 and None not in keys:
            merged += 1
        else:
            misses.append(tgroup["expect_merge_to"])

    # 误合并：同一引擎组内出现真值归属不同内容键的成员
    # （真值未标记重复的 URL 对若被并组 → 误合并）。以"真值组集合"为参照：
    # 每个引擎组的成员按真值组归属划分，若一个引擎组混合了 ≥2 个真值组（或
    # 混入非真值组 URL）→ 误合并。
    truth_member_urls = set()
    truth_group_index = {}  # 真值组序号 → set(成员重写 URL)
    for idx, tgroup in enumerate(truth_groups):
        rewritten = {rewrite_url(u, host_map) for u in tgroup["members"]}
        truth_group_index[idx] = rewritten
        truth_member_urls |= rewritten
    false_merges = 0
    for group in groups:
        member_urls = {m["url"] for m in group["members"]}
        owning = [i for i, urls in truth_group_index.items() if member_urls & urls]
        non_truth = member_urls - truth_member_urls
        if len(owning) > 1 or (owning and non_truth) or (not owning and len(member_urls) > 1):
            # 多真值组并进一组 / 真值组混入无关 URL / 无真值归属的组（本身就是
            # 引擎自行发现的重复——真值库未植入即属未声明合并，计入误合并）
            false_merges += 1

    total_groups = len(truth_groups)
    if total_groups == 0:
        return SuiteResult("B5", {"merged": 0, "false_merges": false_merges, "rate": None},
                           passed=False, not_enabled=True,
                           detail="空分母：真值集无重复组（not_enabled）")
    metrics = {
        "total": total_groups,
        "merged": merged,
        "missed": misses,
        "false_merges": false_merges,
        "rate": _rate_hits(merged, total_groups),
        "threshold": entry["should_cover"],
    }
    passed = merged >= entry["should_cover"] and false_merges == 0
    return SuiteResult("B5", metrics, passed=passed)


# ---------------------------------------------------------------------------
# B4 规则驱动（不读真值库——遍历规则×通用映射全组合 + 反向样例）
# ---------------------------------------------------------------------------


def _make_record(url, http_status=None, error_class=None):
    return {
        "url": url,
        "final_url": url,
        "redirect_chain": [],
        "http_status": http_status,
        "error_class": error_class,
    }


# 通用映射全组合状态集（HTTP 语义区间取样——每个判定分支至少一个代表码；
# 语义区间集在 classify 内是语义非政策数值，此处按区间取代表码构造断言输入）
_GENERIC_REPRESENTATIVE_STATUSES = (200, 302, 404, 410, 401, 403, 405, 406, 429, 451, 500, 521, 400)
_GENERIC_ERROR_CLASSES = (None, "dns_failure", "read_timeout", "connection_error")

# B4 期望：按 classify 通用映射语义构造期望（规则命中优先；通用映射按区间）。
# 期望不内联政策数值——直接消费通用映射函数本身对"无规则"输入的输出作对账基准：
# 对"不该命中规则的输入"，classify 结果必须等于 generic_verdict 的输出
# （这保证规则不越界改判）；对"该命中"的输入，结果必须来自规则（rule_id 非 None
# 且 verdict/reason 与规则声明一致）。


def suite_b4_rule_driven(ruleset, effective_rules, disabled):
    """B4：遍历每条生效规则 × 通用映射代表组合喂 classify，含反向样例。

    - 正向：规则匹配形态（同 host_suffix + 同状态）→ 必须命中该规则
      （rule_id 一致，verdict/reason = 规则声明）；
    - 反向：不同 host（后缀不匹配 / 近似域名）× 全状态组合 → 不得命中任何规则，
      且结果与通用映射逐字段一致（防"适用域写宽了基准永远绿"）；
    - 同 host 不同状态 → 不得命中（http_status 维度不匹配）。
    规则包无生效规则 → not_enabled（exit 1，不冒充通过）。
    """
    if not effective_rules:
        return SuiteResult(
            "B4",
            {"assertions": 0, "failed": 0, "enabled_rules": 0},
            passed=False,
            not_enabled=True,
            detail=(
                "空分母：无生效规则（disabled=%d：%s）——规则驱动套件 not_enabled"
                % (len(disabled), ",".join(d["id"] for d in disabled) or "无")
            ),
        )

    failures = []
    assertions = 0

    # 反向样例 host 集：与任何 host_suffix 不同、且不做后缀；含近似域名形态
    # （evil-<suffix> 不得命中 <suffix>——_host_matches 的边界语义）
    reverse_hosts = []
    for rule in effective_rules:
        suffix = rule["match"]["host_suffix"]
        reverse_hosts.append("evil-" + suffix)
        reverse_hosts.append("not-" + suffix.split(".", 1)[0] + ".example.invalid")
    reverse_hosts = sorted(set(reverse_hosts))

    for rule in effective_rules:
        suffix = rule["match"]["host_suffix"]
        want_status = rule["match"]["http_status"]
        # 正向：同 host 同状态（error_class 为 None 时才走状态通路）
        for prefix in (rule_host_prefix(suffix),):
            url = "https://%s/path/sample" % prefix
            rec = _make_record(url, http_status=want_status)
            outcome = classify_record(rec, effective_rules)
            assertions += 1
            if outcome.get("rule_id") != rule["id"]:
                failures.append("正向未命中 %s @ %s/%s" % (rule["id"], prefix, want_status))
            elif outcome["verdict"] != rule.get("disposition") or outcome["reason"] != rule.get("reason"):
                failures.append(
                    "正向判定不符 %s: got %s/%s want %s/%s"
                    % (rule["id"], outcome["verdict"], outcome["reason"],
                       rule.get("disposition"), rule.get("reason"))
                )

        # 反向 A：不同 host × 全代表状态 → 不得命中任何规则且等于通用映射
        for host in reverse_hosts:
            for status in _GENERIC_REPRESENTATIVE_STATUSES:
                url = "https://%s/path/sample" % host
                rec = _make_record(url, http_status=status)
                outcome = classify_record(rec, effective_rules)
                expected = generic_only(rec)
                assertions += 1
                if outcome != expected:
                    failures.append(
                        "反向越界命中 %s @ %s/%s: got %s/%s want %s/%s"
                        % (rule["id"], host, status,
                           outcome["verdict"], outcome["reason"],
                           expected["verdict"], expected["reason"])
                    )

        # 反向 B：同 host 不同状态/带错误类 → **本规则**不得命中
        # （同站其他规则合法命中不算越界——断言只针对本规则的适用域）
        for status in _GENERIC_REPRESENTATIVE_STATUSES:
            if status == want_status:
                continue
            url = "https://%s/path/sample" % rule_host_prefix(suffix)
            rec = _make_record(url, http_status=status)
            outcome = classify_record(rec, effective_rules)
            assertions += 1
            if outcome.get("rule_id") == rule["id"]:
                failures.append(
                    "同 host 异状态越界 %s @ %s/%s" % (rule["id"], suffix, status)
                )
        for err in ("dns_failure", "read_timeout"):
            url = "https://%s/path/sample" % rule_host_prefix(suffix)
            rec = _make_record(url, error_class=err)
            outcome = classify_record(rec, effective_rules)
            assertions += 1
            if outcome.get("rule_id") == rule["id"]:
                failures.append("error_class 越界 %s @ %s" % (rule["id"], err))

    return SuiteResult(
        "B4",
        {"assertions": assertions, "failed": len(failures), "enabled_rules": len(effective_rules)},
        passed=not failures,
        detail=None if not failures else "; ".join(failures[:8]),
    )


def rule_host_prefix(suffix):
    """host_suffix → 该后缀下的具体主机（域内子域形态，必命中 _host_matches）。"""
    return "www." + suffix


def classify_record(record, rules):
    from bookmark_doctor.classify import classify

    return classify(record, rules)


def generic_only(record):
    """无规则世界的判定基准（B4 反向样例对账用）。"""
    from bookmark_doctor.classify import generic_verdict

    verdict, reason = generic_verdict(record)
    return {"verdict": verdict, "reason": reason, "rule_id": None, "conflict": None}


# ---------------------------------------------------------------------------
# 探针状态（探活缺陷注入的全局开关——CLI 单次进程内使用）
# ---------------------------------------------------------------------------


class _BenchState(object):
    defect = None


bench_state = _BenchState()


# ---------------------------------------------------------------------------
# B6 一致性（同输入两次运行 check 流水线 → 逐字节一致）
# ---------------------------------------------------------------------------


def suite_b6_consistency(bookmarks, ruleset, effective_rules, host_map):
    """B6：同一输入连跑两次探测+分类流水线 → 结果载荷逐字节一致。"""
    from bookmark_doctor.serialize import serialize_payload

    payload1, _ = run_probe_and_classify(bookmarks, ruleset, effective_rules, host_map)
    payload2, _ = run_probe_and_classify(bookmarks, ruleset, effective_rules, host_map)
    identical = serialize_payload(payload1) == serialize_payload(payload2)
    return SuiteResult(
        "B6",
        {"byte_identical": identical},
        passed=identical,
        detail=None if identical else "两次运行载荷不一致（确定性破坏）",
    )


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def _prune_suites(requested):
    """--only 解析：未知名 → BenchConfigError（exit 2）。"""
    if not requested:
        return list(SUITE_IDS)
    names = [name.strip().upper() for name in requested.split(",") if name.strip()]
    unknown = [name for name in names if name not in SUITE_IDS]
    if unknown:
        raise BenchConfigError("未知套件名 --only %s（可用: %s）" % (",".join(unknown), ",".join(SUITE_IDS)))
    return sorted(set(names))


def run_bench(only=None, defect=None):
    """基准主流程 → (suite_results, host_map)。配置错误抛 BenchConfigError。"""
    bench_state.defect = defect
    suite_ids = _prune_suites(only)

    chrome_obj, netscape_text, truth_obj, manifest = load_fixtures()
    ruleset, effective_rules, disabled = load_ruleset()
    bookmarks = build_uir(chrome_obj, netscape_text)

    # mock：动态端口 + unreachable 端口（前提校验：确实拒绝连接）
    server, mock_base_url = start_mock_server()
    try:
        unreachable_port = _find_free_port()
        _assert_unreachable(unreachable_port)
        mock_base = type("MockBase", (), {"port": _url_port(mock_base_url)})()
        host_map = build_host_map(manifest, mock_base, unreachable_port)

        results = []
        need_check = any(sid in suite_ids for sid in ("B1", "B2", "B3", "B5", "B6"))
        check_payload = None
        results_by_id = None
        if need_check:
            check_payload, results_by_url = run_probe_and_classify(
                bookmarks, ruleset, effective_rules, host_map
            )
            # id 对账：truth id = sha1("html|seq")（gen_fixtures 口径：netscape
            # 源名 "html" + 文件内序）。bench 以同口径重建一份 UIR 取 id↔URL，
            # 再落回重写后的探测结果。
            id_bookmarks = build_id_aliased_uir(chrome_obj, netscape_text)
            results_by_id = {}
            for bm in id_bookmarks:
                rewritten = rewrite_url(bm["url"], host_map)
                record = results_by_url.get(rewritten)
                if record is None:
                    raise BenchConfigError("真值 id %s 的 URL 未在探测结果中: %s" % (bm["id"], bm["url"]))
                results_by_id[bm["id"]] = record
            if len(results_by_id) != len(id_bookmarks):
                raise BenchConfigError("真值 id 对账不完整（id 派生口径漂移？）")

        if "B1" in suite_ids:
            results.append(suite_b1_anti_crawl(truth_obj, results_by_id, manifest))
        if "B2" in suite_ids:
            results.append(suite_b2_unreachable(truth_obj, results_by_id, manifest))
        if "B3" in suite_ids:
            results.append(suite_b3_dead(truth_obj, results_by_id, manifest))
        if "B4" in suite_ids:
            results.append(suite_b4_rule_driven(ruleset, effective_rules, disabled))
        if "B5" in suite_ids:
            # 去重引擎消费与 check.json 同口径的重写后 URL（final_url 优先路径才能对上）
            bench_bookmarks = [
                dict(bm, url=rewrite_url(bm["url"], host_map)) for bm in bookmarks
            ]
            results.append(
                suite_b5_dedupe(bench_bookmarks, check_payload, truth_obj, ruleset, manifest, host_map)
            )
        if "B6" in suite_ids:
            results.append(suite_b6_consistency(bookmarks, ruleset, effective_rules, host_map))
        return results, host_map
    finally:
        server.shutdown()
        server.server_close()


def build_id_aliased_uir(chrome_obj, netscape_text):
    """以 gen_fixtures 派生口径重建 UIR：netscape 源名 = "html"（truth id 对账专用）。

    gen_fixtures 的 truth id = sha1("html|seq")——netscape 文件序。
    chrome 源条目与 netscape 同序（生成器双格式同源），本对账只消费 netscape 源。
    """
    from bookmark_doctor.model import build_bookmarks
    from bookmark_doctor.parse.netscape import parse_netscape

    return build_bookmarks(parse_netscape(netscape_text), "html")


def main(argv=None) -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="内置基准 runner（M4）：真值对账 + 规则驱动断言 + 探活（全程离线 loopback）"
    )
    parser.add_argument("--only", default=None, help="只跑指定套件（逗号分隔，如 B1,B3）")
    parser.add_argument(
        "--inject-defect",
        default=None,
        choices=list(DEFECTS),
        help="注入探活缺陷（403-dead：403 通用映射改 dead）——基准必须 exit 1",
    )
    parser.add_argument("--report", default=None, help="指标 JSON 落盘路径（.tmp/ 下，非冻结产物）")
    args = parser.parse_args(argv)

    try:
        results, host_map = run_bench(only=args.only, defect=args.inject_defect)
    except BenchConfigError as exc:
        print("[bench] 配置错误: %s" % exc, file=sys.stderr)
        return 2

    all_passed = all(r.passed for r in results)
    report = {
        "schema": "bookmark-doctor.bench/1",
        "injected_defect": bench_state.defect,
        "mock_rewrite": {k: v for k, v in sorted(host_map.items())},
        "suites": [r.as_dict() for r in results],
        "all_passed": all_passed,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print("[bench] 指标已写入 %s" % report_path, file=sys.stderr)
    for r in results:
        status = "PASS" if r.passed else ("NOT_ENABLED" if r.not_enabled else "FAIL")
        print(
            "[bench] %s %s %s" % (r.suite_id, status, json.dumps(r.metrics, ensure_ascii=False, sort_keys=True))
        )
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

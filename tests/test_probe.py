"""M3 probe（探测引擎）+ ruleset（锚点硬门正式引擎）测试。

探测测试打本地 mock 站点（模块级 fixture 起 ThreadingHTTPServer，仅 loopback）；
ruleset 测试复用仓库正本 + 合成构造的台账场景。
"""

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from bookmark_doctor.probe import probe_url
from bookmark_doctor.ruleset import apply_anchor_gate, load_effective_rules

# ---------------------------------------------------------------------------
# 本地 mock（测试自带，仅 loopback；与 tools/mock_site.py 同一响应表语义）
# ---------------------------------------------------------------------------

_STATUS_CODES = (200, 301, 302, 403, 404, 405, 410, 521)


class _Handler(BaseHTTPRequestHandler):
    def _respond(self, code, extra_headers=None):
        body = b""
        self.send_response(code)
        self.send_header("Content-Length", "0")
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        self._route()

    def do_HEAD(self):
        self._route()

    def _route(self):
        path = self.path.split("?", 1)[0].strip("/")
        parts = path.split("/") if path else []
        if len(parts) == 2 and parts[0] == "status" and parts[1].isdigit():
            code = int(parts[1])
            self._respond(code if code in _STATUS_CODES else 404)
            return
        if len(parts) == 2 and parts[0] == "redirect" and parts[1] in ("301", "302"):
            self._respond(int(parts[1]), {"Location": "/final/200"})
            return
        if path == "redirect/loop":
            self._respond(302, {"Location": "/redirect/loop"})
            return
        if len(parts) == 3 and parts[0] == "redirect" and parts[1] == "chain":
            # 两跳链：chain → step2 → final/200
            if parts[2] == "start":
                self._respond(302, {"Location": "/redirect/chain/step2"})
                return
            if parts[2] == "step2":
                self._respond(302, {"Location": "/final/200"})
                return
        if len(parts) == 2 and parts[0] == "final" and parts[1] == "200":
            self._respond(200)
            return
        if path == "headless-405":
            # HEAD → 405；GET → 200（HEAD 拒绝降级 GET 语义场景）
            if self.command == "HEAD":
                self._respond(405)
            else:
                self._respond(200)
            return
        if path == "never":
            # 挂起：阻塞读直至客户端断开
            try:
                while self.rfile.readline(64):
                    pass
            except (ConnectionError, OSError):
                pass
            return
        self._respond(404)

    def log_message(self, fmt, *args):
        pass


@pytest.fixture(scope="module")
def mock_base():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:%d" % server.server_address[1]
    server.shutdown()
    server.server_close()


def _cfg(**overrides):
    cfg = {
        "timeout_s": 5,
        "retry_max": 0,
        "delay_s": 0,
        "redirect_max": 5,
        "user_agent": "pytest-probe/0.1",
    }
    cfg.update(overrides)
    return cfg


def test_2xx_alive(mock_base):
    r = probe_url(mock_base + "/status/200", _cfg())
    assert r.http_status == 200 and r.error_class is None and r.final_url


def test_404_410_dead_path(mock_base):
    assert probe_url(mock_base + "/status/404", _cfg()).http_status == 404
    assert probe_url(mock_base + "/status/410", _cfg()).http_status == 410


def test_blocked_403_521(mock_base):
    assert probe_url(mock_base + "/status/403", _cfg()).http_status == 403
    assert probe_url(mock_base + "/status/521", _cfg()).http_status == 521


def test_redirect_chain_recorded(mock_base):
    r = probe_url(mock_base + "/redirect/chain/start", _cfg())
    assert r.http_status == 200
    assert r.final_url.endswith("/final/200")
    assert len(r.redirect_chain) == 2
    assert r.redirect_chain[-1].endswith("/final/200")


def test_first_hop_status_preserved_on_redirect(mock_base):
    """首跳状态必须保留（反爬 302→登录页 200 场景）。

    缺陷复现：跟随跳转后若只留终态（200），ruleset 里挂 ``http_status=302``
    的风控规则永不命中——微博 302 会被通用映射判 alive。修复后探测记录须
    同时给出首跳状态（302）与终态（200）。
    """
    r = probe_url(mock_base + "/redirect/302", _cfg())
    assert r.http_status == 200
    assert r.final_url.endswith("/final/200")
    assert r.first_hop_status == 302, "首跳状态丢失——302 风控规则将永不命中"


def test_first_hop_status_equals_terminal_without_redirect(mock_base):
    """无跳转时首跳状态 = 终态（同一响应）。"""
    r = probe_url(mock_base + "/status/403", _cfg())
    assert r.http_status == 403
    assert r.first_hop_status == 403


def test_redirect_loop(mock_base):
    r = probe_url(mock_base + "/redirect/loop", _cfg())
    assert r.error_class == "redirect_loop"
    assert r.http_status is None


def test_head_rejected_falls_back_to_get(mock_base):
    # 405 场景：HEAD 被拒 → 降级 GET 限读（合计算一次逻辑探测）
    r = probe_url(mock_base + "/headless-405", _cfg())
    assert r.http_status == 200
    assert r.error_class is None


def test_dns_failure(mock_base):
    r = probe_url("http://unreachable.invalid/x", _cfg(timeout_s=3))
    assert r.error_class == "dns_failure"


def test_connection_refused(mock_base):
    r = probe_url("http://127.0.0.1:1/x", _cfg(timeout_s=3))
    assert r.error_class == "connection_error"


def test_hang_times_out(mock_base):
    r = probe_url(mock_base + "/never", _cfg(timeout_s=1))
    assert r.error_class in ("read_timeout", "connect_timeout")


def test_user_agent_from_config():
    # UA 只取 cfg（ruleset 单点），引擎不写字面量——这里只验证"请求带上了配置的 UA"
    seen = {}

    class _Catch(_Handler):
        def _route(self):
            seen["ua"] = self.headers.get("User-Agent")
            self._respond(200)

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Catch)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        probe_url("http://127.0.0.1:%d/x" % server.server_address[1], _cfg())
    finally:
        server.shutdown()
        server.server_close()
    assert seen["ua"] == "pytest-probe/0.1"


def test_probe_missing_params_raise_no_defaults():
    """引擎零默认值：probe 五参数缺任一即报错（不静默补 0/空串）。"""
    base = _cfg()
    for key in ("user_agent", "timeout_s", "retry_max", "redirect_max", "delay_s"):
        broken = dict(base)
        del broken[key]
        with pytest.raises(ValueError) as exc:
            probe_url("http://127.0.0.1:1/x", broken)
        assert "probe.%s" % key in str(exc.value), key


def test_probe_bookmarks_missing_delay_raises():
    from bookmark_doctor.probe import probe_bookmarks

    broken = _cfg()
    del broken["delay_s"]
    with pytest.raises(ValueError):
        probe_bookmarks(["http://127.0.0.1:1/x"], broken)


def test_redirect_limit_exceeded():
    # 跳转上限 2，链长 3 → too_many_redirects
    class _Chain(_Handler):
        counter = {"n": 0}

        def _route(self):
            _Chain.counter["n"] += 1
            self._respond(302, {"Location": "/next/%d" % _Chain.counter["n"]})

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Chain)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        r = probe_url(
            "http://127.0.0.1:%d/start" % server.server_address[1], _cfg(redirect_max=2)
        )
    finally:
        server.shutdown()
        server.server_close()
    assert r.error_class == "too_many_redirects"


# ---------------------------------------------------------------------------
# ruleset：锚点硬门正式引擎（与 M1 预览 loader 同判定顺序）
# ---------------------------------------------------------------------------


def _observations():
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    return json.loads(
        (root / "data" / "measurements" / "observations.json").read_text(encoding="utf-8")
    )


def test_repo_ruleset_all_rules_enabled():
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    ruleset = json.loads(
        (root / "data" / "rules" / "ruleset.json").read_text(encoding="utf-8")
    )
    enabled, disabled = apply_anchor_gate(ruleset, _observations())
    assert disabled == []
    assert len(enabled) == len(ruleset["degrade_rules"])


def test_anchor_gate_missing_and_pending():
    observations = _observations()
    pending_id = next(
        obs["id"] for obs in observations["observations"] if obs["check_status"] != "verified"
    )
    ruleset = {
        "degrade_rules": [
            {"id": "R-OK", "anchor": {"observation_id": "OBS-20261015-csdn-blog-521"}},
            {"id": "R-PENDING", "anchor": {"observation_id": pending_id}},
            {"id": "R-NOPE", "anchor": {"observation_id": "OBS-9999-not-exist"}},
        ]
    }
    enabled, disabled = apply_anchor_gate(ruleset, observations)
    assert [r["id"] for r in enabled] == ["R-OK"]
    reasons = {d["id"]: d["reason"] for d in disabled}
    assert reasons["R-PENDING"] == "anchor_not_verified"
    assert reasons["R-NOPE"] == "anchor_missing"


def test_load_effective_rules_from_repo():
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    ruleset, enabled, disabled = load_effective_rules(root)
    assert ruleset["schema"]
    assert enabled and disabled == []
    assert ruleset["probe"]["user_agent"]
    assert ruleset["tracked_query_params"]["prefixes"]

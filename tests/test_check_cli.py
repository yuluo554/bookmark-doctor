"""M3 CLI check / dedupe 子命令测试——退出码契约 + 确定性 + 未启用清单输出。

check 测试打本地 mock（subprocess 真跑 CLI），不依赖外网。
"""

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


class _Handler(BaseHTTPRequestHandler):
    def _respond(self, code):
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?", 1)[0].strip("/")
        parts = path.split("/") if path else []
        if len(parts) == 2 and parts[0] == "status" and parts[1].isdigit():
            self._respond(int(parts[1]))
            return
        self._respond(404)

    do_HEAD = do_GET

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


def _run_cli(args, cwd):
    env = {"PYTHONPATH": str(REPO_ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    import os

    env.update({k: v for k, v in os.environ.items() if k in ("SYSTEMROOT", "PATH", "TEMP", "TMP")})
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "bookmark_doctor"] + args,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _make_tree(tmp_path, base):
    bookmarks = [
        {"id": "t1", "title": "ok", "url": base + "/status/200", "add_date": 1,
         "folder": [], "source": "m.html"},
        {"id": "t2", "title": "gone", "url": base + "/status/404", "add_date": 2,
         "folder": [], "source": "m.html"},
        {"id": "t3", "title": "blocked", "url": base + "/status/403", "add_date": 3,
         "folder": [], "source": "m.html"},
    ]
    tree = {
        "schema": "bookmark-doctor.tree-v1",
        "sources": ["m.html"],
        "chrome_epoch_delta_us": 11644473600000000,
        "bookmarks": bookmarks,
    }
    path = tmp_path / "tree.json"
    path.write_bytes(
        json.dumps(tree, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    )
    return path


def test_check_cli_happy_path(tmp_path, mock_base):
    tree = _make_tree(tmp_path, mock_base)
    out = tmp_path / "check.json"
    proc = _run_cli(
        ["check", str(tree), "--probe-date", "2026-10-15", "--out", str(out)],
        tmp_path,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema"] == "bookmark-doctor.check-v1"
    assert payload["probe_date"] == "2026-10-15"
    assert payload["rules_disabled"] == []
    verdicts = {r["url"]: r["verdict"] for r in payload["results"]}
    assert verdicts[mock_base + "/status/200"] == "alive"
    assert verdicts[mock_base + "/status/404"] == "dead"
    assert verdicts[mock_base + "/status/403"] == "review"
    counts = payload["summary"]["verdict_counts"]
    assert counts == {"alive": 1, "dead": 1, "review": 1}


def test_check_cli_byte_deterministic(tmp_path, mock_base):
    tree = _make_tree(tmp_path, mock_base)
    out1, out2 = tmp_path / "c1.json", tmp_path / "c2.json"
    for out in (out1, out2):
        proc = _run_cli(
            ["check", str(tree), "--probe-date", "2026-10-15", "--out", str(out)],
            tmp_path,
        )
        assert proc.returncode == 0
    assert out1.read_bytes() == out2.read_bytes(), "同输入同参数 → check.json 逐字节一致"


def test_check_cli_missing_tree_exit2(tmp_path):
    proc = _run_cli(["check", str(tmp_path / "nope.json"), "--out", "-"], tmp_path)
    assert proc.returncode == 2
    assert "不可读" in proc.stderr.decode("utf-8", "replace")


def test_check_cli_bad_schema_exit2(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_bytes(b'{"schema": "other/1"}')
    proc = _run_cli(["check", str(bad), "--out", "-"], tmp_path)
    assert proc.returncode == 2
    # 无半成品
    assert not (tmp_path / "check.json").exists()


def test_check_cli_ruleset_broken_exit2(tmp_path, mock_base):
    tree = _make_tree(tmp_path, mock_base)
    broken_rules = tmp_path / "broken-rules.json"
    broken_rules.write_bytes(b"{oops")
    proc = _run_cli(
        ["check", str(tree), "--rules", str(broken_rules), "--out", "-"], tmp_path
    )
    assert proc.returncode == 2


def test_check_cli_disabled_rules_printed_to_stderr(tmp_path, mock_base):
    """未启用清单随运行输出到 stderr（plan/04 §2.3 承诺；缺陷 8 修复）。"""
    tree = _make_tree(tmp_path, mock_base)
    rules = {
        "schema": "bookmark-doctor.ruleset/1",
        "probe": {"timeout_s": 5, "retry_max": 0, "delay_s": 0,
                  "redirect_max": 5, "user_agent": "t/0.1"},
        "degrade_rules": [
            {"id": "R-PENDING", "match": {"host_suffix": "x.invalid", "http_status": 403},
             "disposition": "review", "reason": "r",
             "anchor": {"observation_id": "OBS-20261015-bilibili-redirect-claim",
                        "check_status": "verified"}},
        ],
    }
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(json.dumps(rules), encoding="utf-8")
    out = tmp_path / "c.json"
    proc = _run_cli(
        ["check", str(tree), "--rules", str(rules_path),
         "--probe-date", "2026-10-15", "--out", str(out)],
        tmp_path,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    stderr = proc.stderr.decode("utf-8", "replace")
    assert "未启用规则" in stderr and "R-PENDING" in stderr
    assert "anchor_not_verified" in stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["rules_disabled"][0]["id"] == "R-PENDING"


def test_dedupe_cli_happy_path(tmp_path, mock_base):
    tree_path = tmp_path / "tree.json"
    tree = json.loads(tree_path.read_text(encoding="utf-8")) if tree_path.exists() else None
    tree_path = _make_tree(tmp_path, mock_base)
    out = tmp_path / "dedupe.json"
    proc = _run_cli(["dedupe", str(tree_path), "--out", str(out)], tmp_path)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema"] == "bookmark-doctor.dedupe-v1"
    assert payload["summary"]["duplicate_groups"] == 0  # 三个 URL 互不相同


def test_dedupe_cli_groups_and_bytes(tmp_path):
    bookmarks = [
        {"id": "a", "title": "a", "url": "https://x.invalid/p/1?utm_source=s", "add_date": 1,
         "folder": [], "source": "m.html"},
        {"id": "b", "title": "b", "url": "https://x.invalid/p/1/?share_token=q", "add_date": 2,
         "folder": [], "source": "m.html"},
        {"id": "c", "title": "c", "url": "https://x.invalid/p/1#frag", "add_date": 3,
         "folder": [], "source": "m.html"},
    ]
    tree = {
        "schema": "bookmark-doctor.tree-v1",
        "sources": ["m.html"],
        "chrome_epoch_delta_us": 11644473600000000,
        "bookmarks": bookmarks,
    }
    tree_path = tmp_path / "tree.json"
    tree_path.write_bytes(
        json.dumps(tree, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    )
    out1, out2 = tmp_path / "d1.json", tmp_path / "d2.json"
    for out in (out1, out2):
        proc = _run_cli(["dedupe", str(tree_path), "--out", str(out)], tmp_path)
        assert proc.returncode == 0
    assert out1.read_bytes() == out2.read_bytes()
    payload = json.loads(out1.read_text(encoding="utf-8"))
    groups = payload["duplicate_groups"]
    assert len(groups) == 1
    assert [m["id"] for m in groups[0]["members"]] == ["a", "b", "c"]
    assert groups[0]["fragment_variant"] is True
    # 保留策略：无追踪参数优先于 add_date 最早
    assert groups[0]["keep"]["id"] == "c"


def test_dedupe_cli_missing_check_exit2(tmp_path, mock_base):
    tree_path = _make_tree(tmp_path, mock_base)
    proc = _run_cli(
        ["dedupe", str(tree_path), "--check", str(tmp_path / "nocheck.json"), "--out", "-"],
        tmp_path,
    )
    assert proc.returncode == 2

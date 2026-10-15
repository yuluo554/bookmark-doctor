"""M5 CLI report / export / run 子命令测试 + aging/report/export 单元（plan/04 §4）。

契约锁定：
- report：零外链硬断言 / 七节结构 / 未探测独立分区 / 渲染零判定（字节级确定性）；
- export：默认不删不改 / --apply-dedupe / --exclude-dead / 开关缺产物 exit 2 /
  往返解析一致 / 转义纪律；
- aging：阈值取 ruleset（缺失/非法报错）/ null 单列 / 参考日确定性；
- run：全链路编排（打本地 mock，不依赖外网）/ 退出码契约。
"""

import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from bookmark_doctor.aging import (
    AgingConfigError,
    build_aging_profile,
    load_aging_tiers,
)
from bookmark_doctor.export import export_netscape, filter_bookmarks
from bookmark_doctor.parse.netscape import parse_netscape
from bookmark_doctor.report import assert_no_external_resources, render_report

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_cli(args, cwd):
    import os

    env = {"PYTHONPATH": str(REPO_ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    env.update({k: v for k, v in os.environ.items() if k in ("SYSTEMROOT", "PATH", "TEMP", "TMP")})
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "bookmark_doctor"] + args,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _tree(bookmarks):
    return {
        "schema": "bookmark-doctor.tree-v1",
        "sources": ["m.html"],
        "chrome_epoch_delta_us": 11644473600000000,
        "bookmarks": bookmarks,
    }


def _bm(id_, url, title="标题", add_date=None, folder=None):
    return {
        "id": id_,
        "title": title,
        "url": url,
        "add_date": add_date,
        "folder": folder or [],
        "source": "m.html",
    }


def _check_payload(results):
    counts = {}
    for item in results:
        counts[item["verdict"]] = counts.get(item["verdict"], 0) + 1
    return {
        "schema": "bookmark-doctor.check-v1",
        "probe_date": "2026-10-15",
        "ruleset_version": "v-test",
        "ruleset_revision": 1,
        "rules_disabled": [],
        "summary": {"total": len(results), "verdict_counts": counts, "reason_counts": {}},
        "results": results,
    }


def _record(url, verdict, reason="r", rule_id=None):
    return {
        "url": url,
        "final_url": None,
        "redirect_chain": [],
        "http_status": None,
        "error_class": None,
        "verdict": verdict,
        "reason": reason,
        "rule_id": rule_id,
        "conflict": None,
    }


# ---------- aging 单元 ----------

def test_aging_tiers_loaded_from_ruleset():
    ruleset = json.loads((REPO_ROOT / "data" / "rules" / "ruleset.json").read_text(encoding="utf-8"))
    tiers = load_aging_tiers(ruleset)
    assert tiers == ruleset["aging"]["tiers_days"]


def test_aging_config_missing_rejected():
    with pytest.raises(AgingConfigError):
        load_aging_tiers({})
    with pytest.raises(AgingConfigError):
        load_aging_tiers({"aging": {}})
    with pytest.raises(AgingConfigError):
        load_aging_tiers({"aging": {"tiers_days": [730, 365]}})  # 非升序
    with pytest.raises(AgingConfigError):
        load_aging_tiers({"aging": {"tiers_days": [0]}})


def test_aging_profile_tiers_and_unknown():
    # 参考日 2026-10-15；400 天前 ≈ 2025-09-10（1年+，不足2年）；800 天前（2年+）；
    # 未来 add_date（1年内）；None（未知单列）
    base = datetime.date(2026, 10, 15)
    d = lambda days: int(datetime.datetime.combine(
        base - datetime.timedelta(days=days), datetime.time.min
    ).replace(tzinfo=datetime.timezone.utc).timestamp())
    bookmarks = [
        _bm("a", "http://x/1", add_date=d(400)),
        _bm("b", "http://x/2", add_date=d(800)),
        _bm("c", "http://x/3", add_date=d(10)),
        _bm("d", "http://x/4", add_date=None),
        _bm("e", "http://x/5", add_date=d(1300)),
    ]
    profile = build_aging_profile(bookmarks, [365, 730, 1095], base)
    assert profile["as_of_date"] == "2026-10-15"
    assert [t["tier"] for t in profile["tiers"]] == ["1年+", "2年+", "3年+"]
    assert [t["count"] for t in profile["tiers"]] == [1, 1, 1]
    assert profile["within"]["count"] == 1
    assert profile["unknown_add_date"]["count"] == 1
    assert profile["unknown_add_date"]["ids"] == ["d"]
    assert "以添加时间近似未访问" in profile["note"]


# ---------- report 单元 ----------

def test_report_zero_external_resources():
    check = _check_payload([_record("http://x/1", "dead")])
    html = render_report(check, tree_bookmarks=[_bm("a", "http://x/1")]).decode("utf-8")
    assert_no_external_resources(html)  # 不抛 = 无 <link>/<script src>/<img>/@import/外链字体
    # 七节标题齐
    for section in ("摘要", "失效清单", "待复核清单", "重复清单",
                    "长期未访问画像", "未探测条目", "建议清理清单", "口径与免责"):
        assert section in html


def test_report_unprobed_section_and_no_judgment():
    bookmarks = [_bm("a", "http://x/1"), _bm("b", "http://x/2")]
    check = _check_payload([_record("http://x/1", "alive")])
    html = render_report(check, tree_bookmarks=bookmarks).decode("utf-8")
    assert "未探测条目" in html
    assert "http://x/2" in html  # 未探测 URL 独立呈现
    # 渲染零判定：check 没说的 verdict 不出现新结论
    assert html.count('class="badge dead"') == 0


def test_report_escape_and_deterministic():
    bookmarks = [_bm("a", "http://x/1?a=1&b=<2>", title="<script>&\"x\"")]
    check = _check_payload([_record("http://x/1?a=1&b=<2>", "review")])
    html_bytes_1 = render_report(check, tree_bookmarks=bookmarks)
    html_bytes_2 = render_report(check, tree_bookmarks=bookmarks)
    assert html_bytes_1 == html_bytes_2  # 字节级确定
    html = html_bytes_1.decode("utf-8")
    assert "<script>&\"x\"" not in html  # 原文不得直出
    assert "&lt;script&gt;&amp;\"x\"" in html.replace("&quot;", "\"")


def test_report_dedupe_fragment_variant_marked():
    group = {
        "group_id": "dup-0001",
        "members": [
            {"id": "a", "url": "http://x/1", "fragment_variant": True},
            {"id": "b", "url": "http://x/1#top", "fragment_variant": True},
        ],
        "keep": {"id": "a", "url": "http://x/1"},
    }
    dedupe = {"schema": "bookmark-doctor.dedupe-v1", "duplicate_groups": [group]}
    check = _check_payload([])
    html = render_report(check, dedupe_payload=dedupe, tree_bookmarks=[]).decode("utf-8")
    assert "仅锚点不同" in html
    assert "dup-0001" in html


# ---------- export 单元 ----------

def test_export_roundtrip_and_escape():
    bookmarks = [
        _bm("a", "http://x/1?a=1&b=2", title="中文 & <标题>"),
        _bm("b", "http://x/2", title=None, add_date=1700000000, folder=["父", "子"]),
    ]
    html = export_netscape(bookmarks).decode("utf-8")
    assert html.startswith("<!DOCTYPE NETSCAPE-Bookmark-file-1>")
    reparsed = list(parse_netscape(html))
    assert len(reparsed) == 2
    assert reparsed[0]["url"] == "http://x/1?a=1&b=2"
    assert reparsed[0]["title"] == "中文 & <标题>"
    assert reparsed[1]["folder"] == ["父", "子"]
    assert reparsed[1]["add_date"] == 1700000000


def test_export_filters_only_existing_verdicts():
    bookmarks = [_bm("a", "http://x/1"), _bm("b", "http://x/2"), _bm("c", "http://x/3")]
    dedupe = {"duplicate_groups": [{
        "group_id": "dup-0001",
        "members": [{"id": "a", "url": "http://x/1"}, {"id": "b", "url": "http://x/2"}],
        "keep": {"id": "a", "url": "http://x/1"},
    }]}
    check = _check_payload([_record("http://x/2", "dead")])
    # 默认不删不改
    assert filter_bookmarks(bookmarks) == bookmarks
    # apply_dedupe：组内非保留成员剔除；组外书签原样保留
    assert [bm["id"] for bm in filter_bookmarks(
        bookmarks, dedupe_payload=dedupe, apply_dedupe=True)] == ["a", "c"]
    # exclude_dead：剔除 dead URL
    assert [bm["id"] for bm in filter_bookmarks(
        bookmarks, check_payload=check, exclude_dead=True)] == ["a", "c"]
    # 组合：组内剔 b、dead 剔 x/2（b）→ 剩 a、c
    assert [bm["id"] for bm in filter_bookmarks(
        bookmarks, dedupe_payload=dedupe, check_payload=check,
        apply_dedupe=True, exclude_dead=True)] == ["a", "c"]
    # 无产物 + 开关关：不消费
    assert filter_bookmarks(bookmarks, apply_dedupe=True, exclude_dead=True) == bookmarks


def test_export_cli_switches_and_exit_codes(tmp_path):
    tree_path = tmp_path / "tree.json"
    bookmarks = [_bm("a", "http://x/1"), _bm("b", "http://x/2")]
    tree_path.write_bytes(json.dumps(_tree(bookmarks), ensure_ascii=False).encode("utf-8"))
    dedupe_path = tmp_path / "dedupe.json"
    dedupe_path.write_text(json.dumps({"duplicate_groups": [{
        "group_id": "dup-0001",
        "members": [{"id": "a", "url": "http://x/1"}, {"id": "b", "url": "http://x/2"}],
        "keep": {"id": "a", "url": "http://x/1"},
    }]}, ensure_ascii=False), encoding="utf-8")
    check_path = tmp_path / "check.json"
    check_path.write_text(json.dumps(_check_payload([
        _record("http://x/1", "dead")])), encoding="utf-8")

    # 默认不删不改：全量导回
    out = tmp_path / "full.html"
    r = _run_cli(["export", str(tree_path), "--out", str(out)], cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert len(list(parse_netscape(out.read_text(encoding="utf-8")))) == 2

    # apply_dedupe：1 条
    out2 = tmp_path / "deduped.html"
    r = _run_cli(["export", str(tree_path), "--dedupe", str(dedupe_path),
                  "--apply-dedupe", "--out", str(out2)], cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert [e["url"] for e in parse_netscape(out2.read_text(encoding="utf-8"))] == ["http://x/1"]

    # exclude_dead：剔除 a 后剩 b
    out3 = tmp_path / "nodead.html"
    r = _run_cli(["export", str(tree_path), "--check", str(check_path),
                  "--exclude-dead", "--out", str(out3)], cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert [e["url"] for e in parse_netscape(out3.read_text(encoding="utf-8"))] == ["http://x/2"]

    # 开关缺产物 → exit 2
    r = _run_cli(["export", str(tree_path), "--apply-dedupe",
                  "--out", str(tmp_path / "x.html")], cwd=str(tmp_path))
    assert r.returncode == 2


# ---------- report CLI ----------

def test_report_cli_end_to_end(tmp_path):
    tree_path = tmp_path / "tree.json"
    bookmarks = [_bm("a", "http://x/1", title="存活"), _bm("b", "http://x/2", add_date=None)]
    tree_path.write_bytes(json.dumps(_tree(bookmarks), ensure_ascii=False).encode("utf-8"))
    check_path = tmp_path / "check.json"
    check_path.write_text(json.dumps(_check_payload([
        _record("http://x/1", "alive"), _record("http://x/2", "review", rule_id="R")]),
        ), encoding="utf-8")
    out = tmp_path / "report.html"
    r = _run_cli(["report", str(tree_path), "--check", str(check_path),
                  "--aging-date", "2026-10-15", "--out", str(out)], cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    html = out.read_bytes().decode("utf-8")
    assert_no_external_resources(html)
    # 渲染层零判定：消费既有结论原样呈现
    assert "存活" in html
    assert "http://x/2" in html
    assert "添加时间未知" in html  # aging null 单列


# ---------- run 编排（打本地 mock） ----------

@pytest.fixture(scope="module")
def mock_base():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
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

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    import threading

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:%d" % server.server_address[1]
    server.shutdown()
    server.server_close()


def _write_input(tmp_path, base):
    """合成 Netscape 输入（run 的起点走 import 真解析）。"""
    lines = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        "<DL><p>",
        '    <DT><A HREF="%s/status/200" ADD_DATE="1700000000">ok</A>' % base,
        '    <DT><A HREF="%s/status/404" ADD_DATE="1600000000">gone</A>' % base,
        '    <DT><A HREF="%s/status/200" ADD_DATE="1500000000">dup-ok</A>' % base,
        "</DL><p>",
    ]
    path = tmp_path / "input.html"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_run_orchestrates_all_steps(tmp_path, mock_base):
    from bookmark_doctor.probe import probe_bookmarks

    src = _write_input(tmp_path, mock_base)
    out_dir = tmp_path / "out"
    r = _run_cli(["run", str(src), "--out-dir", str(out_dir),
                  "--probe-date", "2026-10-15"], cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr.decode("utf-8")
    for name in ("tree.json", "check.json", "dedupe.json",
                 "report.html", "bookmarks-export.html"):
        assert (out_dir / name).exists(), name
    tree = json.loads((out_dir / "tree.json").read_text(encoding="utf-8"))
    # import 层同 URL 精确合并（M2 冻结语义）：3 条输入 → 2 条（200 合一）
    assert len(tree["bookmarks"]) == 2
    check = json.loads((out_dir / "check.json").read_text(encoding="utf-8"))
    assert check["probe_date"] == "2026-10-15"
    verdicts = {item["url"]: item["verdict"] for item in check["results"]}
    assert verdicts[mock_base + "/status/404"] == "dead"
    assert verdicts[mock_base + "/status/200"] == "alive"
    dedupe = json.loads((out_dir / "dedupe.json").read_text(encoding="utf-8"))
    assert dedupe["summary"]["duplicate_groups"] == 0  # 同 URL 已在 import 合并
    html = (out_dir / "report.html").read_bytes().decode("utf-8")
    assert_no_external_resources(html)
    assert "dead" in html
    exported = list(parse_netscape(
        (out_dir / "bookmarks-export.html").read_text(encoding="utf-8")))
    assert len(exported) == 2  # 默认不删不改

    # 第二次 run（--apply-dedupe --exclude-dead）：显式动作生效（剔除 dead → 剩 200）
    out_dir2 = tmp_path / "out2"
    r = _run_cli(["run", str(src), "--out-dir", str(out_dir2),
                  "--probe-date", "2026-10-15",
                  "--apply-dedupe", "--exclude-dead"], cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr.decode("utf-8")
    exported2 = list(parse_netscape(
        (out_dir2 / "bookmarks-export.html").read_text(encoding="utf-8")))
    assert len(exported2) == 1
    assert exported2[0]["url"] == mock_base + "/status/200"


def test_run_bad_input_exit2_no_outdir_semiproduct(tmp_path):
    broken = tmp_path / "bad.json"
    broken.write_bytes(b"not json at all")
    out_dir = tmp_path / "o"
    r = _run_cli(["run", str(broken), "--out-dir", str(out_dir)], cwd=str(tmp_path))
    assert r.returncode == 2
    assert not (out_dir / "tree.json").exists(), "解析失败不得落半成品"


def test_run_deterministic_outputs(tmp_path, mock_base):
    src = _write_input(tmp_path, mock_base)
    digests = []
    import hashlib

    for index in (1, 2):
        out_dir = tmp_path / ("run%d" % index)
        r = _run_cli(["run", str(src), "--out-dir", str(out_dir),
                      "--probe-date", "2026-10-15"], cwd=str(tmp_path))
        assert r.returncode == 0, r.stderr.decode("utf-8")
        for name in ("tree.json", "check.json", "dedupe.json", "report.html"):
            digests.append(hashlib.sha256((out_dir / name).read_bytes()).hexdigest())
    assert digests[0::4] == digests[4:] or True  # 占位，下行严格比对
    assert digests[:4] == digests[4:]

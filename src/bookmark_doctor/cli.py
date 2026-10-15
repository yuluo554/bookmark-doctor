"""bookmark-doctor 命令行入口。

子命令全集（M5）：``--version``/``--selftest`` + import / check / dedupe /
report / export / run。退出码契约（锁定进测试，plan/03 §8）：
- 0 = 运行完成（含"体检发现问题"——问题进报告，不是错误）
- 2 = 用法错误 / 无参数 / 输入不可用（含解析失败——不落半成品）
- ``--selftest``：0 通过 / 1 失败
"""

import argparse
import json
import platform
import sys
from pathlib import Path

from bookmark_doctor import __version__
from bookmark_doctor._encoding import ensure_utf8_stdio
from bookmark_doctor.parse.errors import ParseError

_APP = "bookmark-doctor"

# 仓库根（import 默认数据源正本按相对仓库根解析）
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_APP,
        description=(
            "收藏夹体检工具（中文站点友好）：失效检测 / 重复合并 / 长期未访问画像 / 一键导回。"
            "纯本地、零上传、运行时零第三方依赖。"
        ),
        epilog=(
            "子命令：import / check / dedupe / report / export / run。"
            "报告单文件 HTML 断网可开；导出默认不删不改，合并/剔除须显式开关。"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%s %s" % (_APP, __version__),
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="运行内置自检并输出 JSON（退出码携带成败：0 通过 / 1 失败）",
    )
    subparsers = parser.add_subparsers(dest="command")
    parser_import = subparsers.add_parser(
        "import",
        help="解析浏览器书签文件并合并 → tree.json（UIR）",
        description=(
            "解析 Netscape Bookmark HTML（.html/.htm）与 Chrome/Edge Bookmarks JSON（.json），"
            "合并为统一中间表示 tree.json。多文件输入；解析失败 exit 2 不落半成品。"
        ),
    )
    parser_import.add_argument(
        "files",
        nargs="+",
        help="输入文件（.html/.htm = Netscape；.json = Chrome/Edge）",
    )
    parser_import.add_argument(
        "--out",
        default=None,
        help="输出路径（默认 tree.json；传 - 则仅 stdout 打印合并摘要不落盘）",
    )
    parser_check = subparsers.add_parser(
        "check",
        help="探测 tree.json 全部书签并分类 → check.json（失效检测）",
        description=(
            "对 tree.json（UIR）全部书签做单次逻辑探测（HEAD，405/501 降级 GET）并按"
            "状态分类表 + 降级规则判定 verdict。串行降频；单 URL 网络失败落 review 不中断；"
            "文件级失败 exit 2 不落半成品。"
        ),
    )
    parser_check.add_argument("tree", help="tree.json 路径（UIR）")
    parser_check.add_argument(
        "--rules",
        default=None,
        help="规则包路径（默认 data/rules/ruleset.json 仓库正本；参数保留覆盖位）",
    )
    parser_check.add_argument(
        "--probe-date",
        default=None,
        help="探测日期（YYYY-MM-DD；默认当天——产物确定性要求基准传固定值）",
    )
    parser_check.add_argument("--out", default="check.json", help="输出路径（默认 check.json）")
    parser_dedupe = subparsers.add_parser(
        "dedupe",
        help="URL 规范化去重 → dedupe.json（重复组清单，绝不自动删）",
        description=(
            "对 tree.json（UIR）按规范化比较键分组，输出重复组 + 建议保留项。"
            "只出清单不删除；--check 提供探测结果时比较键优先用 final_url。"
        ),
    )
    parser_dedupe.add_argument("tree", help="tree.json 路径（UIR）")
    parser_dedupe.add_argument(
        "--check",
        default=None,
        help="check.json 路径（可选；提供时比较键优先用 normalize(final_url)）",
    )
    parser_dedupe.add_argument(
        "--rules",
        default=None,
        help="规则包路径（默认仓库正本；取 tracked_query_params）",
    )
    parser_dedupe.add_argument("--out", default="dedupe.json", help="输出路径（默认 dedupe.json）")
    parser_report = subparsers.add_parser(
        "report",
        help="check/dedupe 产物 → 单文件 HTML 报告（零外链，断网可开）",
        description=(
            "渲染单文件 HTML 报告：只消费 check.json / dedupe.json 既有结论"
            "（渲染层零判定逻辑），附长期未访问画像（阈值取 ruleset aging.tiers_days）。"
            "资源零外链：CSS 内联、无外部脚本/图片/字体，断网可开。"
        ),
    )
    parser_report.add_argument("tree", help="tree.json 路径（UIR，供标题与未探测分区）")
    parser_report.add_argument("--check", default="check.json", help="check.json 路径（默认 check.json）")
    parser_report.add_argument(
        "--dedupe",
        default=None,
        help="dedupe.json 路径（可选；缺省时重复节呈现无数据）",
    )
    parser_report.add_argument(
        "--rules",
        default=None,
        help="规则包路径（默认仓库正本；取 aging.tiers_days）",
    )
    parser_report.add_argument(
        "--aging-date",
        default=None,
        help="画像参考日（YYYY-MM-DD；默认取 check.json 的 probe_date，再缺省当天）",
    )
    parser_report.add_argument("--out", default="report.html", help="输出路径（默认 report.html）")
    parser_export = subparsers.add_parser(
        "export",
        help="tree.json → Netscape HTML 导回文件（默认不删不改）",
        description=(
            "导出标准 Netscape Bookmark HTML（浏览器可导入）。默认全量导回、"
            "不删不改；--apply-dedupe（重复组只留建议保留项）与 --exclude-dead"
            "（剔除 check 判 dead 条目）为显式可选动作，须同时提供对应产物。"
        ),
    )
    parser_export.add_argument("tree", help="tree.json 路径（UIR）")
    parser_export.add_argument(
        "--dedupe",
        default=None,
        help="dedupe.json 路径（--apply-dedupe 时必填）",
    )
    parser_export.add_argument(
        "--check",
        default=None,
        help="check.json 路径（--exclude-dead 时必填）",
    )
    parser_export.add_argument(
        "--apply-dedupe",
        action="store_true",
        help="显式动作：重复组只保留建议保留项（需 --dedupe）",
    )
    parser_export.add_argument(
        "--exclude-dead",
        action="store_true",
        help="显式动作：剔除 check 判 dead 的条目（需 --check）",
    )
    parser_export.add_argument("--out", default="bookmarks-export.html", help="输出路径（默认 bookmarks-export.html）")
    parser_run = subparsers.add_parser(
        "run",
        help="全链路编排：import → check → dedupe → report → export",
        description=(
            "一条命令跑完整链路（编排层：复用各子命令实现，无第二份判定逻辑）。"
            "产物落在 --out-dir：tree.json / check.json / dedupe.json / report.html /"
            " bookmarks-export.html；任何文件级失败 exit 2 不落半成品目录。"
        ),
    )
    parser_run.add_argument("files", nargs="+", help="输入文件（.html/.htm = Netscape；.json = Chrome/Edge）")
    parser_run.add_argument("--out-dir", default=".", help="输出目录（默认当前目录）")
    parser_run.add_argument(
        "--probe-date",
        default=None,
        help="探测日期（YYYY-MM-DD；默认当天——产物确定性要求传固定值）",
    )
    parser_run.add_argument(
        "--rules",
        default=None,
        help="规则包路径（默认仓库正本）",
    )
    parser_run.add_argument(
        "--apply-dedupe",
        action="store_true",
        help="导出时显式应用去重（重复组只留建议保留项）",
    )
    parser_run.add_argument(
        "--exclude-dead",
        action="store_true",
        help="导出时显式剔除 dead 条目",
    )
    return parser


def _check_python():
    ok = sys.version_info >= (3, 8)
    return {"name": "python", "ok": ok, "detail": platform.python_version()}


def _check_cjk_stdout():
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "体检".encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return {
            "name": "cjk-stdout",
            "ok": False,
            "detail": "stdout 编码无法输出中文字符: %r" % encoding,
        }
    return {"name": "cjk-stdout", "ok": True, "detail": "中文输出正常"}


def _check_runtime_deps():
    try:
        from importlib.metadata import requires

        requirements = requires(_APP) or []
    except Exception:
        # 源码态（未安装）无法读取发行元数据：如实标注"不适用"，由安装面与 CI 核对。
        return {
            "name": "runtime-deps",
            "ok": None,
            "detail": "元数据不可用（源码态运行）；完整性由安装面与 CI 核对",
        }
    runtime = [item for item in requirements if ";" not in item]
    if runtime:
        return {
            "name": "runtime-deps",
            "ok": False,
            "detail": "存在第三方运行时依赖: %s" % "; ".join(runtime),
        }
    return {"name": "runtime-deps", "ok": True, "detail": "零第三方运行时依赖"}


def _selftest() -> int:
    checks = [_check_python(), _check_cjk_stdout(), _check_runtime_deps()]
    ok = all(check["ok"] is not False for check in checks)
    payload = {"name": _APP, "version": __version__, "ok": ok, "checks": checks}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if ok else 1


def _cmd_import(args) -> int:
    from bookmark_doctor.model import build_tree, merge_duplicates, serialize_tree

    out_path = args.out
    # 第一遍：全量解析 + 构树（任何文件失败 → exit 2，不落半成品）
    try:
        sources = [{"path": Path(p), "source": Path(p).name} for p in args.files]
        tree = build_tree(sources, _REPO_ROOT)
    except ParseError as exc:
        print("[import] 解析失败: %s" % exc, file=sys.stderr)
        return 2
    merged, dup_groups = merge_duplicates(tree["bookmarks"])
    tree["bookmarks"] = merged
    summary = {
        "schema": tree["schema"],
        "sources": tree["sources"],
        "bookmarks_total": len(tree["bookmarks"]),
        "duplicate_groups_merged": dup_groups,
        "add_date_null": sum(1 for b in tree["bookmarks"] if b["add_date"] is None),
    }
    print(
        json.dumps(summary, ensure_ascii=False, sort_keys=True),
        flush=True,
    )
    if out_path == "-":
        return 0
    target = Path(out_path) if out_path else Path("tree.json")
    try:
        target.write_bytes(serialize_tree(tree))
    except OSError as exc:
        print("[import] 输出不可写 %s: %s" % (target, exc), file=sys.stderr)
        return 2
    print("[import] 已写入 %s" % target, file=sys.stderr)
    return 0


def _resolve_rules_path(rules_arg):
    """--rules 覆盖位；缺省取仓库正本（plan/03 §9 单点）。"""
    return Path(rules_arg) if rules_arg else _REPO_ROOT / "data" / "rules" / "ruleset.json"


def _serialize_payload(payload):
    """check.json / dedupe.json 确定性序列化（K18 纪律，serialize 模块单点）。"""
    from bookmark_doctor.serialize import serialize_payload

    return serialize_payload(payload)


def _cmd_check(args) -> int:
    import datetime

    from bookmark_doctor.classify import classify
    from bookmark_doctor.model import serialize_tree
    from bookmark_doctor.probe import probe_bookmarks
    from bookmark_doctor.ruleset import RulesetError, load_effective_rules
    from bookmark_doctor.serialize import write_atomic

    tree_path = Path(args.tree)
    try:
        tree = json.loads(tree_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("[check] tree.json 不可读: %s" % exc, file=sys.stderr)
        return 2
    if tree.get("schema") != "bookmark-doctor.tree-v1":
        print("[check] 输入不是 bookmark-doctor.tree-v1: %s" % tree_path, file=sys.stderr)
        return 2
    try:
        ruleset, effective_rules, disabled = load_effective_rules(_REPO_ROOT, args.rules)
    except (RulesetError, OSError, ValueError) as exc:
        print("[check] 规则包不可用: %s" % exc, file=sys.stderr)
        return 2
    probe_date = args.probe_date or datetime.date.today().isoformat()
    bookmarks = tree.get("bookmarks", [])
    urls = [bm["url"] for bm in bookmarks]
    if urls:
        print(
            "[check] 探测 %d 条（串行降频，delay=%.2fs）..."
            % (len(urls), float(ruleset["probe"]["delay_s"])),
            file=sys.stderr,
        )
    records = probe_bookmarks(
        urls,
        ruleset["probe"],
        progress=lambda i, total, url: print(
            "[check] %d/%d %s" % (i + 1, total, url), file=sys.stderr
        ),
    )
    results = []
    for record in records:
        outcome = classify(record, effective_rules)
        results.append(
            {
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
    verdict_counts = {}
    reason_counts = {}
    for item in results:
        verdict_counts[item["verdict"]] = verdict_counts.get(item["verdict"], 0) + 1
        reason_counts[item["reason"]] = reason_counts.get(item["reason"], 0) + 1
    payload = {
        "schema": "bookmark-doctor.check-v1",
        "probe_date": probe_date,
        "ruleset_version": ruleset.get("version"),
        "ruleset_revision": ruleset.get("revision"),
        "rules_disabled": disabled,
        "summary": {
            "total": len(results),
            "verdict_counts": verdict_counts,
            "reason_counts": reason_counts,
        },
        "results": results,
    }
    target = Path(args.out) if args.out else Path("check.json")
    if target.name == "-":
        print(
            json.dumps(payload["summary"], ensure_ascii=False, sort_keys=True),
            flush=True,
        )
        return 0
    try:
        write_atomic(target, _serialize_payload(payload))
    except OSError as exc:
        print("[check] 输出不可写 %s: %s" % (target, exc), file=sys.stderr)
        return 2
    print(
        "[check] 已写入 %s（%s）"
        % (target, json.dumps(verdict_counts, ensure_ascii=False, sort_keys=True)),
        file=sys.stderr,
    )
    return 0


def _cmd_dedupe(args) -> int:
    from bookmark_doctor.dedupe import build_duplicate_groups
    from bookmark_doctor.ruleset import RulesetError, load_ruleset
    from bookmark_doctor.serialize import write_atomic

    tree_path = Path(args.tree)
    try:
        tree = json.loads(tree_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("[dedupe] tree.json 不可读: %s" % exc, file=sys.stderr)
        return 2
    if tree.get("schema") != "bookmark-doctor.tree-v1":
        print("[dedupe] 输入不是 bookmark-doctor.tree-v1: %s" % tree_path, file=sys.stderr)
        return 2
    try:
        ruleset = load_ruleset(_REPO_ROOT, args.rules)
    except (RulesetError, OSError, ValueError) as exc:
        print("[dedupe] 规则包不可用: %s" % exc, file=sys.stderr)
        return 2
    tracked_params = ruleset.get("tracked_query_params") or {}
    check_records = None
    if args.check:
        try:
            check_payload = json.loads(Path(args.check).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print("[dedupe] check.json 不可读: %s" % exc, file=sys.stderr)
            return 2
        check_records = check_payload.get("results", [])
    groups = build_duplicate_groups(tree.get("bookmarks", []), tracked_params, check_records)
    payload = {
        "schema": "bookmark-doctor.dedupe-v1",
        "ruleset_version": ruleset.get("version"),
        "summary": {
            "total": len(tree.get("bookmarks", [])),
            "duplicate_groups": len(groups),
        },
        "duplicate_groups": groups,
    }
    target = Path(args.out) if args.out else Path("dedupe.json")
    if target.name == "-":
        print(
            json.dumps(payload["summary"], ensure_ascii=False, sort_keys=True),
            flush=True,
        )
        return 0
    try:
        write_atomic(target, _serialize_payload(payload))
    except OSError as exc:
        print("[dedupe] 输出不可写 %s: %s" % (target, exc), file=sys.stderr)
        return 2
    print("[dedupe] 已写入 %s（重复组 %d）" % (target, len(groups)), file=sys.stderr)
    return 0


def _load_json_file(path, label):
    """读 JSON 产物；不可读 → (None, 错误消息)。"""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), None
    except (OSError, ValueError) as exc:
        return None, "%s 不可读 %s: %s" % (label, path, exc)


def _cmd_report(args) -> int:
    from bookmark_doctor.aging import (
        AgingConfigError,
        build_aging_profile,
        load_aging_tiers,
    )
    from bookmark_doctor.report import render_report
    from bookmark_doctor.ruleset import RulesetError, load_ruleset
    from bookmark_doctor.serialize import write_atomic

    tree, err = _load_json_file(args.tree, "[report] tree.json")
    if err:
        print(err, file=sys.stderr)
        return 2
    if tree.get("schema") != "bookmark-doctor.tree-v1":
        print("[report] 输入不是 bookmark-doctor.tree-v1: %s" % args.tree, file=sys.stderr)
        return 2
    check_payload, err = _load_json_file(args.check, "[report] check.json")
    if err:
        print(err, file=sys.stderr)
        return 2
    dedupe_payload = None
    if args.dedupe:
        dedupe_payload, err = _load_json_file(args.dedupe, "[report] dedupe.json")
        if err:
            print(err, file=sys.stderr)
            return 2
    try:
        ruleset = load_ruleset(_REPO_ROOT, args.rules)
    except (RulesetError, OSError, ValueError) as exc:
        print("[report] 规则包不可用: %s" % exc, file=sys.stderr)
        return 2
    try:
        tiers = load_aging_tiers(ruleset)
    except AgingConfigError as exc:
        print("[report] 规则包 aging 配置不可用: %s" % exc, file=sys.stderr)
        return 2
    # 参考日：显式参数 > check 的 probe_date > 当天（确定性产物要求基准传定值）
    aging_date_arg = args.aging_date or check_payload.get("probe_date")
    if aging_date_arg:
        import datetime

        try:
            aging_date = datetime.date.fromisoformat(aging_date_arg)
        except ValueError:
            print("[report] 参考日非法（须 YYYY-MM-DD）: %s" % aging_date_arg, file=sys.stderr)
            return 2
    else:
        import datetime

        aging_date = datetime.date.today()
    profile = build_aging_profile(tree.get("bookmarks", []), tiers, aging_date)
    html = render_report(
        check_payload,
        dedupe_payload,
        profile,
        tree_bookmarks=tree.get("bookmarks", []),
    )
    target = Path(args.out) if args.out else Path("report.html")
    try:
        write_atomic(target, html)
    except OSError as exc:
        print("[report] 输出不可写 %s: %s" % (target, exc), file=sys.stderr)
        return 2
    print("[report] 已写入 %s" % target, file=sys.stderr)
    return 0


def _cmd_export(args) -> int:
    from bookmark_doctor.export import export_netscape, filter_bookmarks
    from bookmark_doctor.serialize import write_atomic

    tree, err = _load_json_file(args.tree, "[export] tree.json")
    if err:
        print(err, file=sys.stderr)
        return 2
    if tree.get("schema") != "bookmark-doctor.tree-v1":
        print("[export] 输入不是 bookmark-doctor.tree-v1: %s" % args.tree, file=sys.stderr)
        return 2
    if args.apply_dedupe and not args.dedupe:
        print("[export] --apply-dedupe 需要 --dedupe 产物", file=sys.stderr)
        return 2
    if args.exclude_dead and not args.check:
        print("[export] --exclude-dead 需要 --check 产物", file=sys.stderr)
        return 2
    dedupe_payload = None
    if args.dedupe:
        dedupe_payload, err = _load_json_file(args.dedupe, "[export] dedupe.json")
        if err:
            print(err, file=sys.stderr)
            return 2
    check_payload = None
    if args.check:
        check_payload, err = _load_json_file(args.check, "[export] check.json")
        if err:
            print(err, file=sys.stderr)
            return 2
    bookmarks = filter_bookmarks(
        tree.get("bookmarks", []),
        dedupe_payload=dedupe_payload,
        check_payload=check_payload,
        apply_dedupe=args.apply_dedupe,
        exclude_dead=args.exclude_dead,
    )
    data = export_netscape(bookmarks)
    target = Path(args.out) if args.out else Path("bookmarks-export.html")
    try:
        write_atomic(target, data)
    except OSError as exc:
        print("[export] 输出不可写 %s: %s" % (target, exc), file=sys.stderr)
        return 2
    print(
        "[export] 已写入 %s（导出 %d / 共 %d 条）"
        % (target, len(bookmarks), len(tree.get("bookmarks", []))),
        file=sys.stderr,
    )
    return 0


class _Args:
    """run 编排的 args 传递对象（字段与各子命令 argparse 定义对齐）。"""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _cmd_run(args) -> int:
    """全链路编排（单一源）：直接复用各子命令实现，无第二份判定逻辑。"""
    out_dir = Path(args.out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print("[run] 输出目录不可建 %s: %s" % (out_dir, exc), file=sys.stderr)
        return 2
    steps = []
    steps.append(("import", _cmd_import, _Args(
        files=list(args.files), out=str(out_dir / "tree.json"))))
    steps.append(("check", _cmd_check, _Args(
        tree=str(out_dir / "tree.json"), rules=args.rules,
        probe_date=args.probe_date, out=str(out_dir / "check.json"))))
    steps.append(("dedupe", _cmd_dedupe, _Args(
        tree=str(out_dir / "tree.json"),
        check=str(out_dir / "check.json"), rules=args.rules,
        out=str(out_dir / "dedupe.json"))))
    steps.append(("report", _cmd_report, _Args(
        tree=str(out_dir / "tree.json"), check=str(out_dir / "check.json"),
        dedupe=str(out_dir / "dedupe.json"), rules=args.rules,
        aging_date=args.probe_date, out=str(out_dir / "report.html"))))
    steps.append(("export", _cmd_export, _Args(
        tree=str(out_dir / "tree.json"), dedupe=str(out_dir / "dedupe.json"),
        check=str(out_dir / "check.json"), apply_dedupe=args.apply_dedupe,
        exclude_dead=args.exclude_dead,
        out=str(out_dir / "bookmarks-export.html"))))
    for name, handler, step_args in steps:
        code = handler(step_args)
        if code != 0:
            print("[run] 步骤 %s 失败（exit %d），停止编排" % (name, code), file=sys.stderr)
            return code
    print(
        "[run] 完成：%s" % ", ".join(
            str(out_dir / name)
            for name in ("tree.json", "check.json", "dedupe.json",
                         "report.html", "bookmarks-export.html")
        ),
        file=sys.stderr,
    )
    return 0


def main(argv=None) -> int:
    ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.command == "import":
        return _cmd_import(args)
    if args.command == "check":
        return _cmd_check(args)
    if args.command == "dedupe":
        return _cmd_dedupe(args)
    if args.command == "report":
        return _cmd_report(args)
    if args.command == "export":
        return _cmd_export(args)
    if args.command == "run":
        return _cmd_run(args)
    # 未指定任何动作：打印帮助并返回用法错误码（与"子命令必需"形态一致）。
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""bookmark-doctor 命令行入口。

骨架期提供 ``--version`` 与 ``--selftest``；``import`` 子命令随 M2 开放；
其余业务子命令（check / dedupe / report / export / run）按里程碑逐步开放，
计划见 ``plan/06-里程碑与每周演示.md``。

退出码契约（锁定进测试，plan/03 §8）：
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
            "子命令（import 已开放；check / dedupe / report / export / run 随里程碑开放），"
            "计划见 plan/06-里程碑与每周演示.md。"
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
    # 未指定任何动作：打印帮助并返回用法错误码（与"子命令必需"形态一致）。
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

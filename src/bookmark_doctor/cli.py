"""bookmark-doctor 命令行入口。

骨架期提供 ``--version`` 与 ``--selftest``；业务子命令
（import / check / dedupe / report / export / run）按里程碑逐步开放，
计划见 ``plan/06-里程碑与每周演示.md``。

退出码契约（锁定进测试）：
- 0 = 运行完成（含"体检发现问题"——问题进报告，不是错误）
- 2 = 用法错误 / 无参数 / 输入不可用
- ``--selftest``：0 通过 / 1 失败
"""

import argparse
import json
import platform
import sys

from bookmark_doctor import __version__
from bookmark_doctor._encoding import ensure_utf8_stdio

_APP = "bookmark-doctor"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_APP,
        description=(
            "收藏夹体检工具（中文站点友好）：失效检测 / 重复合并 / 长期未访问画像 / 一键导回。"
            "纯本地、零上传、运行时零第三方依赖。"
        ),
        epilog=(
            "子命令（import / check / dedupe / report / export / run）随里程碑逐步开放，"
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


def main(argv=None) -> int:
    ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.selftest:
        return _selftest()
    # 未指定任何动作：打印帮助并返回用法错误码（与后续"子命令必需"形态一致）。
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

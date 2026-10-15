"""标准流编码守卫（全入口共用）。

设计口径（既定口径 K8）：
- 按 ``stream.encoding`` 探针决定是否 reconfigure 为 UTF-8；
- 中文控制台（cp936 等能表达中文的编码）保持不动——不改变用户终端现状；
- 无法判定的流（无 encoding / 无 reconfigure）不动。

所有会打印的执行入口（主 CLI 与 tools/ 下每个脚本）在输出前调用
``ensure_utf8_stdio()``。
"""

import sys

_CJK_PROBE = "中文"


def _can_encode_cjk(stream) -> bool:
    encoding = getattr(stream, "encoding", None)
    if not encoding:
        return True  # 判定不了 → 不动
    try:
        _CJK_PROBE.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def ensure_utf8_stdio() -> None:
    """若 stdout/stderr 无法输出中文，则改配为 UTF-8（其余情况不动）。"""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        if _can_encode_cjk(stream):
            continue
        try:
            stream.reconfigure(encoding="utf-8")
        except (ValueError, OSError, AttributeError):
            pass

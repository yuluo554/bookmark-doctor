"""确定性输出写盘（M3）：check.json / dedupe.json 共用。

序列化纪律沿用 K18：``sort_keys=True`` + ``ensure_ascii=False`` + 缩进 2 +
LF 行尾 + 结尾换行；无时间戳/时钟/随机——同输入逐字节一致。
写盘用 write_bytes（``Path.write_text(newline=)`` 是 3.10+ 参数，E-11 禁用）。
"""

import json

from bookmark_doctor.parse.errors import ParseError


def serialize_payload(payload):
    """dict → 确定性字节（与 model.serialize_tree 同一纪律，不第二份实现）。"""
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        + b"\n"
    )


def write_atomic(path, data):
    """先全量序列化成功才写盘（不落半成品语义）；OSError 向上（CLI exit 2）。"""
    with open(path, "wb") as handle:
        handle.write(data)

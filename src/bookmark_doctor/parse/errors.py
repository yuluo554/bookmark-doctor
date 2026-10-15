"""解析层公共异常（M2）。

"文件不能用"的唯一异常通道：坏 HTML 结构 / 坏 JSON / 缺关键字段 /
Chrome 纪元常量缺失，全部抛 :class:`ParseError`，由 CLI 捕获后
stderr 人读消息 + 退出码 2（plan/03 §8、plan/04 §1.2）。
"""


class ParseError(Exception):
    """文件级解析失败（对应退出码 2，不落半成品）。"""

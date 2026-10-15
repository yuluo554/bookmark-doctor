"""解析层（M2）：Netscape Bookmark HTML 与 Chrome/Edge Bookmarks JSON。

公共契约：
- :class:`ParseError`——一切"文件不能用"（坏结构 / 坏 JSON / 缺关键字段）
  的唯一异常类型；CLI 捕获后 stderr 人读消息 + 退出码 2（plan/03 §8）；
- 两个解析器都是**纯函数**：输入文本，输出条目字典列表，不触盘、无时钟；
- "未知不猜补"（K2）：缺失/非法字段一律落 ``None``，绝不填默认值；
- Chrome 纪元换算常量的唯一正本在 ``data/fixtures/set-1/manifest.json``
  的 ``chrome_epoch_delta_us``（冻结口径 K12）；解析器不接受任何字面常量，
  由调用方（model.load_chrome_epoch_delta）显式传入。
"""

from bookmark_doctor.parse.errors import ParseError

__all__ = ["ParseError"]

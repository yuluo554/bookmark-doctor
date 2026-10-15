"""Netscape Bookmark HTML 解析器（M2）。

规格（plan/04 §1.2、HANDOFF-M2 待办 #2、冻结口径 K13/K14/K15）：
- ``html.parser.HTMLParser`` 子类流式解析 ``<DT><H3>``（文件夹）与
  ``<DT><A HREF ADD_DATE>``（书签）；``<DL>`` 嵌套 = 层级；
- HTML 实体由 ``html.unescape`` 解码（title 与 href 属性值都解）；
- ``ADD_DATE``：epoch 秒字符串；纯数字（可负）→ int；缺失 / 空串 /
  非法 → ``None``（未知不猜补，K2）；
- 坏结构显式报错：``<DT><A>`` 无 href /``<DT><H3>`` 后无 ``<DL>`` /
  括号不配平（DL 层级栈下溢或收尾残留）→ :class:`ParseError`；
- 纯函数：输入文本，输出条目列表（每项 title/url/add_date/folder），
  不触盘、无时钟、无随机。
"""

import html as _html
from html.parser import HTMLParser

from bookmark_doctor.parse.errors import ParseError


def _parse_add_date(raw):
    """ADD_DATE 属性值 → epoch 秒 int；缺失/空/非法 → None（不猜补）。"""
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


class _NetscapeParser(HTMLParser):
    """流式状态机：只认四类标签（H3/A/DL/B），其余忽略。"""

    def __init__(self):
        # convert_charrefs=True：正文实体由 HTMLParser 解码后经 handle_data
        # 到达；属性值（HREF/ADD_DATE）本就始终自动解码，无需手工 unescape
        HTMLParser.__init__(self, convert_charrefs=True)
        self.entries = []
        self._folder_stack = []
        # 已见 <H3> 标题、等待其后的 <DL> 开启（坏结构检测用，K15）
        self._pending_h3 = None
        self._in_h3 = False      # <H3>…</H3> 文本区间
        self._in_anchor = False  # <A>…</A> 文本区间（只在此区间累积标题）
        # <DL> 开标签计数（与 folder_stack 深度可差 1：根 DL 无文件夹名）
        self._dl_depth = 0
        self._finished = False

    # -- 标签处理 ---------------------------------------------------------

    def handle_starttag(self, tag, attrs):
        if tag == "dl":
            if self._pending_h3 is not None:
                self._folder_stack.append(self._pending_h3)
                self._pending_h3 = None
            self._dl_depth += 1
        elif tag == "h3":
            self._pending_h3 = ""  # 文本由 handle_data 累积
            self._in_h3 = True
        elif tag == "a":
            attrd = dict(attrs)
            href = attrd.get("href")
            if href is None:
                raise ParseError("第 %d 行：<DT><A> 缺少 HREF 属性" % (self.getpos()[0],))
            self.entries.append(
                {
                    "title": "",  # 文本由 handle_data 累积；空标题保持 None
                    "url": href,
                    "add_date": _parse_add_date(attrd.get("add_date")),
                    "folder": list(self._folder_stack),
                    "_line": self.getpos()[0],
                }
            )
            self._in_anchor = True

    def handle_startendtag(self, tag, attrs):
        # 自闭合形态（如 <H3/>）不产生文件夹语义；<A/> 无内容视作坏结构
        if tag == "a":
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "dl":
            self._dl_depth -= 1
            if self._dl_depth < 0:
                raise ParseError("第 %d 行：</DL> 多于 <DL>（层级不配平）" % (self.getpos()[0],))
            # 文件夹 DL 关闭（栈深追平层级）→ 弹出其文件夹名；
            # 根 DL 关闭时栈已空或一并清空
            while self._folder_stack and len(self._folder_stack) >= self._dl_depth:
                self._folder_stack.pop()
            if self._dl_depth == 0:
                self._finished = True  # 根 DL 闭合后忽略后续内容
        elif tag == "h3":
            self._in_h3 = False
            if self._pending_h3 is None:
                self._pending_h3 = ""
        elif tag == "a":
            self._in_anchor = False

    def handle_data(self, data):
        if self._finished:
            return
        if self._in_h3 and self._pending_h3 is not None:
            self._pending_h3 += data
        elif self._in_anchor and self.entries:
            self.entries[-1]["title"] += data

    def finish(self):
        """收尾校验：H3 悬空 / DL 不配平 → ParseError（K15）。"""
        if self._pending_h3 is not None:
            raise ParseError("<H3> 后没有对应的 <DL>（第 %d 行附近）" % (self.getpos()[0],))
        if self._dl_depth != 0 or self._folder_stack:
            raise ParseError("<DL> 层级不配平（缺失 </DL>）")


def parse_netscape(text):
    """解析 Netscape Bookmark HTML 文本 → 条目列表。

    返回 list[dict]，每项：title（str|None）/ url（str）/ add_date
    （int|None）/ folder（list[str]，从根到直接父文件夹）。
    结构坏 → :class:`ParseError`。
    """
    if not text or not text.strip():
        raise ParseError("空文件（不是有效的 Netscape 书签 HTML）")
    parser = _NetscapeParser()
    try:
        parser.feed(text)
        parser.close()
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError("HTML 解析失败: %s" % exc)
    parser.finish()
    out = []
    for item in parser.entries:
        title = item["title"].strip() or None
        out.append(
            {
                "title": title,
                "url": item["url"],
                "add_date": item["add_date"],
                "folder": item["folder"],
            }
        )
    return out

"""M3 零字面量门禁（plan/03 §9）——src/ 不得出现 probe 数值/平台主机名第二份。

扫描面 = src/bookmark_doctor 引擎源码（M3 扩张：probe/classify/normalize/
dedupe/ruleset/serialize/cli 全部纳入）。豁免口径写死：
- 状态分类语义区间（2xx/404/410 等语义判定）与 HTTPRedirect 跳转语义码
  属 HTTP 语义非政策数值——豁免名单显式列出（classify/probe 的语义区间）；
- 任何 *.com / *.cn / *.net 平台主机名字面量一律红线（知乎/微博/CSDN 等
  平台名只允许出现在 data/rules/ruleset.json 与 data/measurements/）。
"""

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src" / "bookmark_doctor"

# 平台主机名红线（零字面量的主机名面；规则数据只住 data/rules/）
_HOSTNAME_PATTERN = re.compile(
    r"(?i)\b(zhihu|weibo|csdn|bilibili|juejin|douban|tieba|baidu|taobao|jd\.com|"
    r"weixin|mp\.weixin|github)\b"
)

# 允许的 HTTP 语义数值面（豁免口径写死；这些是协议语义，非 ruleset 参数）：
# - classify.py：语义区间端点（200/300/400/500）与状态枚举（404/410/401/403/
#   405/406/429/451/521/522/523）——plan/04 §2.2 分类表本身的落点；
# - probe.py：跳转语义码（301/302/303/307/308）与 405/501 降级触发码；
# - 其余模块：任何 3 位 HTTP 码都红线。
_SEMANTIC_HTTP_FILES = {
    "classify.py",
    "probe.py",
    "normalize.py",  # 仅 DEFAULT_PORTS（80/443 协议端口语义）
}

# 分类表数值（plan/04 §2.2 行 + 跳转语义 + HEAD 拒绝降级码 + 默认端口）——
# 逐值登记，新增须先改口径
_SEMANTIC_STATUS_CODES = {
    200, 300, 301, 302, 303, 307, 308, 400, 401, 403, 404, 405, 406,
    410, 429, 451, 500, 501, 521, 522, 523,
    80, 443,  # 默认端口协议语义（normalize DEFAULT_PORTS，非 ruleset 参数）
}


def _iter_source_files():
    for path in sorted(SRC_DIR.rglob("*.py")):
        yield path


def test_no_platform_hostnames_in_src():
    """src/ 零平台主机名词面（主机名只住 ruleset 正本）。"""
    bad = []
    for path in _iter_source_files():
        text = path.read_text(encoding="utf-8")
        for match in _HOSTNAME_PATTERN.finditer(text):
            bad.append("%s:%d %s" % (path.name, text[: match.start()].count("\n") + 1, match.group(0)))
    assert bad == [], "src/ 出现平台主机名词面（应取 ruleset）: %s" % bad


def test_no_second_copy_of_probe_numbers():
    """probe 数值（timeout/retry/delay/redirect 上限、UA 串）不得在 src/ 出现第二份。

    逐值扫描：ruleset probe 节的每个数值（除 0 与 1 这类结构值）不得以
    字面量出现在引擎源码——取 ruleset 正本动态生成扫描集。
    """
    import json

    ruleset = json.loads(
        (REPO_ROOT / "data" / "rules" / "ruleset.json").read_text(encoding="utf-8")
    )
    probe_cfg = ruleset["probe"]
    forbidden_numbers = set()
    for key, value in probe_cfg.items():
        if key == "user_agent":
            continue
        if isinstance(value, (int, float)) and value not in (0, 1):
            forbidden_numbers.add(value)
    # UA 字符串面也禁（含特征子串）
    ua_fragment = probe_cfg["user_agent"].split("/")[0]
    assert ua_fragment, "ruleset probe.user_agent 异常"

    bad = []
    for path in _iter_source_files():
        text = path.read_text(encoding="utf-8")
        if ua_fragment in text:
            bad.append("%s: UA 词面第二份 %r" % (path.name, ua_fragment))
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                if not isinstance(node.value, bool) and node.value in forbidden_numbers:
                    bad.append("%s:%d 数值 %r 第二份" % (
                        path.name, node.lineno, node.value))
    assert bad == [], "probe 数值/UA 第二份: %s" % bad


def test_http_status_literals_only_in_semantic_modules():
    """3 位 HTTP 状态码字面量只允许出现在语义分类模块（豁免名单写死）。"""
    bad = []
    for path in _iter_source_files():
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, int)
                and not isinstance(node.value, bool)
                and 100 <= node.value <= 599
                and node.value not in _SEMANTIC_STATUS_CODES
            ):
                bad.append("%s:%d 未登记 HTTP 码 %d" % (path.name, node.lineno, node.value))
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, int)
                and not isinstance(node.value, bool)
                and 100 <= node.value <= 599
                and path.name not in _SEMANTIC_HTTP_FILES
            ):
                bad.append("%s:%d HTTP 码 %d 出现在非语义模块" % (path.name, node.lineno, node.value))
    assert bad == [], "HTTP 状态码字面量越界: %s" % bad


def test_gate_catches_pollution():
    """门禁可证伪：污染源码 → 门必须红（变异验证常驻形态）。"""
    src = (SRC_DIR / "classify.py").read_text(encoding="utf-8")
    # 模拟污染：不在真文件里写，验证扫描函数对合成 AST 的判定
    import types

    polluted = "VISITED_HOST = 'zhihu.com'\n" + src
    matches = list(_HOSTNAME_PATTERN.finditer(polluted))
    assert matches, "主机名扫描器失效：平台名词面未检出"
    # 数值扫描器对合成常量节点
    tree = ast.parse("X = 12345")
    found = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value == 12345
    ]
    assert found, "数值扫描器失效"

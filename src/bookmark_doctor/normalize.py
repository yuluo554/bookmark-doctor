"""URL 规范化（M3）——比较键专用单点实现。

规格出处：plan/04 §3.1 六步流水线 [冻结草案落地]；HANDOFF-M3 待办 #3。

纪律：
- **原始 URL 永不改写**——normalize 结果只作比较键；
- 追踪参数名单取 ruleset ``tracked_query_params``（exact + prefixes），不写第二份；
- 未实测短链不猜：``shortlink_known`` 映射由调用方（dedupe）注入，
  本模块不解析短链目标；
- 六步**固定顺序**：scheme → host/端口 → 路径 → 查询串 → fragment → final_url。

3.8 兼容：不使用 ``removeprefix`` / ``|`` 合并等 3.9+ 语法。
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DEFAULT_PORTS = {"http": 80, "https": 443}  # 协议语义端口（非 ruleset 参数）


def _is_tracked(name, exact, prefixes):
    if name in exact:
        return True
    for prefix in prefixes:
        if name.startswith(prefix):
            return True
    return False


def normalize_url(url, tracked_params, shortlink_known=None):
    """URL 原文 → 比较键（六步流水线，固定顺序）。

    ``tracked_params``：ruleset ``tracked_query_params`` 节
    （{"exact": [...], "prefixes": [...]}，缺失按空表处理）。
    ``shortlink_known``：{原 URL: 目标 URL} 已实测短链映射（ruleset 节，
    M3 阶段 ruleset 未收录 → 传 None 即不启用该步，不猜）。
    """
    exact = list((tracked_params or {}).get("exact", []))
    prefixes = list((tracked_params or {}).get("prefixes", []))

    # 第 0 步（映射）：已实测短链 → 比较键用映射目标（plan/04 §3.1 第 6 步前半）；
    # 未收录 → 不猜，按原 URL 继续流水线。
    if shortlink_known and url in shortlink_known:
        url = shortlink_known[url]

    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    # 第 1 步：scheme 归一 http → https（比较键层面）
    original_scheme = scheme
    if scheme == "http":
        scheme = "https"
    # 第 2 步：host 小写；去默认端口（按**原 scheme** 的默认端口判——
    # http://host:80 归一为 https://host，而非保留 80 变成 https 非默认端口）
    hostname = (parts.hostname or "").lower()
    port = parts.port
    if port is not None and DEFAULT_PORTS.get(original_scheme) == port:
        port = None
    netloc = hostname if port is None else "%s:%d" % (hostname, port)
    # 第 3 步：路径——连续斜杠折叠；去尾斜杠（根路径除外）
    path = parts.path or ""
    while "//" in path:
        path = path.replace("//", "/")
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    # 第 4 步：查询串——剥离追踪参数 → 按键名排序重序列化
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracked(k, exact, prefixes)
    ]
    query_pairs.sort()
    query = urlencode(query_pairs)
    # 第 5 步：fragment 剥离（仅 fragment 不同的 URL 归入同组，组上另附标记）
    return urlunsplit((scheme, netloc, path, query, ""))


def fragment_of(url):
    """URL 原文的 fragment（不含 #；无 → None）。fragment_variant 标记用。"""
    parts = urlsplit(url)
    return parts.fragment or None

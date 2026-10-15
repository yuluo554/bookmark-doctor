"""HTTP 探测引擎（M3）——单次逻辑探测。

规格出处：plan/03 §3（urllib 自写 handler）、plan/04 §2.1、HANDOFF-M3 待办 #1。

语义（冻结口径，plan/04 §2.1）：
- 每个 URL **一次逻辑探测**：先 HEAD；405/501 → 降级 GET 限读即断——
  HEAD 与降级 GET **合计算一次**，不算二次探测；
- 不携带 cookies/凭据；UA 取 ruleset ``probe.user_agent``（单点，不写第二份）；
- 跟随跳转至 ``probe.redirect_max`` 上限并记录跳转链；超限/成环 →
  错误类 ``too_many_redirects`` / ``redirect_loop``（classify 落 review）；
- timeout_s / retry_max / delay_s 全取 ruleset；串行 + 请求间隔降频。

HTTP 通路用 ``urllib.request``（零第三方依赖）；redirect 不用默认
``HTTPRedirectHandler`` 行为——自写循环以记录完整跳转链、显式识别
成环与超限（可审计，plan/03 §3）。

错误类（error_class，classify 消费；plan/04 §2.2——网络不可达 ≠ 失效）：
``dns_failure`` / ``connect_timeout`` / ``read_timeout`` / ``tls_error`` /
``connection_error`` / ``too_many_redirects`` / ``redirect_loop``。
4xx/5xx 终态不是网络错误，走 ``http_status`` 通路。
"""

import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

# HEAD 被拒（405/501）后降级 GET 的最大读取字节数（限读即断，不落正文）
_GET_DRAIN_LIMIT = 1024


class ProbeResult(object):
    """单 URL 探测记录（check.json 条目形态，plan/04 §2.1 字段）。"""

    __slots__ = ("url", "final_url", "redirect_chain", "http_status", "error_class")

    def __init__(self, url):
        self.url = url
        self.final_url = None
        self.redirect_chain = []
        self.http_status = None
        self.error_class = None

    def as_dict(self):
        return {
            "url": self.url,
            "final_url": self.final_url,
            "redirect_chain": list(self.redirect_chain),
            "http_status": self.http_status,
            "error_class": self.error_class,
        }


def _opener():
    """不自动跟随跳转的 opener（跳转由引擎自写循环显式处理）。"""

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    return urllib.request.build_opener(_NoRedirect())


def _classify_network_error(exc):
    """网络层异常 → error_class。"""
    if isinstance(exc, ssl.SSLError):
        return "tls_error"
    if isinstance(exc, urllib.error.URLError):
        return _classify_network_error(exc.reason)
    if isinstance(exc, socket.gaierror):
        return "dns_failure"
    if isinstance(exc, socket.timeout) or isinstance(exc, TimeoutError):
        # socket.timeout 在 3.10+ 是 TimeoutError / OSError 子类；3.8 独立。
        # 读超时（request 已发出、response.read 阶段）也归此——无法区分更细，保守同码。
        return "read_timeout"
    if isinstance(exc, ConnectionError):
        return "connection_error"
    if isinstance(exc, OSError):
        # 其余 OS 网络层错误（拒绝连接/不可达等）统一连接类
        return "connection_error"
    return "connection_error"


def _is_redirect(code):
    return code in (301, 302, 303, 307, 308)


def _single_request(opener, url, method, timeout_s, user_agent):
    """发一次请求 → (status, final_url, headers)；网络层异常向上抛。

    4xx/5xx 经 HTTPError 携带状态码——按"终态响应"消费（不是错误）。
    """
    request = urllib.request.Request(url, method=method, headers={"User-Agent": user_agent})
    try:
        response = opener.open(request, timeout=timeout_s)
        try:
            return response.status, response.geturl(), dict(response.headers)
        finally:
            response.close()
    except urllib.error.HTTPError as exc:
        try:
            headers = dict(exc.headers or {})
            return exc.code, url, headers
        finally:
            exc.close()


def _drain(response, limit):
    """限读即断：最多读 limit 字节。"""
    try:
        response.read(limit)
    except Exception:
        pass


def probe_url(url, probe_cfg, opener=None):
    """探测一个 URL → ProbeResult（一次逻辑探测语义）。

    ``probe_cfg``：ruleset ``probe`` 节（timeout_s / retry_max / delay_s /
    redirect_max / user_agent——全部单点取用）。
    网络层失败不抛出：落 ``error_class``（单 URL 失败不中断整批，plan/04 §2.4）。
    """
    user_agent = probe_cfg.get("user_agent", "")
    timeout_s = probe_cfg.get("timeout_s")
    retry_max = int(probe_cfg.get("retry_max", 0))
    redirect_max = int(probe_cfg.get("redirect_max"))
    delay_s = float(probe_cfg.get("delay_s", 0))
    if timeout_s is None:
        raise ValueError("ruleset probe.timeout_s 缺失（单点口径，不设引擎默认值）")
    if opener is None:
        opener = _opener()

    result = ProbeResult(url)
    current = url

    for attempt in range(retry_max + 1):
        if attempt:
            time.sleep(delay_s)
        seen = []  # 成环检测范围 = 单次逻辑探测的跳转链（重试另起新链）
        hops = 0
        while True:
            if current in seen:
                result.error_class = "redirect_loop"
                return result
            seen.append(current)
            try:
                status, final, headers = _single_request(
                    opener, current, "HEAD", timeout_s, user_agent
                )
            except Exception as exc:  # 网络层失败（HTTPError 已在下游消费）
                if attempt < retry_max:
                    break  # 重试：另起一次 attempt（HEAD 从头再来）
                result.error_class = _classify_network_error(exc)
                return result
            if _is_redirect(status):
                location = headers.get("Location") or ""
                if not location:
                    # 3xx 无 Location：无法跟随 → 按终态 status 通路返回
                    result.http_status = status
                    result.final_url = current
                    return result
                current = urllib.parse.urljoin(current, location)
                result.redirect_chain.append(current)
                hops += 1
                if hops > redirect_max:
                    result.error_class = "too_many_redirects"
                    return result
                continue
            if status in (405, 501):
                # HEAD 被拒 → 降级 GET 限读即断（与 HEAD 合计算一次逻辑探测）
                request = urllib.request.Request(
                    current, headers={"User-Agent": user_agent}
                )
                try:
                    response = opener.open(request, timeout=timeout_s)
                    with response:
                        status = response.status
                        _drain(response, _GET_DRAIN_LIMIT)
                except urllib.error.HTTPError as exc:
                    with exc:
                        status = exc.code
                        _drain(exc, _GET_DRAIN_LIMIT)
                except Exception as exc:
                    if attempt < retry_max:
                        break
                    result.error_class = _classify_network_error(exc)
                    return result
            # 终态（非 3xx）：
            result.http_status = status
            result.final_url = current
            return result
    # 不可达（retry 耗尽走不到这——最后一轮必返回）；防御性收口：
    result.error_class = "connection_error"
    return result


def probe_bookmarks(urls, probe_cfg, progress=None):
    """批量串行探测（请求间隔 delay_s 降频）→ [探测记录 dict]。

    ``progress``：可选回调 (index, total, url)——CLI 进度展示用。
    """
    delay = float(probe_cfg.get("delay_s", 0))
    opener = _opener()
    results = []
    for index, url in enumerate(urls):
        if progress:
            progress(index, len(urls), url)
        results.append(probe_url(url, probe_cfg, opener=opener).as_dict())
        if delay and index < len(urls) - 1:
            time.sleep(delay)
    return results

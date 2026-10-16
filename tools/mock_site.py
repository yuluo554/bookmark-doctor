"""本地 mock 站点（M1 雏形；M4 基准复用）。

按路径脚本化响应（plan/05 §4.3）：
- ``/status/403``、``/status/521`` … → 对应状态码（200/301/302/403/404/405/410/521；
  405 供 HEAD→GET 降级语义场景——M3 补全，M3 前不在集内）；3xx 场景**发 Location 头**
  跳到 ``/final/200``（真实跳转链，首跳 3xx → 终态 200）；
- ``/redirect/302`` → 302 跳到 ``/final/200``（模拟风控跳转链）；
- ``/redirect/301`` → 301 跳到 ``/final/200``；
- ``/redirect/loop`` → 302 自环（跳转成环场景）；
- ``/hang`` → 挂起（读取超时场景；阻塞至客户端断开——客户端超时即触发其超时语义）；
- 其余路径 → 404。

纪律：**仅 loopback**（默认 127.0.0.1；显式拒绝绑定 0.0.0.0）；无正文内容
（body 只有状态行说明）；无系统时钟依赖（除挂起时长参数）。

用法（仓库根运行）：
    PYTHONPATH=src py -X utf8 tools/mock_site.py [--port 0] [--hang-seconds 30]

退出码：Ctrl+C / SIGTERM 正常停止返回 0。
"""

import argparse
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bookmark_doctor._encoding import ensure_utf8_stdio

_STATUS_CODES = (200, 301, 302, 403, 404, 405, 410, 521)


class MockHandler(BaseHTTPRequestHandler):

    def _respond(self, code, extra_headers=None):
        body = ("mock: %d\n" % code).encode("ascii")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=ascii")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _hang(self):
        # 自旋读取客户端断开：客户端超时断连后立即结束（不依赖系统时钟差值）
        try:
            while self.rfile.readline(64):
                pass
        except (ConnectionError, OSError):
            pass

    def do_GET(self):
        path = self.path.split("?", 1)[0].strip("/")
        parts = path.split("/") if path else []

        if len(parts) == 2 and parts[0] == "status" and parts[1].isdigit():
            code = int(parts[1])
            if code in _STATUS_CODES:
                # 3xx 场景发 Location 头 → 真实跳转链（首跳 3xx → 终态 200），
                # 与 tools/bench.py mock 同语义（风控 302 场景复现前提）
                headers = {"Location": "/final/200"} if code in (301, 302) else None
                self._respond(code, headers)
                return
            self._respond(404)
            return

        if len(parts) == 2 and parts[0] == "redirect" and parts[1] in ("301", "302"):
            code = int(parts[1])
            self._respond(code, {"Location": "/final/200"})
            return

        if path == "redirect/loop":
            self._respond(302, {"Location": "/redirect/loop"})
            return

        if len(parts) == 2 and parts[0] == "final" and parts[1] == "200":
            self._respond(200)
            return

        if path == "hang":
            self._hang()
            self._respond(200)
            return

        self._respond(404)

    do_HEAD = do_GET

    def log_message(self, fmt, *args):  # 静默：不刷屏，也避免 stderr 时序依赖
        pass


def _assert_loopback(host):
    infos = socket.getaddrinfo(host, None)
    for info in infos:
        if not ipaddress_loopback(info[4][0]):
            raise SystemExit("拒绝启动：mock 站点仅允许 loopback 地址（got %s）" % info[4][0])


def ipaddress_loopback(ip):
    # 3.8 兼容的极简 loopback 判定（不引依赖）：IPv4 127.0.0.0/8 或 IPv6 ::1
    if ":" in ip:
        return ip == "::1"
    parts = ip.split(".")
    return len(parts) == 4 and parts[0] == "127"


def main(argv=None) -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="本地 mock 站点（仅 loopback）")
    parser.add_argument("--host", default="127.0.0.1", help="默认 127.0.0.1；仅允许 loopback")
    parser.add_argument("--port", type=int, default=0, help="0 = 运行时分配（默认）")
    args = parser.parse_args(argv)

    _assert_loopback(args.host)
    server = ThreadingHTTPServer((args.host, args.port), MockHandler)
    # 端口信息打印到 stdout（端口运行时分配，不进任何冻结产物字节）
    print("[mock_site] listening on http://%s:%d" % server.server_address[:2])
    print("[mock_site] ready", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

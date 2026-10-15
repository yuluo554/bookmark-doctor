"""编码守卫测试：本机即可复现 CI 的 cp1252 场景与中文控制台（cp936）保持不动。"""

import io
import os
import subprocess
import sys

from bookmark_doctor._encoding import ensure_utf8_stdio


def _make_wrapper(encoding):
    return io.TextIOWrapper(io.BytesIO(), encoding=encoding, errors="strict")


def _patch_streams(monkeypatch, stream):
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", stream)


def test_reconfigures_stream_that_cannot_encode_cjk(monkeypatch):
    stream = _make_wrapper("cp1252")
    _patch_streams(monkeypatch, stream)
    ensure_utf8_stdio()
    assert (stream.encoding or "").lower().replace("-", "") == "utf8"


def test_keeps_cp936_console_untouched(monkeypatch):
    stream = _make_wrapper("cp936")
    _patch_streams(monkeypatch, stream)
    ensure_utf8_stdio()
    assert (stream.encoding or "").lower().replace("-", "") == "cp936"


def test_keeps_utf8_stream_untouched(monkeypatch):
    stream = _make_wrapper("utf-8")
    _patch_streams(monkeypatch, stream)
    ensure_utf8_stdio()
    assert (stream.encoding or "").lower().replace("-", "") == "utf8"


def test_selftest_survives_cp1252_stdio():
    """子进程真跑：PYTHONIOENCODING=cp1252 下自检必须 exit 0 且中文正常输出。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp1252"
    result = subprocess.run(
        [sys.executable, "-m", "bookmark_doctor", "--selftest"],
        capture_output=True,
        env=env,
    )
    assert result.returncode == 0
    text = result.stdout.decode("utf-8")
    assert "bookmark-doctor" in text
    assert "中文输出正常" in text

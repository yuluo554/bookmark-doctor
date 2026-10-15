"""CLI 冒烟与退出码契约测试（骨架期）。"""

import json
import subprocess
import sys

import pytest

from bookmark_doctor import __version__
from bookmark_doctor.cli import main


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()  # capsys 只能消费一次
    assert __version__ in captured.out


def test_help_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "usage" in captured.out.lower()


def test_no_args_shows_help_and_exit_2(capsys):
    assert main([]) == 2
    captured = capsys.readouterr()
    assert "usage" in captured.out.lower()


def test_selftest_passes(capsys):
    assert main(["--selftest"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip().splitlines()[-1])
    assert payload["name"] == "bookmark-doctor"
    assert payload["ok"] is True
    assert payload["version"] == __version__


def test_module_invocation():
    """模块形态通路（python -m）真跑子进程。"""
    result = subprocess.run(
        [sys.executable, "-m", "bookmark_doctor", "--version"],
        capture_output=True,
    )
    assert result.returncode == 0
    assert __version__.encode("ascii") in result.stdout


def test_installed_metadata_version_matches():
    """安装面版本一致性：以发行态安装时（README / CI 通路）必须与源码版本一致。"""
    try:
        from importlib.metadata import version as dist_version
    except ImportError:
        pytest.skip("importlib.metadata 不可用")
    try:
        installed = dist_version("bookmark-doctor")
    except Exception:
        pytest.skip("未以发行态安装（源码态运行）；装好后的版本一致性由 README / CI 安装通路核验")
    assert installed == __version__

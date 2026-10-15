"""工作流与仓库级守门测试。

- workflow 必须可被 YAML 解析（非法 YAML 会让 GitHub 静默不建任何 job）；
- 每个 job 必须有 runs-on 与 steps；
- 每个 actions/checkout step 必须 fetch-depth: 0（为历史扫描类守门预留；浅克隆会静默空验）。
"""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOW_DIR = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _load_workflows():
    files = sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))
    assert files, "未找到任何 workflow 文件"
    return files


def test_workflows_parse():
    for path in _load_workflows():
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"{path.name} 解析结果不是映射"
        # YAML 的 `on:` 会被解析为布尔键 True（YAML 1.1）
        triggers = data.get("on", data.get(True))
        assert triggers, f"{path.name} 缺少 on 触发器"
        jobs = data.get("jobs") or {}
        assert jobs, f"{path.name} 没有任何 job"
        for job_name, job in jobs.items():
            assert job.get("runs-on"), f"{path.name}::{job_name} 缺少 runs-on"
            steps = job.get("steps") or []
            assert steps, f"{path.name}::{job_name} 没有任何 step"


def test_checkout_steps_use_full_history():
    for path in _load_workflows():
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        jobs = data.get("jobs") or {}
        for job_name, job in jobs.items():
            for step in job.get("steps") or []:
                uses = step.get("uses") or ""
                if uses.startswith("actions/checkout"):
                    depth = (step.get("with") or {}).get("fetch-depth")
                    assert depth == 0, (
                        f"{path.name}::{job_name} 的 checkout 未配置 fetch-depth: 0；"
                        "浅克隆会让历史扫描类守门静默空验"
                    )

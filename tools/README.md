# tools/ — 生成器 / 基准 / 审计脚本

本目录存放**开发侧与发布侧工具**（不进用户命令面；用户 CLI 只保留用户要用的子命令）。

## 规划中的脚本

| 脚本 | 用途 | 里程碑 |
|---|---|---|
| `gen_ruleset.py` | 生成 / 校验 `data/rules/ruleset.json`（`--check` 位级一致守门） | M1 |
| `gen_fixtures.py` | 生成 / 校验合成书签集与植入真值（`--check` 位级一致守门） | M1 |
| `mock_site.py` | 本地 mock 站点（403/302/521/404/超时等反爬响应模拟；仅 loopback） | M1 |
| `bench.py` | 内置基准 runner（退出码三语义：0 达标 / 1 未达标 / 2 用法） | M4 |

## 纪律（新增脚本必须遵守）

1. **编码守卫**：脚本入口第一步调用 `ensure_utf8_stdio()`（`from bookmark_doctor._encoding import ensure_utf8_stdio`）；所有输出走 stdout/stderr 前先守卫。
2. **确定性**：禁 stdlib `random`、禁系统时钟、禁 set 迭代序；输出经显式 sort；写盘用 `write_bytes` / `newline="\n"`。
3. **Python 3.8 兼容**：项目底线 3.8（本机默认通道 3.8.8），不使用 3.9+ 语法/API。
4. **运行方式**：从仓库根运行（如 `py -X utf8 tools/bench.py`），依赖已安装的包（`pip install -e ".[dev]"`）或 `PYTHONPATH=src`。
5. 维护 / 发布类工具留在本目录，**不挂到用户 CLI**。

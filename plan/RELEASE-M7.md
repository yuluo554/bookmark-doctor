# RELEASE-M7 — v0.2.0 发布留档

> 生成：2026-10-20。三件套之三：发布决策与证据留档（另两件：tag + GitHub Release）。
> 措辞纪律：本文件随仓库公开，**不落个人路径 / 邮箱 / token 词面**。
> 前置留档见 `plan/RELEASE-M6.md`（v0.1.0）。

## 0. 版本与定位

| 项 | 值 |
|---|---|
| 版本 | **0.2.0**（minor；相对 0.1.0 有对外可感知的兼容性变更，见 §1） |
| 基线 | 上一发布 `v0.1.0`（tag 与 Release **保持不动**，仅新增 `v0.2.0`） |
| 变更规模 | 5 个受版本控制文件 + 版本号 + 本留档 |
| 是否重打包 | 是（新版本新产物）；`v0.1.0` 的两个附件**未动** |

## 1. 本版改了什么

| 类别 | 内容 | 对外影响 |
|---|---|---|
| 测试环境依赖（原 D1，P1） | `tests/test_probe.py` 的网络错误类测试改用**不走代理**的 opener fixture；断言未改 | 无（仅测试侧） |
| 依赖口径（原 D2） | README「测试期依赖仅 `pytest`」→「`pytest` + `pyyaml`」 | 无（文档） |
| license 元数据（原 D3，P1） | `license = "MIT"` + `project.license-files`；删 `License ::` classifier；`build-system` 下限抬到 `setuptools>=77` | 无（元数据） |
| CI 卫生（原 D4） | actions → `v7`（`node24`）；加 `concurrency`（仅非 main 分支取消旧 run） | 无（CI） |
| **解释器底线（DEC3′）** | `requires-python` 由 `>=3.8` **收紧到 `>=3.9`**；classifiers 去 3.8；CI 矩阵 `windows×3.8` → `windows×3.9` | **有**：Python 3.8 用户无法再安装本包 |

### 1.1 DEC3′ 的由来（与原始迭代建议不同，须留痕）

原迭代方案建议保持 `>=3.8`，同时把 license 改为 SPDX 字符串。**两者互斥**，实测依据：

- SPDX `project.license` 字符串（PEP 639）自 setuptools **77.0.0** 起支持；
- setuptools **76.0.0** 起 `requires-python` 即为 `>=3.9`，**75.3.2 是支持 py3.8 的最后一版**；
- 因此在 py3.8 上，SPDX 写法会在**构建元数据阶段直接报配置错误**，`pip install -e .` 无法完成。

真实安装实测（非推断）：

```
SPDX 写法 @ py3.8 → exit=1  ValueError: invalid pyproject.toml config: `project.license`
原 TOML 表写法 @ py3.8 → exit=0  Successfully installed
```

取舍：**抬底线到 3.9**（最小让步；3.9 通道可解析 setuptools 82.x，满足 `>=77`），
实测 setuptools 82.0.0 对该 pyproject 的元数据构建 **0 warning**，METADATA 写出 `License-Expression: MIT`。
最终结论由用户拍板（见 `update/03-执行记录.md` §一）。

## 2. 验证证据（本机实测）

| 项 | 结果 |
|---|---|
| 全量测试（3.12.10 通道，含代理环境） | **159 passed**（唯一项 `test_dns_failure` 由红转绿；退出码 0） |
| 干净环境复验（全新 venv + `pip install -e ".[dev]"`） | 安装退出码 0 / warning 0；**159 passed** |
| 元数据构建（setuptools 84.0.0 与 82.0.0 各一次） | **WARNINGS: []**（改前为 2 条 `SetuptoolsDeprecationWarning`） |
| 元数据字段 | `License-Expression: MIT`（PEP 639 生效） |
| 三通路冒烟 | `bookmark-doctor --version` / `--selftest` / `python -m bookmark_doctor --selftest` 均退出码 0 |
| workflow 守门测试 | `tests/test_meta.py` 2 passed（YAML 可解析 + `fetch-depth: 0` 在位） |
| 不变量 | `data/**`、`ruleset.json`、门槛与 `false_dead`/`false_alive` 0 硬门、退出码语义**未动** |

> 3.9 通道本身未在本机实跑（本机仅 3.8 / 3.12），以 setuptools 82.0.0 等价验证；
> CI 的 `windows×3.9` 腿为最终证据。

## 3. 发布物定案与留档

| 产物 | 说明 | 字节 | sha256 |
|---|---|---|---|
| `bookmark-doctor-0.2.0-source.zip` | 便携源码包（口径见 §5） | 500701 | `2e89709a99874354a349f1204ddf64f5ab154e04dc3db56b4add459871c4a14a` |
| `bookmark_doctor-0.2.0.tar.gz` | 标准 sdist（`python -m build --sdist`） | 72304 | `ad5159bf0894361c07b9dd01cceee6a52e381b3d3640b3ce30789a2079b9cc66` |

- 便携 zip **确定性验证**：同一规则两次打包**逐字节一致**（sha256 相同）。
- 便携 zip 自检：69 条目 / 单根目录 `bookmark-doctor-0.2.0/` / `ZIP_STORED` / 固定
  `date_time=(2026,10,20,0,0,0)` / **8 个非 ASCII 文件名全部 `flag_bits=0x800`** / 无 `RELEASE-*` 成员。
- 解包冒烟：解包后 `PYTHONPATH=src python -X utf8 -m bookmark_doctor --version` → `bookmark-doctor 0.2.0`（退出码 0）。

## 4. CI

- 矩阵：`windows-latest×3.9` + `windows-latest×3.12` + `ubuntu-latest×3.12`；
- actions：`actions/checkout@v7` / `actions/setup-python@v7`（均为 `node24` 运行时，无 Node20 弃用注解）；
- `concurrency`：同 ref 新 run 取消旧 run，但 **main 分支不取消**（保留每个提交 CI 结论可查）；
- 取值方式（不抄会变的裸数字）：
  `gh run list --repo yuluo554/bookmark-doctor --branch main --limit 3` 与
  `gh api repos/yuluo554/bookmark-doctor/commits/<sha>/check-runs --jq '[.check_runs[]|.conclusion]'`。

## 5. 便携 zip 打包口径（可复现）

1. 成员 = `git ls-files` 全部跟踪文件（取工作树内容）；
2. **排除 `plan/RELEASE-*.md`**——发布留档记录产物 sha256，随包发出会自指（本文件即在排除之列）；
3. 压缩方式 `ZIP_STORED`；`date_time` 固定 `(2026,10,20,0,0,0)`；
4. 成员路径统一加根目录前缀 `bookmark-doctor-0.2.0/`；
5. 非 ASCII 文件名显式置 `flag_bits |= 0x800`。

> sdist 由 setuptools 生成，含 `LICENSE / README / pyproject / src/ / tests/`，**不含 `plan/` 与 `data/`**，
> 故与本留档的 sha256 无自指关系。

## 6. tag 与 Release

| 项 | 值 |
|---|---|
| tag | `v0.2.0`（annotated） |
| Release | https://github.com/yuluo554/bookmark-doctor/releases/tag/v0.2.0 |
| 附件 | `bookmark-doctor-0.2.0-source.zip` / `bookmark_doctor-0.2.0.tar.gz`（ASCII 名，sha256 见 §3） |
| 上一版 | `v0.1.0` 的 tag 与两个附件**保持原样**（历史事实不覆盖） |

## 7. 已知残留（不掩盖）

1. **Python 3.8 用户的实际报错文案不友好**：为"构建依赖 `setuptools>=77` 解析失败"，
   而非 pip 的 `Requires-Python` 干净拒绝（属既有行为，非本版引入）。
2. **sdist 不含 `data/`**：从 sdist 安装后跑 `tests/` 会因缺 `data/fixtures` 失败；
   "下载即用"以 **source.zip** 为准（README 已如此指引）。本版沿用，未扩大范围。
3. **`plan/**` 历史留档仍写"Python ≥ 3.8"**：按"不改历史留档"保留；`README`、`tools/README.md`、
   `pyproject.toml`、`ci.yml` 已同步为 3.9。
4. **`update/`（诊断与执行交接物）未入本版本控制**：含本机绝对路径，按纪律排除。
5. **临时构建目录**均在系统临时目录，未入仓库。

## 8. 脱敏（本版沿用 M6 四步口径）

| 步骤 | 结论 |
|---|---|
| ① 文件名扫描 | 本版新增/改动文件仅 6 个，无密钥形态文件名 |
| ② 内容级扫描 | 改动为测试 fixture、版本号、README 文案、pyproject 元数据、CI 配置；含"Python 版本号/actions 版本号"等纯技术字面值，无个人信息 |
| ③ 发布物扫描 | 便携 zip 与 sdist 为源码文本，成员同 §5 口径 |
| ④ 历史扫描 | 无历史改写；全史元数据沿用 M6 已脱敏状态 |

# RELEASE-M6 — 发布留档

> 生成：2026-10-15（M6 发布执行实录）。三件套之二：发布决策与证据留档（另两件：tag + GitHub Release）。
> 措辞纪律：本文件随仓库公开，**不落个人路径 / 邮箱 / token 词面**（历史教训：留档自命中必踩）。

## 1. 脱敏四步（命令 + 结论逐项留档）

| 步骤 | 动作 | 结论 |
|---|---|---|
| ① 文件名扫描 | `git ls-files` 全量过 `.env/.key/secret/token/password` 形态 | 0 命中；`.gitignore` 覆盖运行产物（`out/`、`.venv/`、`dist/`、`*_private/`、个人书签样本等） |
| ② 内容级扫描 | 全部跟踪文本 grep 密钥形态 / 手机号 / 身份证 / 个人路径 / 内网 IP / 邮箱词面 | 仅命中两类**非个人信息**：站点域名（`mp.weixin.qq.com` 等，实测数据本体）与 epoch 时间戳数字（合成集 add_date 字面值，数字形态撞手机号正则的误报，逐条核实非手机号） |
| ③ 二进制样例扫描 | 发布物（zip / tar.gz）逐条目 Python 字节读法强标记扫描 | 0 命中（同 ② 口径，时间戳误报已逐条核实） |
| ④ 历史扫描 | `git cat-file --batch-all-objects` 全对象（94 blobs + 9 commits）扫描 | 0 命中；旧对象已 `reflog expire --expire=now --all && git gc --prune=now` 清净，`git fsck` 无残留 |

**提交元数据邮箱决策**（未建远端零成本窗口内执行完毕）：
- 原状态：全部提交的 author/committer 邮箱为真实个人邮箱（本地 git 全局配置所致）；
- 执行：`git filter-branch --env-filter` 全史改写为 GitHub noreply（`<id>+yuluo554@users.noreply.github.com`）→ `git log --format='%ae %ce'` 验证全史两字段均为 noreply → reflog 过期 + gc → 全对象扫描确认旧邮箱词面 0 残留；
- 防复发：仓库本地 `git config user.email` 固化为同 noreply 地址（此后提交不受全局配置影响）。

## 2. 干净环境验证（新目录 clone + 全新 venv，按 README 逐条）

- 环境：临时目录 `git clone` 本地仓库 + 全新 venv（Python 3.8.8——项目底线解释器）；
- **暴露问题 1 件并已修复**：3.8 自带 pip 20.2.3 不支持 pyproject 可编辑安装（"editable mode currently requires a setup.py based build"）→ README 快速开始补"升级 pip"步骤（编号顺延为 8 步），commit `1b426ae`；
- 逐条实测：venv 建立 / pip 升级 / `-e ".[dev]"` 安装 / `--version` + `--selftest`（exit 0）/ `pytest`（**145 passed**）/ `run` 端到端（exit 0，27 条 → 5 产物）/ `bench`（B1–B6 全绿 exit 0）/ 数据生成器 `--check` 双绿（位级一致）/ `report` `export` 子命令（exit 0）。

## 3. 发布物定案与留档

| 产物 | 说明 | sha256 |
|---|---|---|
| `bookmark-doctor-0.1.0-source.zip` | 便携源码包：`git ls-files` 全跟踪文件 + ZIP_STORED + 固定 `date_time=(2026,10,15,0,0,0)`，**两次打包逐字节一致**（确定性验证通过） | `c1bca065d7795ecbd50e99db47a649f36f9e29d387dc0d3c023da07e6a689fc6` |
| `bookmark_doctor-0.1.0.tar.gz` | 标准 sdist（`python -m build --sdist`） | `dff5badaede292589d70b4f807d17157c2bcc8de6f3faa113df1a0ef1e5e0339` |

- 缓议项裁决（plan/00 待定决策 A5）：**exe 不做**——零第三方运行时依赖的纯 Python 工具，便携 zip + pip 安装两条通路已覆盖"下载即用"；exe 打包引入 PyInstaller 依赖与杀软误报风险，收益为负。据实记录"不做"。
- 产物与发布源码同基线：`git diff <构建提交>..HEAD -- src/ tools/` 为空（已验证）；
- 发布物本体复核：zip 解包 → 中立目录跑 test_m5 14 passed + CLI --version 0.1.0 + gen_fixtures --check 位级一致（冻结态自检通过）。

## 4. 建仓与 CI

- 建仓：`gh repo create bookmark-doctor --private`（先 private）；remote 初建 https → 首推被拒（OAuth token 无 `workflow` scope，拒绝更新 `.github/workflows/ci.yml`）→ **切换 remote 为 SSH**（本机已有已验证 SSH key）→ push 成功。教训留档：gh https 通路对 workflow 文件的 scope 门，SSH 通路不受限；
- **CI 首跑全绿**（run id `38763701707`）：三矩阵 `windows-3.8 / windows-3.12 / ubuntu-3.12` 全部 success，零诊断轮（预算未消耗；仅 runner 弃用告示，无失败面）；
- 对账：push 事件数 = run 数（1 = 1，单次 push 全史）；run `head_sha` = 本地 HEAD `1b426ae` 逐位一致；
- tag push 行为：见本文件末节"发布后回填"。

## 5. tag 与 Release（执行后回填）

- tag：`v0.1.0`（annotated，打在含终态回写的提交上）
- Release 附件：ASCII 名（source.zip / tar.gz）+ sha256 以本文件 §3 为准
- 真下载复核：执行后回填
- 可见性切换：三清（历史三扫 0 / 坏 blob 修净 / 失败 run 无）后执行，结果回填

## 6. 发布后复核（执行后回填）

- GitHub 全新 clone → 历史扫描 + 全量测试 + 端到端复跑：待回填
- RELEASE-M6 回填提交：待回填（不迁 tag）

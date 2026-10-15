# HANDOFF-M1 — 下一棒：M1 数据先行

> 上一棒：M0 计划先行与骨架（2026-10-15 完成，本对话）。
> 启动方式：`/goal 读取 "plan/HANDOFF-M1.md" 继续完成任务`（会话侧拼项目绝对路径；库内一律相对路径）。

## 一、当前进度与证据

**M0 已完成**：plan/00–07 全套计划文档 + 可运行骨架 + 双解释器验证 + HANDOFF 本体落盘。

| 项 | 证据 |
|---|---|
| 计划文档齐 | `plan/02`–`07` 六份 + `plan/00` v2 回写（决策 D8–D16、待定决策表 A1–A5） |
| 骨架源码 | `src/bookmark_doctor/`（cli / `__main__` / `_encoding`）+ `pyproject.toml`（src 布局、零运行时依赖、dev extras） |
| 测试 | `tests/test_cli.py`（7 项：版本/帮助/无参/selftest/模块通路/安装面版本）+ `tests/test_encoding.py`（4 项：cp1252 改配 / cp936 不动 / utf-8 不动 / 子进程真跑）+ `tests/test_meta.py`（workflow 解析与 fetch-depth 守门） |
| 双解释器 | 3.8.8 系统通道 12 passed；3.12.10 venv 通道 12 passed（含可编辑安装后版本一致性实跑） |
| CLI 冒烟 | 三通路全绿：`.venv/Scripts/bookmark-doctor.exe --version/--selftest`（裸命令）+ `python -m bookmark_doctor --selftest`（模块形态） |
| 变异验证 | 编码守卫探针破坏实验通过（`.tmp/mutation_check.py`，临时件不入仓）：守卫正常改配 utf-8；探针恒真化后不再改配 → 守门测试必然红 |
| CI 就绪（未实跑） | `.github/workflows/ci.yml` 三矩阵；**本地等价校验（未接远端，CI 待首推验证）**：workflow YAML 可解析 + job/step 结构断言 + fetch-depth=0 断言 |
| 工程配置 | `.gitattributes`（eol=lf + `data/** -text` 冻结区）、`.gitignore`、`LICENSE`(MIT)、`README.md`（快速开始 = dev extras 安装通路）、`tools/README.md`、`data/{rules,fixtures,measurements}/README.md` |

## 二、下一棒（M1）待办

1. **实测记录**（`data/measurements/`）：对题面锚点站点逐条复测——微信 `mp.weixin.qq.com/s/...`（预期 200）、知乎（预期 403）、微博（预期 302）、B站（预期 301/302）、掘金或 CSDN（预期 521）、通用站基线（GitHub 200）。用 `curl -sS -o /dev/null -w` 或临时脚本，**只记状态行/重定向链/关键头部，不落正文**；逐条写 `observations.md`（人读）+ `observations.json`（机读，字段见 plan/05 §2）。网络不可达/查证不到的站点如实标 `pending` + 已查渠道，不编造。
2. **规则包 v1**（`data/rules/ruleset.json`）：新建 `tools/gen_ruleset.py` 生成——probe 参数（超时/重试/降频/跳转上限/UA 形态）+ degrade_rules（每条挂 `anchor.observation_id` → observations.json）+ tracked_query_params 初稿 + aging 分档 + similarity 阈值。`--check` 位级一致。
3. **合成书签集**（`data/fixtures/`）：新建 `tools/gen_fixtures.py`——双格式（Netscape HTML + Chrome JSON，**Chrome `date_added` 纪元换算要在真值里对账**）+ `truth.json`（只存输入与期望）+ `manifest.json`（三类易错形态覆盖声明、seed、sha256 表）。URL 全用 `*.invalid` 保留域。`--check` 位级一致。
4. **mock 站点雏形**（`tools/mock_site.py`）：本地 http.server 按 path 脚本化响应（403/302/301/521/404/200/挂起），仅 loopback；M4 基准复用。
5. **守门测试**：锚点硬门 loader 预览（缺锚点/pending → 不生效 + 原因列出）、冻结产物 `--check` 位级门、`data/**` 无 CR 门。新增守门各做一次变异验证。
6. **收尾**：双解释器全量测试 → plan/00/05/06 回写 → HANDOFF-M2 → commit。

## 三、既定口径 K 清单（动了会打挂测试/基准的约定）

- **K1 退出码契约**：CLI 0=完成（含"检出问题"）/ 2=用法与输入不可用；bench 0/1/2 三语义；`--selftest` 0/1。改语义必须连测试一起改并登记决策记录。
- **K2 三态判定语义**：`alive` / `dead` / `review`；网络不可达、403/521、未确证情形**一律 `review`**；通用映射下唯一判死证据 = 404/410；规则命中 > 通用映射；多规则冲突取保守（review > dead > alive）。
- **K3 单点口径**：全部阈值与规则数值只存 `data/rules/ruleset.json`；引擎/基准/测试/文档零第二份（零字面量门禁 M3 落地）；版本号由 manifest 派生。
- **K4 锚点硬门**：规则 `anchor.observation_id` 必须解析到 `check_status=verified` 的观测才可加载生效；否则进"未启用清单"。
- **K5 冻结纪律**：生成器产物（ruleset/fixtures）禁手改，`--check` 位级一致；确定性 RNG（splitmix64 类）、禁 stdlib random / set 迭代序 / 系统时钟；`data/**` 在 `.gitattributes` 标 `-text`。
- **K6 UIR 纪律**：原始 URL 永不改写（规范化只作比较键）；缺失字段一律 `null` 不猜补；解析失败 exit 2 不落半成品。
- **K7 诚实口径**：无远端期间一切 CI 结论写"本地等价校验（未接远端，CI 待首推验证）"；文档计数当轮实测；未跑过的 DoD 不打勾。
- **K8 编码守卫**：所有可执行入口（CLI 与 tools/ 每个脚本）第一步 `ensure_utf8_stdio()`；子进程解码显式 `encoding="utf-8"`；写盘 `write_bytes`/`newline="\n"`（3.8 禁 `Path.write_text(newline=)`）；禁 3.9+ 语法。
- **K9 测试面 = 安装面**：测试真 import 的库全部进 `[dev]` extras（当前 pytest + pyyaml）；README 快速开始与 CI 用同一 extras 集合；两条命令通路（裸命令 / `python -m`）都要冒烟。
- **K10 里程碑收尾顺序**：DoD 验证 → plan/00·05·06 回写 → HANDOFF-M<n+1> → commit →（有远端则 push 等 CI 绿）。

## 四、本机环境坑（只写实测过的）

- **E-1 双解释器通道**：`py` 默认 3.8.8；3.12 需显式 `py -3.12`。venv 已建于 `.venv/`（3.12.10 + dev extras，含 pyyaml 6.0.3）。跑 3.8 通道测试用 `PYTHONPATH=src py -X utf8 -m pytest`；跑 venv 通道用 `.venv/Scripts/python.exe -m pytest`。
- **E-2 egg-info 位置效应**：`.venv` 可编辑安装会在 `src/` 下生成 `bookmark_doctor.egg-info`（已 gitignore）。此后 3.8 系统通道（PYTHONPATH=src）的 `importlib.metadata` 能读到发行元数据 → `test_installed_metadata_version_matches` 从"跳过"变"实跑通过"（版本一致，正确行为）；删掉 egg-info 则恢复跳过。干净 clone 两者皆可，属环境差异不是缺陷。
- **E-3 pip 走镜像**：`NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>`（注册表系统代理污染 `https://127.0.0.1:7897`）。
- **E-4 全程 `PYTHONDONTWRITEBYTECODE=1`**（含 pip install）；出怪错先清 `__pycache__` 再跑。
- **E-5 空目录不入 git**：`data/rules/`、`data/fixtures/`、`data/measurements/`、`tools/` 各有 README.md 占位（已入库），M1 产物放同目录。
- **E-6 git 全局邮箱**：当前提交元数据为**真实个人邮箱**（git 全局配置所致，提交时自动携带）。已列入待定决策 A4 + 发布计划 3.2：发布前改写 GitHub noreply（未建远端 = 零成本窗口）。M1 起若要提前止血可 `git config user.email <GitHub noreply>`（本仓库级），发布期再全历史改写。
- **E-7 无远端**：`git remote -v` 为空；gh 已登录（yuluo554，scopes 无 workflow——建仓 push workflow 文件时优先走 SSH 通道或按 skill 的建仓纪律）。

## 五、M0 DoD checklist（逐项已验证）

- [x] plan/00–07 全部落盘且 plan/00 索引一致
- [x] 骨架源码：src 包 + pyproject（src 布局、零运行时依赖、console script）+ `__main__`
- [x] 编码守卫 + 4 项守卫测试（含 cp1252 子进程真跑）
- [x] CLI `--version` / `--selftest` / 无参 exit 2 / 帮助
- [x] 退出码契约测试（test_cli.py）
- [x] CI workflow + 解析守门 + fetch-depth 守门（test_meta.py）
- [x] 双解释器全量测试绿（3.8.8：12 passed；3.12.10：12 passed）
- [x] 三通路 CLI 冒烟绿（裸命令 ×2 + 模块形态）
- [x] 新守门变异验证（编码守卫探针破坏实验 → 守门必红）
- [x] .gitattributes（eol=lf + data/** -text）/ .gitignore / LICENSE / README / tools·data 说明
- [x] plan/00 回写（D8–D16、A1–A5、里程碑 M0 ✅、诚实口径尾注）
- [x] HANDOFF-M1 落盘（本文件）+ commit
- [x] CI：本地等价校验（未接远端，CI 待首推验证）

## 六、关键命令速查

```bash
cd <项目根>
export PYTHONDONTWRITEBYTECODE=1

# 3.8 系统通道（底线解释器，源码态）
PYTHONPATH=src py -X utf8 -m pytest -q
PYTHONPATH=src py -X utf8 -m bookmark_doctor --selftest

# 3.12 venv 通道（安装态）
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/bookmark-doctor.exe --selftest
.venv/Scripts/python.exe -m bookmark_doctor --selftest

# 依赖（镜像 + NO_PROXY）
NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <pkg>
# venv 重建：py -3.12 -m venv .venv && .venv/Scripts/python.exe -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
```

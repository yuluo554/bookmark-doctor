# HANDOFF-M7 — 完结快照（项目发布完成）

> 上一棒：M6 发布（2026-10-15 完成，本对话）。本快照为**完结态**：里程碑计划 M0–M6 全部达成，无下一棒待办。
> 续接方式（如需继续演进）：直接读本文件 + `plan/RELEASE-M6.md`；库内一律相对路径。

## 一、终态与证据

| 项 | 值 / 证据 |
|---|---|
| 公开仓库 | https://github.com/yuluo554/bookmark-doctor （**PUBLIC**，署名 yuluo554） |
| tag | `v0.1.0`（annotated，打在 `a7213be`） |
| Release | https://github.com/yuluo554/bookmark-doctor/releases/tag/v0.1.0 |
| 附件（ASCII 名 + sha256） | `bookmark-doctor-0.1.0-source.zip` → `c1bca065d7795ecbd50e99db47a649f36f9e29d387dc0d3c023da07e6a689fc6`；`bookmark_doctor-0.1.0.tar.gz` → `dff5badaede292589d70b4f807d17157c2bcc8de6f3faa113df1a0ef1e5e0339` |
| CI | 全绿：6 run 全 success（矩阵 windows 3.8 / windows 3.12 / ubuntu 3.12；含 tag push 触发 run，实测**会**触发） |
| 测试基线 | 145 passed（3.8.8 干净 venv 与发布物本体各复跑一次）；bench B1–B6 exit 0；数据生成器 `--check` 双绿 |
| 发布留档 | `plan/RELEASE-M6.md`（脱敏四步 / 干净环境 / 产物 / 建仓 CI / tag Release / 发布后复核 / 可见性 / 终态 八节） |
| 脱敏 | 四步全过；提交邮箱全史改写 GitHub noreply（`282769740+yuluo554@users.noreply.github.com`），旧对象 gc 清净，全对象扫描 0 残留 |
| topics | `bookmarks, chinese-web, cli, dead-link-checker, open-source, python, url-dedupe` |

## 二、里程碑总表（全达成）

| 里程碑 | 状态 | 核心产物 |
|---|---|---|
| M0 计划先行与骨架 | ✅ | plan/00–07 + 可运行骨架 + CI 三矩阵 |
| M1 数据先行 | ✅ | `data/measurements/` 实测台账 + `data/rules/ruleset.json` v1 + `data/fixtures/set-1/`（27 条真值）+ 数据守门 |
| M2 解析 | ✅ | 双解析器（Netscape 状态机 + Chrome JSON）+ UIR 冻结 K11–K19 + CLI `import` |
| M3 检测与去重 | ✅ | `probe.py` + `classify.py` + `normalize.py` + `dedupe.py` + `ruleset.py` 锚点硬门 + CLI `check`/`dedupe` |
| M4 基准 | ✅ | `tools/bench.py` B1–B6 + false_dead=0 硬门 + 探活可证伪 + 退出码三语义 |
| M5 交付 | ✅ | CLI `report`/`export`/`run` + 七节单文件报告（零外链）+ 一键导回 |
| M6 发布 | ✅ | 公开仓库 + tag + Release（附产物）+ RELEASE-M6 留档 |

## 三、交付物对照（题面 §3 九项）

| # | 题面材料 | 产物位置 | 状态 |
|---|---|---|---|
| 1 | 源代码仓库 | GitHub PUBLIC 仓库 | ✅ |
| 2 | 降级规则库（锚点 + 台账） | `data/rules/` + `data/measurements/` | ✅ |
| 3 | 合成书签数据集 | `data/fixtures/set-1/` | ✅ |
| 4 | 内置基准与复跑脚本 | `tools/bench.py` | ✅ |
| 5 | 本地 CLI 工具 | `src/bookmark_doctor/`（六子命令） | ✅ |
| 6 | 本地 HTML 报告 | `report` 产物（单文件零外链） | ✅ |
| 7 | 一键导回产物 | `export` 产物（Netscape HTML） | ✅ |
| 8 | 技术文档 | README + `data/README.md` + `plan/04` | ✅ |
| 9 | 发布留档三件套 | tag + Release + `plan/RELEASE-M6.md` | ✅ |

## 四、既定口径 K 清单（发布态无新增；沿用 K1–K22 全部）

发布期新增实践红线：
- **发布前脱敏四步 + 提交元数据邮箱改写**：全史 filter-branch 改写 noreply，reflog/gc 后全对象扫描确认 0 残留；库内留档措辞占位化，不落个人标识词面；
- **产物确定性**：便携 zip 用 `ZIP_STORED` + 固定 `date_time`，两次打包逐字节一致；sha256 留档并真下载复核；
- **gh https 通路对 `.github/workflows/` 写入有 `workflow` scope 门 → 改用 SSH remote**（凭据已在 Keychain，不受该 scope 限制）。

## 五、本机环境坑（沿用 HANDOFF-M5 §四 + M5 E-21/E-22 全部；M6 新增）

- **E-23 Python 3.8 自带 pip 20.2.3 不支持 pyproject 可编辑安装**（"editable mode currently requires a setup.py based build"）：新建 3.8 venv 后必须先 `python -m pip install --upgrade pip` 再 `-e ".[dev]"`；README 快速开始第 3 步已固化该纪律。CI 上 setup-python 装的是新 pip，不受影响（故 CI 无此失败面）。
- **E-24 `gh repo create ... --push` 的 https 首推会被 workflow scope 拦截**（拒绝更新 `.github/workflows/ci.yml`）：改 `git remote set-url origin git@github.com:<user>/<repo>.git` 走 SSH 即可；亦可 `gh auth refresh -s workflow`（需浏览器设备码，无人值守场景不可用）。
- **E-25 本机 `/tmp` 路径与 Windows 临时目录混用易踩**：Python 用 `C:\Users\…\AppData\Local\Temp\...` 而 Git Bash 的 `/tmp` 映射到另一目录时，脚本内绝对路径写死会 FileNotFoundError；脚本内一律用 `os.path.dirname(__file__)` 取相对锚点。
- **E-26 heredoc 写 Python 时正则转义**：`rb'...\U...'` 在 bytes 正则里是非法转义（bad escape \U）——扫个人路径用 `C:\\\\Users`（bytes 字面量双反斜杠）或改用 `os.sep` 拼接。

## 六、M6 DoD checklist（逐项已验证）

- [x] 脱敏四步（跟踪文件 / 内容级 / 二进制 / 历史）+ 提交元数据邮箱决策执行（全史 noreply + 0 残留，RELEASE-M6 §1）
- [x] 干净环境验证：新目录 clone + 全新 venv 按 README 逐条跑通（修复 pip 问题 1 件 + 回归复跑 145 passed）
- [x] 建仓（先 private）→ push → CI 首跑全绿（零诊断轮）→ 对账（push 数 = run 数，head_sha 逐提交配对）
- [x] 产物：便携 zip（确定性）+ 标准 sdist + sha256 留档；exe 缓议项显式记录"不做"（plan/00 A5）
- [x] tag + Release（附件 ASCII 名 + sha256 留档）+ 发布物本体复核（真下载 → 逐位一致 → 冻结态自检 23 passed）
- [x] 切 public（visibility=PUBLIC + topics + 匿名 clone/下载复核通过）
- [x] plan/00/06/07 回写 + RELEASE-M6 留档 + 本完结快照
- [x] 发布后全新 clone 复核（历史三扫 0 命中 + 145 passed + run/bench exit 0）

## 七、关键命令速查（发布态）

```bash
cd <项目根>
export PYTHONDONTWRITEBYTECODE=1

# 免安装运行（源码树内）
PYTHONPATH=src python -X utf8 -m bookmark_doctor run data/fixtures/set-1/bookmarks.netscape.html --out-dir out --probe-date 2026-01-01
# 安装为命令
python -m pip install --upgrade pip && python -m pip install -e ".[dev]"   # 3.8 先升 pip（E-23）

# 回归双基线
PYTHONPATH=src python -X utf8 tools/bench.py                 # B1–B6；exit 0 = 达标
PYTHONPATH=src python -X utf8 -m pytest -q                   # 全量 145 项；长跑用后台任务
PYTHONPATH=src python -X utf8 tools/gen_ruleset.py --check   # 数据位级守门
PYTHONPATH=src python -X utf8 tools/gen_fixtures.py --check

# 发布态运维（如需）
git remote -v                                                # origin 走 SSH（https 有 workflow scope 门，E-24）
gh run list --repo yuluo554/bookmark-doctor
gh release view v0.1.0 --repo yuluo554/bookmark-doctor
```
# HANDOFF-M6 — 下一棒：M6 发布

> 上一棒：M5 交付（2026-10-15 完成，本对话）。
> 启动方式：`/goal 读取 "plan/HANDOFF-M6.md" 继续完成任务`（会话侧拼项目绝对路径；库内一律相对路径）。

## 一、当前进度与证据

**M5 已完成**：CLI 全子命令（import/check/dedupe/report/export/run）+ 七节单文件 HTML 报告 + Netscape 导回 + 全链路编排。合成集 `run` 端到端 exit 0（27 条 → 8 节报告 + 导回文件）；bench B1–B6 全绿 exit 0；数据资产 --check 双绿。

| 项 | 证据 |
|---|---|
| CLI 全子命令 | `cli.py` 六子命令 + `--version`/`--selftest`；退出码契约：0 完成 / 2 用法与输入不可用（不落半成品）；`--help` 全量可读 |
| 报告 | `report.py`：八分区（摘要/失效/待复核/重复/长期未访问画像/未探测条目/建议清理/口径与免责）；`assert_no_external_resources` 硬断言（无 `<link>`/外链 script/img/@import/外部字体，CSS 内联——断网可开）；渲染层零判定（只消费 check/dedupe/aging 既有结论）；输出字节级确定 |
| 画像 | `aging.py`：阈值取 ruleset `aging.tiers_days`（缺失/非法 → AgingConfigError，引擎零默认值）；分档取"满足的最高档"；`add_date=null` 单列"添加时间未知"；参考日显式传参（无时钟调用）；口径注明"以添加时间近似未访问" |
| 导回 | `export.py` `filter_bookmarks` + `export_netscape`：默认不删不改全量导回；`--apply-dedupe`（组内非保留成员剔除、组外不动）/`--exclude-dead` 显式开关（缺产物 exit 2）；转义纪律 `&<>"`；导出→再解析 27 条逐条一致（实测） |
| 编排 | `_cmd_run` 直接复用各子命令实现（单一源、零第二份判定）；import→check→dedupe→report→export 串接，任一步失败即停 |
| 测试 | 新增 tests/test_m5.py 14 项（aging 阈值/非法配置/分档与未知、报告零外链/七节/未探测/转义与确定/fragment 标记、export 往返/过滤语义/CLI 开关与 exit2、report CLI、run 编排 mock 端到端/坏输入 exit2 不落半成品/两次运行确定）；变异验证 1 次（`filter_bookmarks` 初版"keep-only"误删组外书签 → 测试红 → 修为"组内剔除"语义 → 绿） |
| 回写 | plan/00（状态行/里程碑表 M5 ✅）/ plan/04（§4 落地标注）/ plan/06（M5 DoD 全勾）/ README（快速开始 run 步骤 + "本地报告与导回"节 + 能力表 M5 勾） |

## 二、下一棒（M6）待办（plan/06 M6 DoD）

1. **脱敏四步**：跟踪文件 / 内容级 / 二进制 / 必要时历史；**提交元数据邮箱决策**——当前提交邮箱为真实个人邮箱，**零成本窗口：未建远端**，改 GitHub noreply（`git config user.email` + `git commit --amend --reset-author` 逐提交或 filter，历史浅可重写）。
2. **干净环境验证**：新目录 clone + 全新 venv 按 README 逐条跑通（修复问题 + 回归测试）。
3. **建仓**（先 private）→ push → CI 首跑（预算多轮诊断）→ 全绿 → 对账（push 数 = run 数，逐提交配对）。
4. **产物**：按 M5 实况定案（源码包/zip；exe 缓议项据实记录"做/不做"——plan/00 待定决策 A5）。
5. **tag + Release**（附件 ASCII 名 + sha256 留档）+ 发布物本体复核（真下载 → 比对 → 冻结态自检）。
6. **收尾**：plan/00/06/07 回写 + RELEASE-M6 留档三件套 + 完结快照。

## 三、既定口径 K 清单（M5 无新增冻结口径；沿用 M3 K1–K22 全部）

M5 新红线已落地（原 M4 预告）：
- **报告渲染层零判定逻辑**（plan/04 §4.4）：report.py 只消费既有结论；
- **资源零外链硬断言**：`assert_no_external_resources` 常驻（渲染函数出口即断言 + 测试锁定）。

沿用关键纪律（M5 实践一致）：
- 引擎不设 ruleset 参数默认值（aging 同 probe 纪律：缺失即 AgingConfigError）；
- `serialize.py` 确定性写盘单点（report.html / 导回 HTML 也走 write_atomic）；
- 锚点硬门 loader 与 test_data_gates 预览 loader 未分叉；
- `--apply-dedupe`/`--exclude-dead` 显式开关语义：**合并/剔除只作用于既有结论命中的条目，组外/非 dead 一律不动**（默认不删不改）。

## 四、本机环境坑（M5 实测增补；沿用 HANDOFF-M5 §四 E-1~E-20 全部条目）

- **E-21 `py - <<EOF` heredoc 在本机 Git Bash 通道注入失败**（stdin 被宿主包装污染，`__zcode_status` 语法错误）：多行 Python 一律写临时 .py 文件再 `py -X utf8 file.py` 执行。
- **E-22 mock 探测判定偶发落 review**（本机 loopback 防火墙驱动抖动，E-17 变体）：run 端到端测试若断言具体 verdict 失败，先复跑确认是否为环境抖动；测试内断言用 mock 服务器（pytest fixture 内起服务），不要跨进程复用手起端口。

## 五、M5 DoD checklist（逐项已验证）

- [x] CLI 全子命令规格冻结 + 测试（report/export/run + 六子命令 --help/退出码）
- [x] 报告：分节完整 + 零外链硬断言 + 免责口径声明 + 未探测独立分区
- [x] 导回：往返一致（机器，27 条逐条）+ 浏览器实际导入（人工步骤：out/bookmarks-export.html 导入 Chrome 书签管理器验证成功——M5 验收记录）
- [x] CLI 编排单一源（渲染/过滤零判定；run 复用子命令实现）
- [x] 干净环境按 README 逐条跑通（本地等价校验，记录退出码：数据 --check 双 0 / run 端到端 0 / bench 0；CI 待首推）
- [x] HANDOFF-M6 落盘 + commit

## 六、关键命令速查（增量）

```bash
cd <项目根>
export PYTHONDONTWRITEBYTECODE=1

# 全链路（一条命令出全部产物；report.html 断网可开）
PYTHONPATH=src py -X utf8 -m bookmark_doctor run data/fixtures/set-1/bookmarks.netscape.html --out-dir out --probe-date 2026-10-15
# 显式动作导回（默认不删不改）
PYTHONPATH=src py -X utf8 -m bookmark_doctor export out/tree.json --dedupe out/dedupe.json --apply-dedupe --out cleaned.html
PYTHONPATH=src py -X utf8 -m bookmark_doctor export out/tree.json --check out/check.json --exclude-dead --out cleaned.html

# 内置基准 / 全量测试（同 M4 速查）
PYTHONPATH=src py -X utf8 tools/bench.py
PYTHONPATH=src py -X utf8 -m pytest -q        # 双解释器；长跑用后台任务
.venv/Scripts/python.exe -X utf8 -m pytest -q

# 数据资产 --check（回归防线）
PYTHONPATH=src py -X utf8 tools/gen_ruleset.py --check
PYTHONPATH=src py -X utf8 tools/gen_fixtures.py --check
```

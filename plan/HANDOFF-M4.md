# HANDOFF-M4 — 下一棒：M4 基准

> 上一棒：M3 检测与去重（2026-10-15 完成，本对话）。
> 启动方式：`/goal 读取 "plan/HANDOFF-M4.md" 继续完成任务`（会话侧拼项目绝对路径；库内一律相对路径）。

## 一、当前进度与证据

**M3 已完成**：探测/分类/规范化/去重引擎 + CLI check/dedupe + 锚点硬门正式引擎 + 零字面量门禁（双解释器 122 passed ×2，变异验证 4 次）。

| 项 | 证据 |
|---|---|
| 探测引擎 | `src/bookmark_doctor/probe.py`：urllib 自写单次逻辑探测——HEAD 先行；405/501 → 降级 GET 限读 1024 字节即断（合计算一次）；跳转链自写循环（记录 `redirect_chain`；成环 → `redirect_loop`、超限 → `too_many_redirects`）；timeout/retry/delay/UA 全取 ruleset `probe` 节（**引擎不设默认值**，缺参数即 ValueError）；串行 + delay_s 降频。网络失败归 error_class 不抛出（单 URL 失败不中断整批） |
| 分类引擎 | `classify.py`：plan/04 §2.2 分类表（2xx→alive / 404/410→dead / 401·403·405·406·429·451→review(4xx_blocked) / 521-523→review(cdn_blocked) / 5xx→review / error_class→review 同码 / 3xx 耗尽→review(redirect_unresolved) / 异常空记录→review(probe_incomplete)）；规则优先于通用映射；多规则冲突保守取值（review>dead>alive）+ `conflict` 备注；host_suffix 边界防近似域名误命中（evil-example.com 不命中 example.com） |
| 规范化 | `normalize.py`：六步流水线单点（http→https / host 小写+去**原 scheme** 默认端口 / 路径折叠+去尾斜杠保根 / 剥追踪参数+按键排序 / 剥 fragment / shortlink_known 映射不猜）；原始 URL 永不改写；追踪名单取 ruleset `tracked_query_params`（exact+prefixes） |
| 去重 | `dedupe.py`：比较键 = normalize(url)；check.json 有 final_url 时优先 normalize(final_url)；固定保留策略 https > 无追踪参数 > add_date 最早（None 不与已知争）> 文件序；fragment_variant 以规范化键为基判定（追踪参数差异被流水线吸收后 fragment 互异才算）；绝不自动删 |
| 规则包 | `ruleset.py`：锚点硬门正式引擎（K4 判定顺序=先台账后规则，与 M1 预览 loader 同构）；`load_effective_rules(repo_root, rules_path)` 返回 (ruleset, enabled, disabled)；`--rules` 覆盖位保留 |
| CLI | `check <tree.json> --probe-date --rules --out`：结果含 ruleset_version/revision + `rules_disabled`（未启用清单）+ summary 双计数 + results；`dedupe <tree.json> --check --out`。文件级失败（tree 不可读/schema 不符/ruleset 坏）exit 2 无半成品；`--out -` 走 stdout 摘要 |
| 确定性 | check.json / dedupe.json 同输入双跑逐字节一致（测试锁定）；序列化纪律与 tree.json 同（sort_keys+LF+结尾换行，serialize.py 单点） |
| mock 场景 | 全场景对照通过：200/403/404/410/521/301/302/环跳/405 降级/挂起超时(read_timeout)/DNS 失败(dns_failure)/拒绝连接(connection_error)；**mock_site.py 本轮补 405 码**（M1 雏形未含，`_STATUS_CODES` 增补） |
| 零字面量门禁 | `tests/test_zero_literals.py` 4 项：平台主机名扫描（zhihu/weibo/csdn/bilibili/juejin/douban/tieba/baidu/taobao/jd/weixin/github 词面红线）/ probe 数值动态取 ruleset 生成扫描集（UA 词面+数值）/ HTTP 码越界扫描（豁免名单显式写死：classify+probe+normalize 三文件、逐值登记 `_SEMANTIC_STATUS_CODES`）/ 扫描器自证。**落地时抓到 3 处真实违规并修复**（classify 注释站点名×2 / probe 默认 timeout=10 / 默认 redirect_max=5——修法=引擎不设默认值） |
| 测试 | 新增 79 项：test_normalize(14)/test_classify(13)/test_dedupe(11，含真值 duplicate_groups 对账)/test_probe(17，自带 loopback mock fixture)/test_check_cli(9，subprocess 真跑)/test_zero_literals(4)；双解释器各 **122 passed** |
| 变异验证 | 4 次：①classify 404→alive 误改→test_classify 红；②ruleset 锚点门 pending 放行→test_anchor_gate_missing_and_pending 红；③probe 405 降级通路瘫→test_head_rejected_falls_back_to_get 红；④normalize 注入 zhihu.com→零字面量门禁红；还原后全绿 |
| 回写 | plan/00（状态行/里程碑表 M3 ✅/索引表 src 新模块行/测试计数 122）/ plan/04（§2.2/§2.3/§3.1 标注已冻结）/ plan/06（M3 DoD 全勾+证据） |

## 二、下一棒（M4）待办

1. **基准 runner `tools/bench.py`**：plan/04 §5.2 双层结构——
   - **样本驱动**：合成集 set-1 真喂引擎（`*.mock.invalid` 主机运行时重写为 loopback mock 端口）→ 与 truth.json 对账；
   - **规则驱动**：不读真值库，遍历 ruleset 每条规则 × 通用映射全组合喂 classify，含"不该命中"反向样例。
2. **mock 主机重写机制**：bench 运行时把 `*.mock.invalid` 解析到 127.0.0.1+动态端口（对照表 = gen_fixtures 的 MOCK_HOSTS → mock_site 路径场景；端口不进冻结产物字节）。truth.json 的 `scenario_hosts` 键即此对照。
3. **指标（manifest 门槛是数据非代码）**：false_dead=0 硬门；三类易错形态命中率分列；重复合并"真值组全合并且无误合并"；指标写进 README（如实）。
4. **可证伪探活**：注入缺陷（403 通用映射改 dead）→ bench 必须 exit 1——常驻测试。退出码三语义（0 达标/1 未达标/2 用法与未知名 `--only` 错误）锁进测试；空分母分支 = `not_enabled` + exit 1（不冒充通过）。
5. **跨格式比对口径 K19**：基准对账不覆盖 folder[0]（Chrome 根树顶层是浏览器来源差异）。
6. **收尾**：bench + 全量测试双基线复跑防回退 → plan/00/05/06 回写（B1–B6 套件对账）→ HANDOFF-M5 → commit。

## 三、既定口径 K 清单（M3 增补 K20–K22；K1–K19 原文见 plan/HANDOFF-M3.md §三）

- **K20 状态分类表**：plan/04 §2.2 表逐行落地于 classify.py；规则命中 > 通用映射；多规则冲突保守（review > dead > alive）+ conflict 备注；error_class 一律 review（网络不可达 ≠ 失效）；无状态无错误的异常记录 → review(probe_incomplete)，不静默判 alive。规则匹配维度 M3 冻结 = host_suffix + http_status（观测状态即 probe 单状态字段——M1 实测首跳形态口径）；未启用维度不参与匹配。
- **K21 规范化六步流水线**：normalize.py 固定顺序（scheme http→https / host 小写+去原 scheme 默认端口 / 路径折叠+尾斜杠保根 / 剥追踪参数+键排序 / 剥 fragment / shortlink_known 不猜）；原始 URL 永不改写；fragment_variant = 规范化键相同且 fragment 互异。
- **K22 去重保留策略**：https > 无追踪参数 > add_date 最早 > 文件序最早；比较键优先 normalize(final_url)（有 check.json 时）；绝不自动删（export --apply-dedupe 为 M5 显式开关）。
- 沿用 M3 纪要：**引擎不设 ruleset 参数默认值**（probe.timeout_s/redirect_max 缺失即 ValueError——零字面量门禁实证的第二份形态）；`serialize.py` 是 check/dedupe/tree 共用确定性写盘单点；锚点硬门 loader 与 tests/test_data_gates.py 预览 loader 不得分叉语义。

## 四、本机环境坑（只写本轮实测过的）

- 沿用 HANDOFF-M3 §四 E-1~E-13 全部条目（双解释器通道 / pip 镜像 / PYTHONDONTWRITEBYTECODE / Git Bash heredoc 失灵→落脚本文件 / mock /hang 语义 / taskkill 双斜杠 / write_text newline 3.10+ / heredoc 嵌套引号 / CLI 文件参数 MSYS 改写）。本轮全部再次验证有效。
- **E-14 MSYS `/tmp` 与 Windows Python 路径不通（复发确认）**：`cp file /tmp/x.bak` 后 Python（py 启动器）读 `/tmp/x.bak` FileNotFoundError——变异验证的备份/还原一律用 `$TEMP`（Windows 侧真实路径）或工作区相对路径。本轮曾因备份错位把 ruleset.py 覆盖成 probe 内容（靠会话记录重写恢复）——**变异验证前先校验备份文件头两行内容再动源码**。
- **E-15 后台服务端口复用假象**：taskkill 后同端口立刻重启可能连上 TIME_WAIT 旧连接外的旧进程残余——mock 冒烟换端口（8931→8932→8933）规避；`netstat -ano | grep :PORT | grep LISTENING` 确认监听 PID 与预期一致再测。
- **E-16 Git Bash `py -X utf8 -c` 内嵌多行脚本**：单引号包裹 + 内部双引号可用（E-12 的正向形态）；含 `%` 格式化的脚本注意 bash 不展开 `%`（安全）但 `$` 会展开——脚本里避免 `$`。

## 五、M3 DoD checklist（逐项已验证）

- [x] 探测引擎（单次/降频/跳转链/超时/重试，参数全出自 ruleset；引擎零默认值）
- [x] 分类表与规则引擎（优先级、保守冲突裁决、未启用清单进 check.json）
- [x] URL 规范化单点实现 + 双向样例测试（含"不该合并"对照）；短链仅用已实测映射、未知不猜
- [x] 零字面量门禁落地（扫描 src/，豁免口径写死）+ 变异验证（4 次全红→还原绿）
- [x] mock 全场景对照（含 405 降级/环跳/挂起/DNS）；check.json / dedupe.json 逐字节一致
- [x] 全量测试绿（3.8.8：122 passed；3.12.10：122 passed）
- [x] plan/00、04、06 回写 + HANDOFF-M4 落盘 + commit

## 六、关键命令速查（增量）

```bash
cd <项目根>
export PYTHONDONTWRITEBYTECODE=1

# 全量测试（双解释器）
PYTHONPATH=src py -X utf8 -m pytest -q
.venv/Scripts/python.exe -X utf8 -m pytest -q

# CLI check / dedupe 冒烟（先起 mock）
PYTHONPATH=src py -X utf8 tools/mock_site.py --port 8933 &
PYTHONPATH=src py -X utf8 -m bookmark_doctor check tree.json --probe-date 2026-10-15 --out check.json
PYTHONPATH=src py -X utf8 -m bookmark_doctor dedupe tree.json --check check.json --out dedupe.json

# 数据资产 --check（回归防线，双解释器）
PYTHONPATH=src py -X utf8 tools/gen_ruleset.py --check
PYTHONPATH=src py -X utf8 tools/gen_fixtures.py --check
```

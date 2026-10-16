# HANDOFF-M5 — 下一棒：M5 交付

> 上一棒：M4 基准（2026-10-15 完成，本对话）。
> 启动方式：`/goal 读取 "plan/HANDOFF-M5.md" 继续完成任务`（会话侧拼项目绝对路径；库内一律相对路径）。

## 一、当前进度与证据

**M4 已完成**：内置基准 runner（B1–B6 样本驱动 + 规则驱动）+ manifest 门槛下发 + 探活缺陷注入 + 退出码三语义 + README 指标节。基准 B1–B6 全绿 exit 0；双解释器 131 passed ×2；变异验证 1 次（classify 403→dead → bench 红、还原绿）。

| 项 | 证据 |
|---|---|
| 基准 runner | `tools/bench.py`：样本驱动（合成集 27 条真值真喂 parse→probe→classify / dedupe 与 truth.json 对账）+ 规则驱动（B4 不读真值库，遍历 4 条生效规则 × 通用映射代表组合喂 classify，372 断言含反向样例：近似域名 / 异状态 / error_class 越界不得命中且结果=通用映射逐字段一致） |
| 套件 | B1 反爬 3/3 review（false_dead=0）/ B2 不可达 8/8 review（false_dead=0）/ B3 死链 3/3 dead / B4 规则驱动 372 断言全过 / B5 重复 4 组全合并且误合并 0 / B6 同输入两次运行逐字节一致 |
| mock 重写 | manifest `mock_host_scenarios` 场景驱动：HTTP 场景 = `/<主机命名空间>/<完整原路径>/status/<场景码>`（保主机+页内区分度，去重键不塌缩）；hang → `/.../hang`；unreachable → 运行时找空端口并**先断言确实拒绝连接**（防 E-15）；scheme http 化（mock 无 TLS）；重写后唯一 URL 只探一次结果扇回（27→16 目标）；端口/映射不进冻结产物 |
| 门槛下发 | manifest `coverage.*.should_cover` → suite threshold；缺失/非法 → BenchConfigError exit 2（门槛是数据非代码，引擎/基准零内联） |
| 探活 | `--inject-defect 403-dead`（403 通用映射改 dead）端到端 → exit 1；常驻测试 tests/test_bench.py；变异验证再证：直接改 classify.py 源码同缺陷 → bench --only B1 红，还原绿 |
| 退出码 | 0 达标 / 1 未达标（含空分母 `not_enabled`——不冒充通过）/ 2 用法与未知名 `--only`、数据资产缺失；`--only B4,B6` 子集运行正常 |
| README | "内置基准"节：一键复跑命令 + 实测指标表（2026-10-15）+ 诚实口径说明（合成集抽样覆盖非穷举，真值只存输入与期望） |
| 测试 | 新增 9 项 test_bench.py（全绿 exit0 / false_dead 硬门 / 门槛=manifest / loopback 断言 / 探活 exit1 / 未知名 exit2 / 子集 / 空分母 not_enabled / B4 体量）；双解释器 **131 passed** ×2 |
| 回写 | plan/00（状态行/里程碑表 M4 ✅/索引行/测试计数 131）/ plan/05（§4 落地标注）/ plan/06（M4 DoD 全勾 + 落地纪要）/ README |

## 二、下一棒（M5）待办（plan/04 §4、plan/06 M5 DoD）

1. **CLI 全子命令**：`report`（单文件 HTML）、`export`（Netscape 导回，`--apply-dedupe`/`--exclude-dead` 显式开关）、`run`（全链路编排 `--out-dir`）；`--help`/退出码契约/编码守卫/输出确定性全套。
2. **报告**：plan/04 §4.2 七节结构（摘要/失效/待复核/重复/未访问画像/建议清理/口径免责）；**资源零外链硬断言**（无 `<link>`/外链 script/img/@import/外部字体；CSS 内联；断网可开）；未探测项独立分区；报告渲染层零判定逻辑（只消费 check/dedupe 既有结论）。
3. **长期未访问画像**：aging 分档取 ruleset `aging.tiers_days`（[365,730,1095]）；`add_date=null` 单列"添加时间未知"；口径注明"以添加时间近似未访问"。
4. **导回**：Netscape HTML 导出往返解析一致（机器）+ 浏览器实际导入（人工，M5 验收记录）；HTML 转义纪律；默认不删不改。
5. **编排单一源**：report/export 只消费既有判定，无第二份判定逻辑；`run` 串 import/check/dedupe/report/export。
6. **收尾**：干净环境按 README 逐条跑通（记录退出码）→ 双基线复跑（bench + 全量测试）→ plan/00/04/06 回写 → HANDOFF-M6 → commit。

## 三、既定口径 K 清单（M4 沿用 M3 全部 K20–K22；K1–K19 见 plan/HANDOFF-M3.md §三）

M4 无新增冻结口径（基准是消费方，不改判定语义）。沿用关键纪律：
- **引擎不设 ruleset 参数默认值**（probe.timeout_s/redirect_max 缺失即 ValueError）；
- `serialize.py` 是 tree/check/dedupe 共用确定性写盘单点（M5 报告/导出如需确定性序列化也走它）；
- 锚点硬门 loader 与 test_data_gates 预览 loader 不得分叉语义；
- **M5 新红线**：报告渲染层零判定逻辑（plan/04 §4.4——单一渲染源雏形）；资源零外链硬断言。

## 四、本机环境坑（M4 实测增补；沿用 HANDOFF-M4 §四 E-1~E-16 全部条目）

- **E-17 本机 loopback 拒绝连接固定 ~2s/次**（防火墙过滤驱动；curl 交叉验证同值；listening 端口连接 4ms）：含 unreachable 场景的耗时预算按此校准（不可达 URL 每次 2 连接 = retry_max+1）。
- **E-18 pytest 全量（含 bench 端到端 9 项）单通道约 5 分钟**：超 Bash 606s 上限风险——长跑一律 `run_in_background` + TaskOutput 轮询；bench 测试用模块级 fixture 共享一次全量运行。
- **E-19 mock 主机多源重写的去重键塌缩陷阱**：跨来源同 URL 重写后探测一次扇回是优化（语义不变）；但**不同 mock 主机**若重写成同路径（如同为 200 场景），dedupe 对账会误报误合并——重写必须保留完整原路径 + 主机命名空间段（bench.py rewrite_url 注释详述）。
- **E-20 bench stdout 是 JSON 报告 + `[bench]` 摘要行混合流**：机器消费用 `--report <path>` 落盘文件；从 stdout 解析需配平花括号提取首个完整 JSON 文档（tests/test_bench.py `_parse_report`）。

## 五、M4 DoD checklist（逐项已验证）

- [x] B1–B6 套件 + manifest 门槛下发；false_dead=0 硬门
- [x] 探活打端到端入口；退出码三语义锁进测试
- [x] 指标写进 README（如实，未达标不预填）
- [x] 基线复跑记录（bench exit 0 + 双解释器 131 passed ×2）；HANDOFF-M5 落盘 + commit

### 2026-10-16 审计加固补录（M4 基准）

缺陷 2（基准保真）修复：bench mock 补发 `Location` 头形成**真实跳转链**（302→登录/访客页 200），
样本经 mock 主机别名规则**真经规则库**判定（不再零命中、不再靠通用映射）；新增
`false_alive` 门（反爬 302 不得判 alive）+ manifest 第四类覆盖 `review_not_alive_302`；
探活缺陷扩为 `403-dead` 与 `302-first-hop-ignored`（二者均须 exit 1）。
详见 `plan/06-里程碑与每周演示.md` M4 行与 `tools/bench.py` 注释。

## 六、关键命令速查（增量）

```bash
cd <项目根>
export PYTHONDONTWRITEBYTECODE=1

# 内置基准（B1–B6 全套；约 2 分钟——含挂起 20s×2 与不可达 4s 场景）
PYTHONPATH=src py -X utf8 tools/bench.py                 # exit 0 = 达标
PYTHONPATH=src py -X utf8 tools/bench.py --only B4       # 快速子集（2s）
PYTHONPATH=src py -X utf8 tools/bench.py --inject-defect 403-dead   # 探活：必须 exit 1
PYTHONPATH=src py -X utf8 tools/bench.py --report .tmp/bench.json   # 指标落盘

# 全量测试（双解释器；单通道约 5 分钟，建议后台跑）
PYTHONPATH=src py -X utf8 -m pytest -q
.venv/Scripts/python.exe -X utf8 -m pytest -q

# 数据资产 --check（回归防线）
PYTHONPATH=src py -X utf8 tools/gen_ruleset.py --check
PYTHONPATH=src py -X utf8 tools/gen_fixtures.py --check
```

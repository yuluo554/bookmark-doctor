# HANDOFF-M3 — 下一棒：M3 检测与去重

> 上一棒：M2 解析（2026-10-15 完成，本对话）。
> 启动方式：`/goal 读取 "plan/HANDOFF-M3.md" 继续完成任务`（会话侧拼项目绝对路径；库内一律相对路径）。

## 一、当前进度与证据

**M2 已完成**：双解析器 + UIR 冻结 + CLI import + 往返一致 + 守门测试（双解释器 43 passed ×2）。

| 项 | 证据 |
|---|---|
| 解析层 | `src/bookmark_doctor/parse/`：`errors.py`（ParseError 唯一异常通道）+ `netscape.py`（html.parser 子类流式状态机：`_in_h3`/`_in_anchor` 文本区间 + DL 深度栈；实体解码 convert_charrefs=True；ADD_DATE 非法→null；坏结构/悬空 H3/DL 不配平→ParseError）+ `chrome_json.py`（roots 三树递归；date_added 显式换算、常量必传**不写第二份**；"0"/非法/负→null；url 节点缺 url→ParseError） |
| UIR（冻结） | `model.py`：`build_tree`（按扩展名分派解析→逐源建条目）/ `merge_duplicates`（同 URL 合并、source 记全部来源、add_date 最早非空）/ `serialize_tree`（sort_keys+LF+结尾换行）。**UIR 冻结口径 K11–K18 见 §三** |
| CLI import | `bookmark-doctor import <files...> --out tree.json`（`--out -` 仅 stdout 摘要）。多文件→合并摘要（bookmarks_total / duplicate_groups_merged / add_date_null）；坏文件/缺失文件 exit 2 + stderr + **无半成品**（先全量解析成功才写盘，测试锁定） |
| 最小导出 | `export.py`：`export_netscape()` UIR→Netscape HTML 字节（完整 folder 路径嵌套重建；转义 & < > "）。**仅服务往返一致测试**；完整导回（--apply-dedupe/--exclude-dead/浏览器实测）仍在 M5 |
| 往返测试 | `tests/test_parse.py` 24 项：双格式"解析→导出→再解析"字段级相等；跨格式同构（27 对）；坏文件参数化（坏 JSON/空 HTML/坏结构/缺 roots）exit 2 + 无产物；混合好坏文件不落盘；同输入两次 serialize_tree 逐字节一致 |
| 双解释器 | 3.8.8 系统通道 **43 passed**；3.12.10 venv 通道 **43 passed**（19 旧 + 24 新） |
| 变异验证 | 2 次：①Netscape finish() 结构校验瘫痪（悬空 H3 + DL 不配平两检查同关）→ `test_parse_netscape_bad_structure` 红；②Chrome roots 非 dict 静默放行 → badroots 参数例红；还原后全绿。注：单瘫 H3 悬空检查时被 DL 配平检查兜住（冗余防线），故变异须同时关两道——属门的双重覆盖，非门失效 |
| 回写 | plan/00（状态/里程碑表 M2 ✅/测试计数 43）/ plan/04（§1.3 合并规则标注已冻结）/ plan/06（M2 DoD 全勾+证据）/ 索引表后续由 M3 补 src 新模块行 |

## 二、下一棒（M3）待办

1. **探测引擎 `probe.py`**：单次逻辑探测（HEAD；405/501 降级 GET 限读即断——合计算一次）；无 cookies；UA 取 ruleset `probe.user_agent`（单点）；跟随跳转至 `redirect_max` 并记录跳转链；超限/成环 → review(redirect_loop/too_many_redirects)；timeout/retries/delay_s 全取 ruleset；串行 + 降频。HTTP 通路用 `urllib.request` 自写 handler（plan/03 §3）。
2. **分类与规则引擎 `classify.py`**：状态分类表（plan/04 §2.2 冻结草案落地）；**规则优先于通用映射**；多规则冲突取保守（review > dead > alive）+ 备注冲突；锚点硬门复用 M1 判定顺序（先解析观测台账→再过滤规则；参考 tests/test_data_gates.py `_ruleset_loader_preview`，M2 未改动该顺序）；**未启用清单**（disabled 规则 + 原因）必须随 stderr/报告输出——防静默照判。
3. **URL 规范化 `normalize.py`（单点实现）**：plan/04 §3.1 六步流水线固定顺序；追踪参数名单取 ruleset `tracked_query_params`；原始 URL 永不改写；未实测短链不猜。
4. **去重 `dedupe.py`**：比较键 = normalize(url)（check.json 有 final_url 时优先用 normalize(final_url)）；重复组 + 建议保留项（https > 无追踪参数 > add_date 最早 > 文件序最早）；绝不自动删；fragment_variant 标记。
5. **CLI `check` / `dedupe` 子命令**：plan/04 附表参数规格；退出码契约同 import（文件级失败 exit 2；单 URL 网络失败落 review 不中断）。
6. **零字面量门禁**：扫描 src/ 不得出现 probe 数值/平台主机名第二份（豁免口径写死：tools/ 生成器是合法单点，见 HANDOFF-M2 §三 K5 纪要）+ 变异验证。
7. **收尾**：mock 站点全场景对照（403/302/521/404/410/200/环跳/挂起/unreachable）；同输入同 ruleset → check.json 逐字节一致（mock 环境）；双解释器全量 → plan/00/04/06 回写 → HANDOFF-M4 → commit。

## 三、既定口径 K 清单（M2 增补 K11–K18；K1–K10 原文见 plan/HANDOFF-M1.md §三）

- **K11 UIR schema**：`bookmark-doctor.tree-v1`；顶层字段 `schema` / `sources`（来源声明顺序）/ `chrome_epoch_delta_us`（K12 正本回显）/ `bookmarks`。条目字段六件套：`id` / `title`（缺失 null）/ `url`（原文永不改写）/ `add_date`（epoch 秒；缺失/非法 null，不猜补）/ `folder`（路径列表，根→直接父）/ `source`。
- **K12 Chrome 纪元常量单点**：`chrome_epoch_delta_us = 11644473600000000` 唯一正本 = `data/fixtures/set-1/manifest.json`；解析器/引擎**不得写字面常量**，一律 `model.load_chrome_epoch_delta(repo_root)` 读取（M4 基准改路径时只动正本）。
- **K13 Netscape 解析语义**：`<DT><H3>` 文件夹（其后 `<DL>` 为其内容）；`<DT><A HREF ADD_DATE>` 书签；`<DL>` 嵌套=层级；实体解码（convert_charrefs）；`ADD_DATE` 纯数字（可负）→int，缺失/空/非法→null；悬空 H3 / DL 下溢 / 收尾不配平 → ParseError。
- **K14 ADD_DATE/日期语义**：null ≠ 0 ≠ 1970——未知就是 null，下游（长期未访问分档）单列"添加时间未知"，禁止猜补。
- **K15 坏结构语义**：Netscape 结构坏（悬空 H3 / DL 配平破坏 / `<DT><A>` 缺 HREF）与 Chrome 结构坏（顶层非对象 / 缺 roots / url 节点缺 url）→ ParseError → CLI exit 2，不落半成品；"文件不能用"与"条目有问题"（exit 0 进报告）语义分离不变。
- **K16 Chrome 解析语义**：roots 三树（bookmark_bar/other/synced，缺树跳过）；type 区分 folder/url；date_added ≤0 或换算为负 → null；name 缺失 → null；未知 type 跳过。
- **K17 id 派生**：`id = sha1("{source}|{seq}")[:12]`，seq = 来源内 1 起文件序（与 M1 gen_fixtures `_bm_id` 同式）；条目顺序 = (来源声明顺序, 来源内文件序)，**不做跨源全局重排**。
- **K18 序列化纪律**：tree.json = `json.dumps(sort_keys=True, ensure_ascii=False, indent=2)` + LF + 结尾换行；无时间戳/时钟/随机；同输入逐字节一致（测试锁定）。
- **K19 跨格式比对边界（M2 实测登记）**：Chrome 根树顶层（书签栏/其他书签/移动设备书签）是浏览器来源差异，非解析差异——跨格式同构比对不覆盖 folder[0]（gen_fixtures 把 4 个文件夹轮转分放三棵根树；Netscape 全在根 DL）。M4 基准对账同此口径。
- 沿用 M1 纪要：K4 锚点门判定顺序（先台账后规则）；K5 零字面量豁免含 tools/ 生成器；pending 观测升级 verified 后的三联动流程。

## 四、本机环境坑（只写本轮实测过的）

- 沿用 HANDOFF-M2 §四 E-1~E-10 全部条目（双解释器通道 / pip 镜像 / PYTHONDONTWRITEBYTECODE / git 邮箱 / 无远端 / Git Bash heredoc 失灵→落脚本文件 / mock /hang 语义 / taskkill 双斜杠）。本轮全部再次验证有效。
- **E-11 `Path.write_text(newline=)` 是 3.10+ 参数**：变异验证脚本在 3.8 系统通道 TypeError——改 `open(path, 'w', encoding='utf-8', newline='')` + write。产品代码同样守此纪律（plan/03 §6 已有，本轮实证）。
- **E-12 heredoc 内嵌 python -c 的引号转义**：Git Bash 通道 `py -c "..."` 内含换行脚本可用，但内部再嵌套引号易错；复杂变异逻辑落 `.py` 临时文件更稳（E-8 同源）。
- **E-13 CLI 文件参数**：Git Bash 传 `/nonexistent.html` 会被 MSYS 路径改写为安装目录（如 `D:\program\Git\nonexistent.html`）——测试断言用 tmp_path 绝对 Windows 路径，不受影响；人工冒烟时留意。

## 五、M2 DoD checklist（逐项已验证）

- [x] Netscape HTML / Chrome JSON 双解析器 + 合并（未知不猜补：缺 ADD_DATE/date_added="0" → null，测试断言）
- [x] 双格式往返一致（合成集 27 条回归：解析→导出→再解析字段级相等；跨格式 27 对同构）
- [x] 坏文件 → stderr 报错 + exit 2 + 无半成品（参数化 4 类 + 缺失文件 + 混合好坏，全部锁定）
- [x] UIR 字段冻结为 K 清单条目（K11–K19）；tree.json 确定性（逐字节一致测试）
- [x] 解析器配生成器样例回归（set-1 真产物喂解析器，非手搓最小样例）
- [x] 全量测试绿（3.8.8：43 passed；3.12.10：43 passed）
- [x] 新守门变异验证（2 次：破坏 → 红 → 还原 → 绿）
- [x] plan/00、04、06 回写 + HANDOFF-M3 落盘 + commit

## 六、关键命令速查（增量）

```bash
cd <项目根>
export PYTHONDONTWRITEBYTECODE=1

# 全量测试（双解释器）
PYTHONPATH=src py -X utf8 -m pytest -q
.venv/Scripts/python.exe -X utf8 -m pytest -q

# CLI import 冒烟
PYTHONPATH=src py -X utf8 -m bookmark_doctor import data/fixtures/set-1/bookmarks.netscape.html --out -
PYTHONPATH=src py -X utf8 -m bookmark_doctor import data/fixtures/set-1/bookmarks.netscape.html data/fixtures/set-1/bookmarks.chrome.json --out tree.json

# 数据资产 --check（回归防线，双解释器）
PYTHONPATH=src py -X utf8 tools/gen_ruleset.py --check
PYTHONPATH=src py -X utf8 tools/gen_fixtures.py --check
```

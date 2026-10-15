# HANDOFF-M2 — 下一棒：M2 解析

> 上一棒：M1 数据先行（2026-10-15 完成，本对话）。
> 启动方式：`/goal 读取 "plan/HANDOFF-M2.md" 继续完成任务`（会话侧拼项目绝对路径；库内一律相对路径）。

## 一、当前进度与证据

**M1 已完成**：三类数据资产落库 + 守门测试 + mock 站点 + 双解释器全绿（18 passed ×2）。

| 项 | 证据 |
|---|---|
| 实测台账 | `data/measurements/observations.{json,md}`（sha256 登记于 `checksums.txt`，守门测试实算对账+变异验证）：2026-10-15 本机 curl 实测 10 条。**verified 7**：GitHub 200 基线 / 微信平台 200 / 知乎首页 302→signin / 知乎问题页 403 / 微博 302→passport visitor / CSDN 博客 521 / B站首页 200（本次环境）。**pending 3**：B站 301/302 声明项、掘金 521 声明项（本机未复现，不编造）、掘金首页 200 观测随文登记。差异登记见 observations.md §三 |
| 规则包 v1 | `data/rules/ruleset.json`（schema `bookmark-doctor.ruleset/1`，revision 1，version `f846f1cb820d` = 内容哈希前 12 位）：probe（timeout 10s / retry 1 / delay 0.5s / redirect_max 5 / UA 固定形态）+ 4 条 degrade_rules（R-ZHIHU-403 / R-ZHIHU-302 / R-WEIBO-302 / R-CSDN-521，**全挂 verified 锚点**）+ tracked_query_params + aging tiers [365,730,1095] + similarity 0.9。**B站/掘金无规则**（锚点 pending，K4） |
| 合成集 | `data/fixtures/set-1/` 四件套（seed 20261015，27 条）：`bookmarks.netscape.html` + `bookmarks.chrome.json`（**Chrome date_added 纪元换算已对账**：epoch 秒×10⁶+11644473600000000，抽样验算过）+ `truth.json`（只存输入与期望：dead 3 / review 11〔反爬 3+不可达 2+DNS 假域 6〕/ alive 13 / add_date_null 1 / 重复 4 组 12 件；分桶互斥且全覆盖）+ `manifest.json`（coverage 应有=实际覆盖 4 类；文件 sha256 表；mock 场景映射表） |
| 生成器 | `tools/gen_ruleset.py` / `tools/gen_fixtures.py`：splitmix64 确定性 RNG、无时钟、显式 sort、`--check` 位级一致（双解释器实测通过）；锚点解析失败/未复核在生成端即 SystemExit |
| mock 站点 | `tools/mock_site.py`：`/status/{200,301,302,403,404,410,521}`、`/redirect/{301,302}`→`/final/200`、`/redirect/loop` 自环、`/hang` 挂起至客户端断开（curl 超时 exit 28 实测）、未知名 404；仅 loopback（`_assert_loopback` 硬门）；curl 全场景冒烟通过 |
| 守门测试 | `tests/test_data_gates.py` 6 项：锚点硬门 loader 预览（含 pending/缺锚点合成反例）、pending 观测支撑零规则反向断言、两个生成器 `--check` 子进程真跑、data 无 CR 门 |
| 变异验证 | 三门全做过：①ruleset 改一字节 → frozen 门红；②data 注入 CR → no-CR 门红；③规则引用观测改名 → 锚点门红（loader disabled + reason=anchor_missing，另由独立脚本复核）；还原后全绿 |
| 双解释器 | 3.8.8 系统通道 **18 passed**；3.12.10 venv 通道 **18 passed** |
| 回写 | plan/00（索引/台账/里程碑表 M1 ✅/测试计数 18）/ plan/05（D-1~D-4 状态 ✅）/ plan/06（M1 DoD 全勾）/ 三个 data README 状态行 |

## 二、下一棒（M2）待办

1. **UIR 冻结**：`tree.json` 字段定稿（id=sha1(source|seq) 前 12 位 / url 原文 / title / add_date（null 不猜补）/ source / 文件内序号 / 文件夹路径树）→ 写入 K 清单（K11 起）。
2. **Netscape HTML 解析器**（`html.parser` 子类）：`<DT><H3>` / `<DT><A HREF ADD_DATE>` 流式；实体解码；ADD_DATE 非法 → null；坏结构显式报错。
3. **Chrome JSON 解析器**：roots 三树递归；`date_added` 换算（换算常量以 manifest `chrome_epoch_delta_us` 为准——**不要在解析器里写第二份常量**，零字面量纪律从 M2 起预热）。
4. **CLI `import` 子命令**：多文件输入 → tree.json + 合并摘要（stdout）；退出码契约（坏文件 exit 2 无半成品）。
5. **往返一致测试**：合成集 set-1 双格式 解析→导出→再解析 字段级相等（export 逻辑最小内实现或直接比对 UIR）。
6. **守门**：解析失败样本（坏 HTML / 坏 JSON / 空文件）→ exit 2 测试；变异验证一次。
7. **收尾**：双解释器全量 → plan/00/04/06 回写（UIR 冻结进 K 清单）→ HANDOFF-M3 → commit。

## 三、既定口径 K 清单（沿用 HANDOFF-M1 §三，M1 无增补修订；K1–K10 原文见 plan/HANDOFF-M1.md）

M1 新增操作纪要（不改变 K 条目本体）：
- K4 锚点硬门已在**生成端前置**（gen_ruleset.py 对锚点解析失败/未复核直接 SystemExit），测试端 loader 预览为第二道门（tests/test_data_gates.py）；M3 正式引擎实现时复用同一判定顺序（先解析观测台账 → 再过滤规则）。
- K5 冻结纪律：两个生成器的数值口径都写在生成器顶部常量区（ruleset 的阈值在 gen_ruleset.py，合成集的结构性常量在 gen_fixtures.py）；M3 零字面量门禁扫描 src/ 时注意豁免口径要包含 tools/ 生成器（它们是数值的合法单点）。
- pending 观测（B站 301/302、掘金 521）**复核升级 verified 后**：改 observations.json → 追加规则进 gen_ruleset.py DEGRADE_RULES → 整目录重生成 + `--check` + 三联动更新（同一提交）。

## 四、本机环境坑（只写本轮实测过的）

- 沿用 HANDOFF-M1 §四 E-1~E-7 全部条目（双解释器通道 / egg-info 位置效应 / pip 镜像+NO_PROXY / PYTHONDONTWRITEBYTECODE / data README 占位 / git 邮箱 / 无远端）。本轮全部再次验证有效。
- **E-8 Git Bash heredoc**：`python - <<'EOF'` 在本机 Git Bash 通道不稳定（exit 49 静默失败）；改用 `cat > file.py <<'EOF'` 落脚本文件再 `py -X utf8 file.py` 执行。
- **E-9 mock 站点挂起语义**：`/hang` 用"阻塞读至客户端断开"实现（不依赖时钟差值）；curl 客户端超时 exit 28 已实测。ThreadingHTTPServer 线程在客户端断开后自行退出。
- **E-10 taskkill 杀后台进程**：mock 站点后台启动后用 `netstat -ano | grep LISTENING` 找 PID → `taskkill //PID <pid> //F`（Git Bash 双斜杠）。

## 五、M1 DoD checklist（逐项已验证）

- [x] 实测记录：锚点站点逐条复测（verified 7 + pending 3，诚实口径差异登记；无编造观测）
- [x] ruleset v1：4 条规则 anchor 全部可解析且 verified；pending 观测支撑零规则（测试断言 + 变异验证）
- [x] 合成集：双格式 + truth（只存输入与期望）+ manifest（三类易错形态件数登记，应有=实际覆盖）
- [x] 生成器 `--check` 位级一致（gen_ruleset + gen_fixtures × 双解释器 = 4 组实测通过）
- [x] 全量测试绿（3.8.8：18 passed；3.12.10：18 passed；含锚点门/冻结门/无 CR 门三项新守门）
- [x] 新守门变异验证（三门各一次：破坏 → 红 → 还原 → 绿）
- [x] mock_site.py 雏形（全场景 curl 冒烟 + loopback 硬门 + 挂起超时语义实测）
- [x] plan/00、05、06 回写 + data README ×3 状态行 + HANDOFF-M2 落盘 + commit

## 六、关键命令速查（增量）

```bash
cd <项目根>
export PYTHONDONTWRITEBYTECODE=1

# 数据资产 --check（双解释器）
PYTHONPATH=src py -X utf8 tools/gen_ruleset.py --check
PYTHONPATH=src py -X utf8 tools/gen_fixtures.py --check
.venv/Scripts/python.exe -X utf8 tools/gen_ruleset.py --check
.venv/Scripts/python.exe -X utf8 tools/gen_fixtures.py --check

# 重新生成（改生成器后整目录重生成，禁手改产物）
PYTHONPATH=src py -X utf8 tools/gen_ruleset.py
PYTHONPATH=src py -X utf8 tools/gen_fixtures.py

# mock 站点（后台起 + 冒烟 + 杀）
PYTHONPATH=src py -X utf8 tools/mock_site.py --port 8765 &
curl -sS -o /dev/null -m 5 -w '%{http_code}\n' http://127.0.0.1:8765/status/403
# 杀：netstat -ano | grep :8765 → taskkill //PID <pid> //F
```

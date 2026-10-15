# bookmark-doctor（收藏夹体检工具 · 中文站点友好）

> **状态：开发中（M5 交付已就绪，全链路闭环）** —— 计划文档、数据资产、检测/去重引擎、内置基准与 `report`/`export`/`run` 全子命令已落盘（见 [plan/06-里程碑与每周演示.md](plan/06-里程碑与每周演示.md)）。CI 配置已就位（**未接远端，待首次推送验证**）。

导入浏览器导出的 `bookmarks.html`，一次跑完失效检测 + 重复合并 + 长期未访问画像 + 一键导回，**并专门适配中文站点**——微信文章 / 知乎 / B站 / 微博的链接不能按普通 HTTP 状态一刀切。零依赖、纯本地 CLI（不是浏览器扩展）。

## 为什么需要它

- **失效检测一刀切，中文站点被误杀**：通用链接检查器把"非 200 = 失效"，而知乎对非浏览器请求返回 403、微博返回 302、掘金/CSDN 常被 CDN 反爬拦截返回 521——这些链接在浏览器里打开完全正常。本项目把这些响应特征做成**版本化降级规则库**（每条规则挂实测记录锚点），一律判"**待复核**"、不判失效。
- **收藏夹只增不减，重复越滚越多**：同一篇文章从不同入口被收藏多次（带 `utm_*` 追踪参数、短链 vs 长链、http vs https）——URL 规范化一键归组。
- **"存了就等于看过"的错觉**：基于添加时间的长期未访问画像，给出分档与建议清理清单。
- **导不回浏览器，闭环断在最后一步**：支持一键导回为浏览器可导入的 Netscape Bookmark HTML。

## 判定语义（先读这条）

判定区分三态：**存活 / 失效 / 待复核**。

- 网络不可达（DNS 失败、超时）与 403/521 反爬拦截 **一律判"待复核"，绝不判失效**；
- "未探测"不会被说成"存活"——报告显式标注数据来源与覆盖；
- 判定为**辅助参考**：链接是否真正失效以你的浏览器实际打开为准。

## 快速开始（开发态，立即可用）

```bash
# 1. 建虚拟环境（Windows 上若 `python` 是商店占位符，改用 `py -3 -m venv .venv`）
python -m venv .venv

# 2. 激活（Windows: .venv\Scripts\activate ｜ macOS/Linux: source .venv/bin/activate）

# 3. 升级 pip（Python 3.8 自带 pip 20 不支持 pyproject 可编辑安装，必须先升）
python -m pip install --upgrade pip

# 4. 可编辑安装（含测试依赖）
python -m pip install -e ".[dev]"

# 5. 冒烟
bookmark-doctor --version
bookmark-doctor --selftest

# 6. 跑测试
python -m pytest

# 7. 一条命令跑全链路（import → check → dedupe → report → export）
PYTHONPATH=src py -X utf8 -m bookmark_doctor run data/fixtures/set-1/bookmarks.netscape.html --out-dir out --probe-date 2026-01-01
#    产物在 out/：tree.json / check.json / dedupe.json / report.html / bookmarks-export.html
#    report.html 是单文件 HTML（CSS 内联、零外链），断网双击可开

# 8. 内置基准（B1–B6，离线；见下方"内置基准"节）
PYTHONPATH=src py -X utf8 tools/bench.py
```

## 规划中的完整能力（按里程碑开放）

| 子命令 | 能力 | 里程碑 |
|---|---|---|
| `import` | Netscape HTML / Chrome·Edge JSON 导入与多源合并 | M2 |
| `check` | 中文站点感知失效检测（降级规则库 + 锚点硬门） | M3 |
| `dedupe` | URL 规范化去重（剥追踪参数 / http-https 归一 / 已实测短链映射） | M3 |
| `report` | 本地单文件 HTML 报告（失效 / 待复核 / 重复 / 未访问画像 / 建议清理）✅ | M5 |
| `export` | 一键导回浏览器可导入的 Netscape Bookmark HTML（默认不删不改；`--apply-dedupe`/`--exclude-dead` 显式开关）✅ | M5 |
| `run` | 一条命令串起全流程 ✅ | M5 |

## 内置基准（M4：可证明达标，一键复跑）

合成书签集（`data/fixtures/set-1`，27 条植入真值）真喂引擎（解析 → 探测 → 分类 / 去重），与 `truth.json` 对账——全程离线（仅 loopback mock，断网可复跑）：

```bash
PYTHONPATH=src py -X utf8 tools/bench.py            # B1–B6 全套件；exit 0 = 达标
PYTHONPATH=src py -X utf8 tools/bench.py --only B4  # 只跑指定套件；未知名 exit 2
PYTHONPATH=src py -X utf8 tools/bench.py --inject-defect 403-dead   # 探活：注入缺陷必须 exit 1
```

- 门槛是数据非代码：命中率 / 覆盖件数门槛读取自 `manifest.json`（缺失即配置错误 exit 2）；
- `false_dead`（真值为存活/待复核却被判失效）= **0 硬门**；
- 探活可证伪：注入"403 通用映射改判失效"缺陷 → 基准必须报未达标（exit 1）——作为常驻测试锁进 `tests/test_bench.py`。

### 评测结果（2026-10-15 实测，set-1 合成集）

| 套件 | 指标 | 结果 | 门槛（manifest 下发） |
|---|---|---|---|
| B1 分类·反爬类 | 403/302/521 → 待复核命中率 | 3/3（100%） | ≥3 件；误判失效数 = 0 ✅ |
| B2 分类·不可达类 | DNS 失败/超时 → 待复核命中率 | 8/8（100%） | ≥2 件；误判失效数 = 0 ✅ |
| B3 分类·死链类 | 404/410 → 失效命中率 | 3/3（100%） | ≥3 件 ✅ |
| B4 分类·规则驱动 | 规则×通用映射全组合断言（含反向样例） | 372/372 通过（4 条生效规则） | 100% ✅ |
| B5 去重类 | 真值重复组合并率 / 误合并 | 4/4（100%）/ 0 | ≥4 组；误合并 = 0 ✅ |
| B6 一致性 | 同输入两次运行逐字节一致 | 一致 | 位级一致 ✅ |

口径说明（诚实边界）：以上为**合成集上的行为对账**（植入真值的抽样覆盖，非穷举——覆盖声明见 `manifest.json` `coverage` 节，"应有/实际覆盖"双数登记）；真值库只存"输入与期望"，观测字段由基准运行时实算。

## 本地报告与导回（M5）

```bash
# 全链路：一条命令出全部产物
PYTHONPATH=src py -X utf8 -m bookmark_doctor run <书签文件...> --out-dir out --probe-date 2026-01-01

# 或分步：报告 / 导回
PYTHONPATH=src py -X utf8 -m bookmark_doctor report out/tree.json --check out/check.json --dedupe out/dedupe.json --out report.html
PYTHONPATH=src py -X utf8 -m bookmark_doctor export out/tree.json --out bookmarks-export.html
# 显式动作（默认不删不改；开关须配套产物，缺失 exit 2）：
PYTHONPATH=src py -X utf8 -m bookmark_doctor export out/tree.json --dedupe out/dedupe.json --apply-dedupe --out cleaned.html
PYTHONPATH=src py -X utf8 -m bookmark_doctor export out/tree.json --check out/check.json --exclude-dead --out cleaned.html
```

- **报告**：单文件 HTML、分节固定（摘要 / 失效 / 待复核 / 重复 / 长期未访问画像 / 未探测条目 / 建议清理 / 口径与免责）；CSS 内联、零外链（无 `<link>`/外部 script/img/@import/外部字体），**断网可开**；渲染层零判定逻辑——只消费 check/dedupe 既有结论，未探测条目独立分区不混入三态。
- **长期未访问画像**：分档阈值取 ruleset `aging.tiers_days`（1年+ / 2年+ / 3年+）；`add_date` 未知条目单列不计档；口径注明"以添加时间近似未访问"。
- **导回**：标准 Netscape Bookmark HTML，浏览器书签管理器可直接导入；默认全量导回；导出文件已验证"导出 → 再解析"往返逐条一致。
- **编排单一源**：`run` 直接复用各子命令实现串接（import → check → dedupe → report → export），无第二份判定逻辑；任一步失败即停止，解析失败不落半成品。

## 计划与文档

| 文档 | 内容 |
|---|---|
| [plan/00-README总览.md](plan/00-README总览.md) | 总览、决策记录、待定决策表 |
| [plan/01-题目文档.md](plan/01-题目文档.md) | 需求原文 |
| [plan/02-需求解读与能力转译.md](plan/02-需求解读与能力转译.md) | 功能清单（含优先级）与非功能需求 |
| [plan/03-架构与技术选型.md](plan/03-架构与技术选型.md) | 架构、选型、目录结构、CI 与编码纪律 |
| [plan/04-模块详设.md](plan/04-模块详设.md) | 五个模块的接口、判定语义与验收判据 |
| [plan/05-数据计划与基准计划.md](plan/05-数据计划与基准计划.md) | 数据资产台账、冻结纪律、基准设计 |
| [plan/06-里程碑与每周演示.md](plan/06-里程碑与每周演示.md) | 里程碑 DoD 与演示物 |
| [data/README.md](data/README.md) | 数据依据查证记录与数据纪律 |

## 合规与隐私（硬承诺）

- **零上传**：书签内容、判定结果、报告、导出文件全部不出本机；
- **单次探测**：只对用户自有书签做单次探测；不批量爬取、不登录、不抓取页面内容、遵守降频；
- 探测请求不携带任何用户标识（不发送 cookies / 登录态）。

## 开发说明

- 运行时**零第三方依赖**（纯 Python 标准库）；测试期依赖仅 `pytest`（`[dev]` extras）。
- 目录结构：`src/bookmark_doctor/`（包）、`tools/`（生成器 / 基准 / 审计脚本）、`data/`（规则库 / 合成集 / 实测记录）、`tests/`。
- CI：GitHub Actions 三矩阵（windows×{3.8, 3.12} + ubuntu×3.12）；**待首推验证**。

## License

[MIT](LICENSE)

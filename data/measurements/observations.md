# 中文站点实测记录台账（observations）

- 机读正本：[`observations.json`](observations.json)（规则锚点解析源；本文件与之同批更新）。
- 观测日期：**2026-10-15**（全部本机实测；工具 = curl，Git Bash 通道）。
- 合规口径：单次探测 / 不登录 / 不抓内容 / 站间降频 ≥3s；**只记状态行 / 重定向链 / Location 等关键头部，不落响应正文**（红线，见 data/README §1.3）。
- 探测 UA：`BookmarkDoctor-Observation/0.1 (single-shot status check; +local measurement)`（ruleset 冻结时以此形态为准）。
- `check_status`：`verified` = 已复核可支撑规则生效；`pending` = 待复核，**不支撑任何规则生效**（锚点指到 pending → 规则进"未启用清单"）。

## 一、台账正文（与 observations.json 一一对应）

| 观测 ID | 站点 | 样例 URL | 状态 | 三态含义 | check_status | 备注 |
|---|---|---|---|---|---|---|
| OBS-20261015-github-home-200 | GitHub（通用站基线） | https://github.com/ | **200** | 可直连 | verified | 基线对照，落通用映射 |
| OBS-20261015-weixin-mp-home-200 | 微信公众平台 | https://mp.weixin.qq.com/ | **200** | 可直连 | verified | 文章页形态同日实测亦 200（data/README §1.2） |
| OBS-20261015-zhihu-home-302 | 知乎 | https://www.zhihu.com/ | **302 → signin** | 登录跳转 | verified | 跟随终态 200 = 登录页；深链 403 见下条 |
| OBS-20261015-zhihu-question-403 | 知乎 | https://www.zhihu.com/question/19550227 | **403** | 反爬（非失效） | verified | 非浏览器 UA bot 拦截；/api/v4 亦 403；浏览器可正常打开 |
| OBS-20261015-weibo-home-302-visitor | 微博 | https://weibo.com/ | **302 → passport visitor** | 风控跳转（非失效） | verified | 非登录态跳访客风控链；链含动态 `_rand`，运行时以实际链为准 |
| OBS-20261015-csdn-blog-521 | CSDN | https://blog.csdn.net/github_38482082/article/details/82190371 | **521** | CDN 反爬（非失效） | verified | 博客深链非浏览器 UA 521；浏览器可正常打开 |
| OBS-20261015-bilibili-home-200 | B站 | https://www.bilibili.com/ | **200** | 可直连 | verified | 本次环境首页/视频页均 200，题面 301/302 未复现 |
| OBS-20261015-bilibili-redirect-claim | B站 | （待提供复现样例） | —（未复现） | — | **pending** | 题面称 301/302；本机未复现，不编造，待跨环境复核 |
| OBS-20261015-juejin-home-200 | 掘金 | https://juejin.cn/ | **200** | 可直连 | verified | 本次环境首页/用户页 200、失效文章 404 |
| OBS-20261015-juejin-521-claim | 掘金 | （待提供复现样例） | —（未复现） | — | **pending** | 题面称 521；本机未复现；CSDN 同形态已 verified |

## 二、复跑命令（工具与形态逐条对应）

```bash
UA="BookmarkDoctor-Observation/0.1 (single-shot status check; +local measurement)"
# 状态行（不跟随）——403/521/302 首跳观测：
curl -sS -o /dev/null -m 20 -A "$UA" -w 'code=%{http_code} loc=%header{location}\n' <URL>
# 跳转链（跟随）——302 终态观测：
curl -sS -L -o /dev/null -m 20 -A "$UA" -w 'final_code=%{http_code} n=%{num_redirects} final=%{url_effective}\n' <URL>
# 站与站之间 sleep 3 降频；全部命令 2026-10-15 本机实测通过
```

## 三、当日实测与题面锚点的差异登记（诚实口径）

- 知乎 403 / 微博 302→visitor / CSDN 521：**复现**，`verified`，可支撑降级规则锚点。
- B站 301/302、掘金 521：**本次网络环境未复现**（首页/深链均 200 或正常 404）。按 K7 诚实口径不编造观测：各立一条 `pending` 观望记录，**不挂任何规则**；待跨环境复核后升级 verified 或删除。
- 未提供复现样例的 pending 观测：`url` 字段为 `null`（缺失字段一律 null，不猜补）。

## 四、完整性登记

sha256 登记纪律（闭环，plan/05 §2）：两份正本的哈希登记在 **`checksums.txt`**
（sha256sum 格式；其自身不在登记范围——避免"文件含自身哈希永不收敛"的自指问题）。
守门测试 `tests/test_data_gates.py::test_observation_ledger_sha256_registered`
实算两份正本并断言与 `checksums.txt` 一致：台账内容变更 → 测试红 → 重算登记
（同一次提交内完成，不留第二份会漂移的口径）。本文件 §四 不重复登记哈希值，
只登记"登记处指向"（单一事实源）。

| 文件 | 用途 | 登记处 |
|---|---|---|
| `observations.json` | 机读正本（规则锚点解析源） | `checksums.txt`（守门测试实算对账） |
| `observations.md` | 人读台账（本文件，含复跑命令与差异登记） | 同上 |

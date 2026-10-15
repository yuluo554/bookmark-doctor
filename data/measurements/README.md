# data/measurements/ — 中文站点实测记录台账

M1 起收录中文站点状态**实测记录**（降级规则库的锚点来源）：

- 逐条记录：站点 / 样例 URL / HTTP 状态 / 重定向链 / 工具 / **观测日期** / 查证状态（`verified` / `pending`） / 备注；
- 探测合规：**单次探测、不登录、不抓内容、遵守降频**（见 `data/README.md §1.3`）；不存响应正文；
- 人读台账 `observations.md` + 机读 `observations.json`（规则锚点解析源），两者 sha256 登记；
- `check_status=pending` 的观测**不支撑规则生效**（锚点指向 pending → 规则进"未启用清单"）。

字段规范：见 `plan/05` §2。

状态：⬜ 待 M1 产出。

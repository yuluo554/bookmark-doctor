# data/fixtures/ — 合成书签集与植入真值

M1 起收录程序化生成的**合成书签集**（Netscape HTML + Chrome JSON 双格式）与**植入真值**：

- 布局草案：`data/fixtures/<set-id>/`（双格式书签文件 + `truth.json` + `manifest.json`）；
- URL 一律使用保留示例域名（`*.invalid`），**零真实站点 URL**；反爬场景由本地 mock 站点模拟；
- 真值只存"输入与期望"（不存 `observed` 类字段——观测必须由基准运行时实算）；
- 生成器 `tools/gen_fixtures.py` 冻结：固定 seed、无时钟、`--check` 位级一致。

数据纪律总纲：见 `data/README.md §3`（合成数据纪律）。

状态：⬜ 待 M1 产出。

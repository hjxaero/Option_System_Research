# 期权快照清洗与 IV 曲面 v0

## 目标

第一阶段目标不是做出最漂亮的 IV 曲面，而是做出可追溯、可复现、不会偷偷污染策略的数据底座。IV 曲面宁愿有洞，也不要把脏数据平滑成看起来合理的数值。

## 标准快照表

每一行是一只期权在某个时间点的状态。

必备字段：

| 字段 | 说明 |
| --- | --- |
| `timestamp` | 标准分钟时间点 |
| `symbol` | 期权合约代码 |
| `term_role` | 当月、次月、当季、次季 |
| `expiry_date` | 到期日 |
| `option_type` | `call` / `put` |
| `strike_price` | 行权价 |
| `underlying_symbol` | 标的代码 |
| `underlying_price` | 标的价格 |
| `futures_symbol` | 用于定价的期货合约 |
| `futures_price` | 用于定价的 forward/futures 输入 |
| `bid_price1` | 买一价 |
| `ask_price1` | 卖一价 |
| `bid_volume1` | 买一量 |
| `ask_volume1` | 卖一量 |
| `last_price` | 最新价 |
| `open_interest` | 持仓量 |
| `volume` | 成交量 |
| `mark_price` | IV/Greeks 使用的定价价格 |
| `price_source` | `micro`、`mid`、`last_inside_spread`、`last`、`none` |
| `spread_bps` | 买卖价差，单位 bps |
| `quote_time` | 盘口来源 tick 时间 |
| `quote_age_ms` | 盘口距离标准分钟时间点的延迟 |
| `quote_quality` | 盘口质量标签 |
| `iv` | 原始反解 IV |
| `iv_quality` | IV 质量标签 |
| `iv_method` | `calc`、`interp`、`smooth`、`none` |

## 盘口清洗

不要直接用 `last_price` 算 IV。价格输入优先级：

1. `bid_price1` / `ask_price1` 都有效且价差正常：用 `micro_price` 或 `mid_price`。
2. 盘口有效但价差太宽：保留价格，但降级标记。
3. `last_price` 在买卖价之间：可作为降级输入。
4. 只有 `last_price`：低质量 fallback。
5. 没有有效价格：不算 IV。

常见脏数据规则：

- `bid_price1 <= 0` 或 `ask_price1 <= 0`：标记 `invalid_bid_ask`。
- `ask_price1 < bid_price1`：标记 `crossed_market`。
- `spread_bps` 过大：标记 `wide_spread`。
- `quote_age_ms` 超过阈值：标记 `stale_quote`。
- 到期时间 `t <= 0`：不算 IV。
- 期权价格低于理论边界：标记 `below_intrinsic`。
- 深度虚值且价格接近最小 tick：保留但降级。
- 成交量和持仓量都为 0：标记低流动性。

深虚值、远月或低活跃合约即使历史 tick 已完整下载，也可能长期没有有效盘口。这类节点属于市场流动性限制，不应继续强行补下载，也不应被平滑成正常 IV。第一阶段默认保留原始快照并在 IV/曲面层排除，待后续接入更好的深度行情或模型化外推能力后再升级。

## IV 反解

初期使用 Black-76 为主，因为中国股指期权用对应股指期货价格做 forward 输入通常更稳定。后续可按品种切换：

- 现货指数输入：Black-Scholes。
- 股指期货输入：Black-76。

到期时间 `T` 必须按交易分钟流逝计算，不能在每天开盘时直接少算一整个到期日。MO 第一阶段约定：

- 一天按 240 个交易分钟。
- 一年按 252 个交易日。
- `T = 剩余交易分钟 / (252 * 240)`。
- 夜间不扣减交易分钟，开盘不会因为日历天变化产生 IV 跳跃。
- 快照可以保留开盘、午盘边界和收盘状态点；T 的衰减仍只按 240 个交易分钟计算。
- 后续接入真实交易日历，但接口保持交易分钟口径。

IV 求解只写入直接可解释的结果：

- 直接求解成功：`iv_method=calc`，`iv_quality=ok` 或相应降级标签。
- 无有效价格：`iv_quality=no_price`。
- 低于内在价值：`iv_quality=below_intrinsic`。
- 求解失败：`iv_quality=solve_failed`。

## IV 曲面表

曲面表从标准快照表派生，不覆盖原始快照。

字段：

| 字段 | 说明 |
| --- | --- |
| `timestamp` | 标准分钟时间点 |
| `expiry_date` | 到期日 |
| `term_role` | 四期限角色 |
| `strike_price` | 行权价 |
| `option_type` | `call` / `put` |
| `moneyness` | `strike_price / futures_price` |
| `log_moneyness` | `ln(strike_price / futures_price)` |
| `delta` | 期权 delta |
| `t_years` | 年化到期时间 |
| `raw_iv` | 原始反解 IV |
| `smooth_iv` | 平滑后 IV |
| `iv_quality` | 质量标签 |
| `surface_quality` | 曲面节点质量标签 |

曲面结构：

- x 轴：`moneyness`、`log_moneyness` 或 `delta`
- y 轴：到期时间
- z 轴：implied volatility

## 曲面平滑 v0

第一阶段不做复杂模型，只做透明、可追溯的处理：

1. 每个期限内按 strike 排序。
2. 剔除异常尖刺。
3. 比较同 strike 的 call/put IV。
4. 用线性插值补中间缺口。
5. 保留 `raw_iv` 和 `smooth_iv` 两列。
6. 插值结果必须标记 `interpolated`。

暂不做：

- SVI
- SABR
- SSVI
- 无标签外推
- 跨到期日补值

## 质量标签

盘口和 IV 的质量标签比强行补全更重要。

推荐标签：

| 标签 | 含义 |
| --- | --- |
| `ok` | 质量正常 |
| `wide_spread` | 买卖价差过宽 |
| `last_inside_spread` | 用买卖价之间的最新价 |
| `last_fallback` | 只有最新价 |
| `stale_quote` | 盘口过旧 |
| `no_price` | 无有效价格 |
| `invalid_bid_ask` | 买卖价无效 |
| `crossed_market` | 卖价低于买价 |
| `below_intrinsic` | 价格低于理论边界 |
| `solve_failed` | IV 求解失败 |
| `outlier` | 异常点 |
| `interpolated` | 插值得到 |
| `low_liquidity` | 低成交/低持仓 |
| `surface_excluded` | 因流动性或报价质量不足，被 IV 曲面剔除 |

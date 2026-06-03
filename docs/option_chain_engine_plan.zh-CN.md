# 期权链引擎计划

本文档是期权链引擎（系统 2）的简体中文版计划与进度记录。它用于统一设计边界、数据口径、质量标准、候选结构规则和后续开发顺序。

更新原则：当系统范围、状态、质量口径、数据结构或下一步计划变化时，同步更新本文档。

## 最近更新

- 2026-06-02：已将系统 2 agent 规则同步到本计划，明确研究级期权链范围、富集快照作为标准输出、统一 `time_to_expiry` 硬规则，并扩展验证清单。
- 2026-06-03：已完成 MO 第一试生产月的富集快照、Black-76 IV/Greeks、bucket mapping、strategy candidates、质量诊断、近到期阶段标签、标准质量口径和候选池分层。

## 当前目标

构建一个“引擎可直接使用”的期权链快照层。下游系统应该直接读取该快照，而不是读取缓慢的原始盘口数据，也不应该重复计算 IV、Greeks、forward 或剩余时间。

该快照设计必须同时考虑：

- 本地 PC 存储容量有限；
- 原始数据读取速度慢；
- 后续会有多个解耦系统读取同一份标准数据；
- 存储结构本身就是引擎合约的一部分，不是临时实现细节。

目标不是普通的 `expiry x strike x call/put` 表，而是 **研究级期权链（Research-Grade Option Chain）**。最终链数据必须包括：

```text
Quote Chain
Contract Chain
Mark Price
IV Chain
Greeks Chain
Surface Coordinates
Liquidity and Tradability Labels
Bucket Mapping
Strategy Leg Candidates
Chain Quality Report
```

标准数据流：

```text
raw market data
  -> four-term snapshot production
  -> enriched option-chain snapshot
  -> fast reader / quality gate / strategy / backtest / risk
```

标准存储原则：

```text
one canonical enriched snapshot
one stable schema
one reader API
many downstream read-only systems
```

下游系统不得：

- 读取原始市场数据；
- 重建期权链；
- 重新计算 IV / Greeks / forward / time-to-expiry；
- 私自使用不同的剩余时间口径。

## 已完成内容

### 架构与计划

- 系统蓝图 PDF 已保存到 `docs/blueprints/`。
- 期权链引擎蓝图 PDF 已保存到 `docs/blueprints/Option_Chain_Engine_Blueprint.pdf`。
- 本文件记录期权链引擎计划、当前状态和进度。
- 定价逻辑放在 `option_platform/pricing/`。
- 期权链富集、读取、质量、候选结构逻辑放在 `option_platform/option_chain/`。

### 核心模型

已实现跨系统稳定模型：

```text
option_platform/core/models.py
```

关键对象：

- `UnderlyingQuote`
- `OptionContractRef`
- `OptionQuote`
- `OptionGreeks`
- `OptionChainRow`

### 期权链引擎

已实现：

```text
option_platform/option_chain/builder.py
option_platform/option_chain/chain.py
option_platform/option_chain/adapters/snapshot.py
```

当前能力：

- 按到期日和行权价分组；
- 配对 call/put；
- 选择 ATM；
- 按 DTE、delta、volume、OI、spread、moneyness 过滤；
- 从 snapshot dataframe 构建期权链对象。

### 定价引擎

已实现：

```text
option_platform/pricing/black76.py
option_platform/pricing/implied_vol.py
```

当前模型：

- Black-76 理论价格；
- 二分法反解隐含波动率；
- delta、gamma、theta、vega、rho；
- 明确的质量标签，例如 `ok`、`no_price`、`below_intrinsic`、`zero_time`、`outlier`。

## 剩余时间硬规则

统一 `t_years` 规则：

```text
1 trading day = 240 minutes
1 trading year = 252 trading days
t_years = remaining_trading_minutes / (252 * 240)
```

富集管线使用：

```text
option_platform.data.time_to_expiry.calculate_t_years_by_trading_minutes
```

所有下游系统必须读取 enriched snapshot 中保存好的 `t_years`，不得重新计算。

这是硬性要求。IV、Greeks、波动率曲面、策略、回测、风控必须使用同一份研究级快照中的剩余时间字段。

必须保存的时间字段：

- `expiry_date`
- `expiry_datetime`
- `calculation_timestamp`
- `remaining_trading_minutes`
- `trading_days_to_expiry`
- `calendar_days_to_expiry`
- `time_to_expiry`
- `t_years`
- `expiry_phase`
- `expiry_phase_rank`
- `expiry_phase_reason`
- `time_to_expiry_convention`

要求的 convention 值：

```text
trading_minutes_remaining_240m_252d
```

分钟递减检查：

```text
T(09:30) - T(09:31) = 1 / (252 * 240)
```

### 到期阶段标签

到期阶段不是坏数据标签，而是统计分层标签。尤其最后三个交易日，theta 和 gamma 完全占主导，delta、bucket、IV/Greeks 的误差自然会被放大，因此必须单独统计。

标签规则：

```text
normal:
  remaining_trading_minutes > 720

last_3_trading_days:
  240 < remaining_trading_minutes <= 720

final_trading_day:
  remaining_trading_minutes <= 240
```

这些标签保存在 enriched option-chain row 上，并传递到策略候选字段 `candidate_expiry_phase`。

## 富集快照生产

已实现：

```text
option_platform/option_chain/enrichment.py
scripts/enrich_four_term_snapshots.py
```

富集快照增加字段：

- `forward`
- `resolved_forward`
- `forward_source`
- `forward_quality`
- `forward_consistency_quality`
- `forward_basis_bps`
- `t_years`
- `remaining_trading_minutes`
- `trading_days_to_expiry`
- `expiry_phase`
- `iv`
- `delta`
- `gamma`
- `theta`
- `vega`
- `rho`
- `theoretical_price`
- `iv_method`
- `iv_quality`
- `greeks_quality`
- `pricing_model`
- `pricing_error`
- `moneyness`
- `log_moneyness`
- `atm_distance`
- `contract_multiplier`
- `mark_quality`
- `pricing_quality`
- `tradability_quality`
- `bucket_ids`
- `bucket_primary`
- `delta_bucket`
- `bucket_quality`
- `is_atm_straddle_candidate`
- `straddle_candidate_id`

后续仍需继续补强的蓝图字段：

- `iv_solver_status`
- `greeks_model`
- `forward_moneyness`
- `moneyness_bucket`
- `tenor_days`
- `tenor_years`
- `liquidity_bucket`
- `is_tradable`
- `is_valid_for_strategy`
- `schema_version`
- `model_version`
- `calculation_timestamp`

## Fast Reader

已实现：

```text
option_platform/option_chain/reader.py
```

reader 直接读取 enriched snapshot 和 strategy sidecar，可返回：

- filtered dataframe；
- `OptionChain`；
- quality report；
- bucket rows；
- strategy candidates；
- strategy quality sidecar；
- primary / research 候选池。

reader 不重新计算 IV 或 Greeks。

已新增策略候选池读取接口：

```text
OptionChainSnapshotReader.get_strategy_candidates_by_pool(...)
OptionChainSnapshotReader.get_primary_strategy_candidates(...)
OptionChainSnapshotReader.get_research_strategy_candidates(...)
OptionChainSnapshotReader.load_strategy_candidates_filtered(...)
```

`load_strategy_candidates_filtered(...)` 支持：

- `start` / `end` 日期范围；
- 指定 `trade_dates`；
- `candidate_pool`；
- `structure_type`；
- `term_role`；
- `candidate_quality`；
- `candidate_expiry_phase`；
- 指定轻量 `columns`，减少 IO。

## 质量门控

已实现：

```text
option_platform/option_chain/quality.py
scripts/check_option_chain_quality.py
```

质量报告包括：

- IV 成功率；
- no price 比例；
- valid quote 比例；
- call/put 配对覆盖；
- ATM 覆盖；
- median spread bps；
- 按到期日统计 forward 质量；
- 重点关注近月和次月质量；
- 面向 research、surface、backtest、strategy scan、execution 的可用性标签。

当前交易主宇宙是当月和次月，因此质量逻辑重点关注 front expiries。

## Forward 规则

MO 当前采用股指期货 IM 作为主要 forward 输入：

```text
MO option expiry -> matching IM futures contract -> timestamp-aligned futures price
```

优先级：

1. 高质量 IM futures forward；
2. 高质量 put-call parity synthetic forward；
3. degraded futures / synthetic forward 只作为诊断或降级输入。

必须保留 parity forward 作为诊断字段，用于持续比较：

- `synthetic_forward`
- `parity_forward`
- `parity_forward_pairs`
- `parity_forward_iqr`
- `forward_basis_error`
- `forward_basis_bps`
- `forward_consistency_quality`

系统应持续比较 futures forward 与 synthetic forward 的差距。差距过大时，不能静默使用，需要质量标签。

## 合约乘数要求

状态：MO 稳定乘数已实现；ETF 分红调整表仍待接入。

这是硬性 schema 要求，尤其针对 ETF 期权。

ETF 期权在现金分红、拆分或其他公司行为后，合约乘数和交割内容可能发生调整。因此期权链快照必须在每个合约行保存乘数。

要求：

```text
all Greeks and risk quantities are per one contract row
downstream notional/risk aggregation must use saved contract_multiplier
downstream systems must not infer multiplier from product defaults
```

必需字段：

- `contract_multiplier`
- `standard_contract_multiplier`
- `adjusted_contract_multiplier`
- `multiplier_source`
- `multiplier_effective_date`
- `contract_adjustment_flag`
- `contract_adjustment_reason`
- `deliverable_description`

MO 当前试验结果：

```text
contract_multiplier: 100 for all rows
standard_contract_multiplier: 100 for all rows
adjusted_contract_multiplier: null
multiplier_source: contract_master
contract_adjustment_flag: false
```

## 第一试生产月

已生成 MO 富集期权链快照：

```text
Product: MO
Range: 2022-07-22 to 2022-08-19
Trading days: 21
Output: data_store/snapshots/four_term_enriched_month_trial/MO/
```

每日行数：

```text
rows = 47,432
```

主要输出：

```text
{trade_date}.parquet
{trade_date}.quality.parquet
{trade_date}.strategy_candidates.parquet
{trade_date}.strategy_quality.parquet
{trade_date}.meta.json
```

异常日报：

```text
artifacts/option_chain/mo_exception_report_2022-07-22_2022-08-19.md
artifacts/option_chain/mo_exception_report_2022-07-22_2022-08-19.csv
```

## Black-76 IV 与 Greeks 质量

当前定价模型：

```text
Black-76
```

核心字段：

- `iv`
- `delta`
- `gamma`
- `theta`
- `vega`
- `rho`
- `iv_quality`
- `greeks_quality`
- `pricing_error`

质量标签：

```text
iv_quality:
  ok
  no_price
  below_intrinsic
  zero_time
  no_forward
  outlier

greeks_quality:
  ok
  no_iv
  iv_{iv_quality}
  near_expiry_unstable
  deep_itm_unstable
  deep_otm_unstable
```

注意：近到期阶段不是简单坏数据，而是单独统计。最后三个交易日的 gamma/theta 效应会显著放大误差。

## Bucket Mapping

状态：已实现 ATM、25D、50D 和 ATM straddle 候选。

核心字段：

- `bucket_ids`
- `bucket_primary`
- `bucket_count`
- `delta_bucket`
- `bucket_selection_rank`
- `bucket_selection_reason`
- `bucket_target_delta`
- `bucket_delta_error`
- `bucket_quality`
- `bucket_quality_reason`
- `is_atm_straddle_candidate`
- `straddle_candidate_id`

标准 bucket：

```text
25D_call
25D_put
50D_call
50D_put
ATM_call
ATM_put
ATM_straddle
```

ATM straddle 规则：

```text
同一 timestamp
同一 expiry
call/put 必须同一 strike
strike 选择 resolved_forward 最近的 common strike
```

重要结论：ATM 和 50D 不必须是同一个行权价。实际交易中 ATM straddle 更应按同一行权价的 call/put 建立，而不是强行绑定独立选择出来的 50D call/put。

bucket quality：

```text
ok:    bucket_delta_error <= 0.05
loose: bucket_delta_error <= 0.10
bad:   bucket_delta_error > 0.10
```

诊断图：

```text
scripts/render_bucket_diagnostics_svg.py
artifacts/option_chain/mo_bucket_diagnostics_2022-08-10_1000.svg
```

2022-08-10 10:00 样例显示：

- 当月 ATM straddle 使用 K7200；
- 次月 ATM straddle 使用 K7100；
- 次月 50D 使用 K7200；
- 因此 ATM 与 50D 可以自然不同。

## Strategy Candidates

状态：已实现结构候选、结构级质量、到期阶段口径和候选池分层。

已实现结构：

```text
atm_straddle:
  long ATM call + long ATM put, same straddle_candidate_id

25d_strangle:
  long 25D call + long 25D put, same term role

25d_risk_reversal:
  long 25D call - short 25D put, same term role

atm_call_calendar:
  long next-month ATM call - short current-month ATM call

atm_put_calendar:
  long next-month ATM put - short current-month ATM put
```

候选结构字段：

- `candidate_id`
- `product`
- `trade_date`
- `timestamp`
- `structure_type`
- `term_role`
- `expiry_date`
- `leg_count`
- `net_mark`
- `net_delta`
- `net_gamma`
- `net_theta`
- `net_vega`
- `net_rho`
- `candidate_quality`
- `candidate_reason`
- `candidate_expiry_phase`
- `candidate_expiry_phase_rank`
- `candidate_pool`
- `candidate_pool_reason`
- `legs_json`

## 候选结构质量规则

基础规则：

```text
ok:
  所有腿 strategy_candidate_ok
  IV ok
  Greeks ok
  forward consistency ok
  bucket quality ok
  结构级诊断在 ok 阈值内

conditional:
  至少一条腿 conditional
  或 bucket loose
  或结构级 net delta 超过 ok 阈值但没有超过 reject 阈值

rejected:
  缺失策略资格
  IV/Greeks 失败
  forward warning/severe/no forward
  bucket bad
  结构级 net delta 超过 reject 阈值
```

结构级净 delta 规则：

```text
atm_straddle:
  ok if abs(net_delta) <= 0.10
  conditional if abs(net_delta) <= 0.20
  rejected if abs(net_delta) > 0.20

25d_strangle:
  ok if abs(net_delta) <= 0.15
  conditional if abs(net_delta) <= 0.30
  rejected if abs(net_delta) > 0.30

atm_call_calendar / atm_put_calendar:
  ok if abs(net_delta) <= 0.15
  conditional if abs(net_delta) <= 0.30
  rejected if abs(net_delta) > 0.30

25d_risk_reversal:
  方向性结构，不使用净 delta 中性 reject 规则
```

## 标准质量口径

当前 `strategy_quality.parquet` 输出三套标准口径：

```text
all_phase:
  所有 strategy candidates

normal_phase:
  candidate_expiry_phase == normal

near_expiry_phase:
  last_3_trading_days + final_trading_day
```

默认生产异常检查应该使用 `normal_phase`。`all_phase` 保留全貌，`near_expiry_phase` 用于单独观察 gamma/theta 主导阶段。

第一试生产月结果：

```text
quality_scope       candidates  ok_ratio  rejected_ratio
all_phase           48683       66.54%    4.00%
normal_phase        45221       69.94%    0.60%
near_expiry_phase    3462       22.10%   48.38%
```

到期阶段拆分：

```text
candidate_expiry_phase  conditional  ok     rejected
normal                  13322        31628  271
last_3_trading_days       873          609  901
final_trading_day         149          156  774
```

解释：normal 阶段 rejected 很少，绝大多数 rejected 来自最后三日和最后一日。因此不能把近到期行为当作普通模型质量失败。

## 候选池分层

已实现三个候选池：

```text
primary_pool:
  candidate_quality == ok
  candidate_expiry_phase == normal
  term_role in current_month, next_month, current_next_month

research_pool:
  candidate_quality == conditional
  或 near-expiry phase
  或非 front term

excluded_pool:
  candidate_quality == rejected
```

第一试生产月候选池分布：

```text
candidate_pool   candidates
primary_pool     31628
research_pool    15109
excluded_pool     1946
```

候选池原因：

```text
normal_front_term_quality_ok        31628
candidate_quality_conditional        4503
term_role_current_quarter            4476
term_role_next_quarter               4343
candidate_quality_rejected           1946
expiry_phase_last_3_trading_days     1482
expiry_phase_final_trading_day        305
```

2022-08-10 reader 抽查：

```text
primary_pool: 1673
research_pool: 703
```

全月 reader API 抽查：

```text
primary_pool + atm_straddle: 7974
primary_pool + current_month + 25d_strangle/risk_reversal: 7543
```

## 异常日报

脚本：

```text
scripts/report_option_chain_exceptions.py
```

输出：

```text
artifacts/option_chain/mo_exception_report_2022-07-22_2022-08-19.md
artifacts/option_chain/mo_exception_report_2022-07-22_2022-08-19.csv
```

默认异常日判定：

```text
quality_scope = normal_phase
ok_ratio < 60%
or rejected_ratio > 2%
```

报告包含：

- Standard Quality Scopes；
- Exception Days (Normal Phase)；
- Top Reasons By Scope；
- Structure Quality By Scope；
- Expiry Phase Quality；
- Candidate Pool Quality。

## 轻量刷新脚本

脚本：

```text
scripts/refresh_expiry_phase_labels.py
```

用途：

- 从已有 enriched snapshot 刷新 `remaining_trading_minutes`；
- 刷新 `trading_days_to_expiry`；
- 刷新 `expiry_phase`；
- 重建 strategy candidates；
- 重建 strategy quality sidecar；
- 不重新计算 forward；
- 不重新反解 IV；
- 不重新计算 Greeks。

这样修改标签规则时不需要完整跑一遍 Black-76 定价。

## 存储与读取性能

策略和回测系统应优先读取：

```text
{trade_date}.strategy_candidates.parquet
{trade_date}.strategy_quality.parquet
```

只有在需要调试候选规则或生成新规则时，才直接读取 enriched snapshot。

已观测 benchmark：

```text
single timestamp bucket rows from enriched:       ~11 ms
single day candidates sidecar selected columns:   <1 ms
single day quality sidecar selected columns:      <1 ms
month candidates sidecars selected columns:       ~13 ms
month quality sidecars selected columns:          ~9 ms
```

结论：高频扫描和多系统读取应使用 sidecar，而不是每次从 enriched snapshot 动态生成候选结构。

## 已通过测试

当前相关测试：

```text
tests/test_black76_pricing.py
tests/test_option_chain_engine.py
tests/test_option_chain_enrichment.py
tests/test_option_chain_quality.py
tests/test_option_chain_snapshot_adapter.py
tests/test_time_to_expiry.py
tests/test_option_chain_strategy_candidates.py
```

最近结果：

```text
34 passed
```

## 当前已知问题

1. enriched snapshot 比原始 four-term snapshot 大，需要长期优化存储。
2. 远月 / 季月在早期 MO 上市阶段流动性弱，很多 no_mark_price 来自缺少连续双边报价。
3. 最后三个交易日自然受到 gamma/theta 主导，不能与普通交易日混合评价。
4. 当前候选池规则偏保守，适合先保护回测与策略扫描质量。
5. ETF 期权分红后的合约乘数调整表仍待接入。
6. 保证金字段尚未实现，应由后续保证金/风险模块计算并回写或侧表保存。
7. 波动率曲面系统保持独立，不合并进期权链引擎；期权链只提供高质量 IV/Greeks 和坐标输入。

## 下一步计划

### 1. Primary Pool 质量门槛细化

目标：让 `primary_pool` 更接近真实可交易候选池。

建议补充：

- bid/ask spread 阈值；
- mark price 来源要求；
- 最小 bid/ask volume；
- open interest / volume 辅助筛选；
- 结构级最小净权利金或最大异常净权利金；
- 各结构独立门槛。

### 2. Strategy Candidate API 完善

状态：已完成第一版。

目标：让后续策略和回测系统直接调用，不重复过滤。

已新增：

- 按结构读取 primary candidates；
- 按日期范围读取候选池；
- 按 `candidate_pool` + `structure_type` + `term_role` 组合过滤；
- 按 `candidate_quality` 和 `candidate_expiry_phase` 过滤；
- 返回轻量列集，减少 IO。

后续可继续补：

- 更细的 timestamp 区间过滤；
- 多日批量 benchmark；
- 策略专用 view，例如 straddle-only / 25D-only / calendar-only。

### 3. IV/Greeks 诊断继续增强

目标：把 Black-76 解不出来或 Greeks 不稳定的原因拆得更细。

建议补充：

- solver iteration；
- solver bracket 状态；
- intrinsic violation 幅度；
- price tolerance；
- near-expiry 单独阈值；
- IV 时间序列跳变诊断。

### 4. 波动率曲面系统对接

保持独立系统，不并入期权链引擎。

期权链引擎需要为曲面系统提供：

- high-quality IV；
- delta；
- moneyness；
- tenor；
- bucket；
- quality labels；
- front/near-expiry 分层。

### 5. 多产品扩展

当前 MO 流程跑通后，后续扩展：

- ETF options；
- 其他指数期权；
- ETF 分红调整乘数；
- 不同标的 forward 规则；
- 不同交易日历和到期规则。

# Option Chain Engine Plan

Single document for system-2 design and implementation progress. Update this
file when scope, status, or next steps change.

## Last Updated

- 2026-06-02: synced system-2 agent rule (`.cursor/rules/option-chain-agent.mdc`) to this plan (research-grade scope, enriched snapshot as canonical output, hard `time_to_expiry` rule, and expanded verification checklist).

## Current Objective

Build an engine-ready option-chain snapshot layer that downstream systems can
read directly without touching slow raw data or recalculating IV/Greeks.

The snapshot design must optimize for both local PC storage and future
cross-system access. Storage layout is part of the engine contract, not an
implementation detail.

The engine target is a **Research-Grade Option Chain**, not just an
`expiry x strike x call/put` table. The finished chain must include:

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

The canonical direction is:

```text
raw market data
  -> four-term snapshot production
  -> enriched option-chain snapshot
  -> fast reader / quality gate / strategy / backtest / risk
```

Canonical storage rule:

```text
one canonical enriched snapshot
one stable schema
one reader API
many downstream read-only systems
```

Downstream systems must not read raw market data, rebuild option chains, or
recalculate IV/Greeks/forward/time-to-expiry.

## Completed

### Architecture And Plans

- Saved the system blueprint PDF under `docs/blueprints/`.
- Saved the option-chain blueprint PDF under
  `docs/blueprints/Option_Chain_Engine_Blueprint.pdf`.
- Engine-ready snapshot schema documented in this file.
- Pricing logic lives in `option_platform/pricing/` (Black-76, enrichment).
- Consolidated option-chain plan and progress in this file (formerly
  `docs/option_chain_progress.md`).

### Core Models

Implemented stable cross-system models:

```text
option_platform/core/models.py
```

Key objects:

- `UnderlyingQuote`
- `OptionContractRef`
- `OptionQuote`
- `OptionGreeks`
- `OptionChainRow`

### Option Chain Engine

Implemented:

```text
option_platform/option_chain/builder.py
option_platform/option_chain/chain.py
option_platform/option_chain/adapters/snapshot.py
```

Current capabilities:

- group by expiration and strike;
- pair call/put rows;
- select ATM row;
- filter by DTE, delta, volume, OI, spread, and moneyness;
- build chain objects from snapshot dataframes.

### Pricing Engine

Implemented:

```text
option_platform/pricing/black76.py
option_platform/pricing/implied_vol.py
```

Current model:

- Black-76 theoretical price;
- raw implied volatility by bisection;
- delta, gamma, theta, vega, rho;
- explicit quality labels such as `ok`, `no_price`, `below_intrinsic`,
  `zero_time`, and `outlier`.

### Time To Expiry

Unified `t_years` rule:

```text
1 trading day = 240 minutes
1 trading year = 252 trading days
t_years = remaining_trading_minutes / (252 * 240)
```

The enrichment pipeline uses:

```text
option_platform.data.time_to_expiry.calculate_t_years_by_trading_minutes
```

All downstream systems should consume saved `t_years` from enriched snapshots
instead of recalculating time to expiry.

This is a hard requirement. Every IV, Greeks, surface, strategy, backtest, and
risk calculation must use the same saved time-to-expiry fields from the
research-grade snapshot.

Required time fields:

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

Required convention value:

```text
trading_minutes_remaining_240m_252d
```

Minute-decay check:

```text
T(09:30) - T(09:31) = 1 / (252 * 240)
```

No downstream module may independently recalculate T or use calendar-day
approximations for pricing.

Expiry-phase tagging:

```text
normal:
  remaining_trading_minutes > 720

last_3_trading_days:
  240 < remaining_trading_minutes <= 720

final_trading_day:
  remaining_trading_minutes <= 240
```

These tags are stored on enriched option-chain rows and propagated to strategy
candidates as `candidate_expiry_phase`. They are statistical segmentation tags,
not automatic bad-data labels. The final three trading days should be analyzed
separately because theta and gamma dominate and naturally amplify delta, bucket,
and IV/Greeks instability.

### Enriched Snapshot Production

Implemented:

```text
option_platform/option_chain/enrichment.py
scripts/enrich_four_term_snapshots.py
```

The enriched snapshot adds:

- `forward`
- `forward_pairs`
- `forward_iqr`
- `t_years`
- `iv`
- `delta`
- `gamma`
- `theta`
- `vega`
- `rho`
- `theoretical_price`
- `iv_method`
- `iv_quality`
- `pricing_model`
- `pricing_error`
- `moneyness`
- `log_moneyness`
- `atm_distance`

Still to add from the new blueprint:

- `iv_solver_status`
- `greeks_model`
- `forward_moneyness`
- `delta_bucket`
- `moneyness_bucket`
- `tenor_days`
- `tenor_years`
- `liquidity_bucket`
- `is_tradable`
- `is_valid_for_strategy`
- `schema_version`
- `model_version`
- `calculation_timestamp`

### Fast Reader

Implemented:

```text
option_platform/option_chain/reader.py
```

The reader loads enriched snapshots directly and can return:

- filtered dataframe;
- `OptionChain`;
- quality report.

It does not recalculate IV or Greeks.

### Quality Gate

Implemented:

```text
option_platform/option_chain/quality.py
scripts/check_option_chain_quality.py
```

Quality report includes:

- IV success ratio;
- no price ratio;
- valid quote ratio;
- call/put pair coverage;
- ATM coverage;
- median spread bps;
- forward quality by expiry;
- front-expiry focused quality;
- usability flags for research, surface, backtest, strategy scan, and execution.

Current quality logic focuses trading usability on front expiries because the
main trading universe is current month and next month.

## First Month Production

Generated enriched option-chain snapshots for:

```text
Product: MO
Range: 2022-07-22 to 2022-08-19
Trading days: 21
Output: data_store/snapshots/four_term_enriched/MO/
```

Each day:

```text
rows = 47,432
```

Storage:

```text
source four_term total size: 20.35 MB
enriched total size: 78.06 MB
size ratio: 3.84x
```

Quality summary by best intraday timestamp:

```text
A grade: 13 days
B grade: 8 days
C/D grade: 0 days
```

Front-expiry quality:

```text
focus_iv_success_ratio: mostly 74% to 93%
focus_atm_coverage_ratio: 100%
```

Summary files:

```text
data_store/experiments/month_trials/MO_2022-07-22_2022-08-19_enriched_summary.csv
data_store/experiments/month_trials/MO_2022-07-22_2022-08-19_enriched_quality_reports.json
```

### Visual Check

Generated a current-month chain view for:

```text
Date: 2022-08-10
Expiry: 2022-08-19
Times: 09:30, 10:30, 13:28, 14:55
```

Output:

```text
data_store/experiments/mo_2022-08-10_current_month_chain_tables.svg
```

Observation:

- 13:28 ATM call/put IV is very consistent.
- 09:30 has wider opening spread.
- Midday and late-day snapshots look usable for current-month chain inspection.

## Current Tests

Relevant tests pass:

```text
tests/test_black76_pricing.py
tests/test_option_chain_engine.py
tests/test_option_chain_enrichment.py
tests/test_option_chain_quality.py
tests/test_option_chain_snapshot_adapter.py
tests/test_option_chain_runtime.py
```

Latest result:

```text
19 passed
```

## Known Issues

1. Enriched snapshot size is about 3.8x the original snapshot for the first
   month. This is acceptable for the current trial but should be optimized.
2. Forward now supports matching IM futures prices as the primary source.
   Put-call parity remains a fallback and a basis diagnostic.
3. Opening snapshots may have wide spreads, so best-timestamp selection should
   remain quality-aware.
4. Execution usability is currently based on first-level bid/ask and spread
   fields. Real execution checks need deeper liquidity and execution-engine
   logic later.
5. Black-76 IV/Greeks quality depends heavily on forward quality. The local IM
   futures minute data is now usable for the first MO month; parity-implied
   forward must still be retained and diagnosed with `parity_forward_pairs`,
   `parity_forward_iqr`, and `forward_basis_error`.

## Next Plan

### OCE-1: Research Chain Schema

Status: in progress.

Deliverables:

- lock `research_option_chain_snapshot` schema;
- lock `bucket_mapping` schema;
- lock `strategy_leg_candidates` schema;
- lock `chain_quality_report` schema;
- add `schema_version`, `model_version`, and `calculation_timestamp`;
- document IV/Greeks quality labels and selection rules.

Canonical row grain:

```text
product
trade_date
timestamp
expiry_date
strike_price
option_type
symbol
```

One row represents one option contract at one chain timestamp.

Required storage fields:

- identity fields:
  - `schema_version`
  - `model_version`
  - `calculation_timestamp`
  - `product`
  - `trade_date`
  - `timestamp`
  - `symbol`
  - `exchange`
  - `underlying_symbol`
- contract fields:
  - `expiry_date`
  - `expiry_datetime`
  - `strike_price`
  - `option_type`
  - `contract_multiplier`
  - `standard_contract_multiplier`
  - `adjusted_contract_multiplier`
  - `multiplier_source`
  - `multiplier_effective_date`
  - `contract_adjustment_flag`
  - `contract_adjustment_reason`
  - `deliverable_description`
  - `tick_size`
  - `exercise_type`
  - `settlement_type`
- quote and mark fields:
  - `bid_price1`
  - `ask_price1`
  - `bid_volume1`
  - `ask_volume1`
  - `last_price`
  - `mid_price`
  - `micro_price`
  - `mark_price`
  - `price_source`
  - `mark_quality`
  - `spread_bps`
  - `quote_quality`
- pricing fields:
  - `resolved_forward`
  - `forward_source`
  - `forward_quality`
  - `t_years`
  - `time_to_expiry_convention`
  - `iv`
  - `delta`
  - `gamma`
  - `theta`
  - `vega`
  - `rho`
  - `iv_quality`
  - `greeks_quality`
- diagnostics:
  - `futures_forward`
  - `synthetic_forward`
  - `forward_basis_bps`
  - `forward_consistency_quality`
  - `forward_resolver_reason`
  - `is_tradable`
  - `is_valid_for_strategy`

#### Contract Multiplier Requirement

Status: implemented for MO stable multipliers; ETF adjustment table integration
is still pending.

This is a hard schema requirement, especially for ETF options.

ETF option contracts can be adjusted after cash dividend, split, or other
corporate-action events. After adjustment, the contract multiplier and sometimes
the deliverable can differ from the standard contract size. The option chain
snapshot must therefore save the multiplier on every contract row.

Required behavior:

```text
all Greeks and risk quantities are per one contract row
downstream notional/risk aggregation must use saved contract_multiplier
downstream systems must not infer multiplier from product defaults
```

Required fields:

- `contract_multiplier`: multiplier used for risk and notional calculation;
- `standard_contract_multiplier`: default multiplier for the product;
- `adjusted_contract_multiplier`: adjusted multiplier if different;
- `multiplier_source`: contract_master / exchange_notice / vendor / default;
- `multiplier_effective_date`: first date this multiplier is valid;
- `contract_adjustment_flag`: true when contract is adjusted;
- `contract_adjustment_reason`: dividend / split / merger / unknown;
- `deliverable_description`: optional text for adjusted ETF deliverables.

For index options such as MO, the multiplier is normally stable, but it must
still be saved so downstream risk, backtest, and execution code can use one
schema for all products.

Current MO trial result:

```text
contract_multiplier: 100 for all 996072 rows
standard_contract_multiplier: 100 for all 996072 rows
adjusted_contract_multiplier: null for all rows
multiplier_source: contract_master
contract_adjustment_flag: false for all rows
```

### OCE-2: Quote + Contract Assembly

Status: mostly implemented for MO four-term snapshots.

Deliverables:

- raw chain snapshot from quote and contract master data;
- call/put pairing by expiry and strike;
- term role assignment;
- mid, micro, spread, quote quality;
- contract metadata fields:
  - `exchange`
  - `product`
  - `contract_multiplier`
  - `standard_contract_multiplier`
  - `adjusted_contract_multiplier`
  - `multiplier_source`
  - `multiplier_effective_date`
  - `contract_adjustment_flag`
  - `contract_adjustment_reason`
  - `deliverable_description`
  - `tick_size`
  - `exercise_type`
  - `settlement_type`.

### OCE-3: Mark Price + Pricing Inputs

Status: partially implemented.

Deliverables:

- `mark_price`;
- `price_source`;
- `mark_quality`;
- `forward`;
- `forward_source`;
- `forward_quality`;
- `time_to_expiry`;
- `time_to_expiry_convention`;
- `remaining_trading_minutes`;
- `trading_days_to_expiry`;
- `calendar_days_to_expiry`;
- `expiry_datetime`;
- `risk_free_rate`;
- pricing input diagnostics.

#### Mark Quality

Status: implemented.

The enriched snapshot now stores `mark_quality` per option row. It is derived
from `mark_price`, `price_source`, and `quote_quality`.

Current labels:

```text
ok
no_mark_price
wide_spread
stale_quote
invalid_bid_ask
crossed_market
missing
last_inside_spread
degraded_last
degraded
```

First-month trial distribution:

```text
ok                 482976
no_mark_price      418466
wide_spread         80933
stale_quote         11678
invalid_bid_ask      2019
```

Important interpretation:

`no_mark_price` is not the same as `wide_spread`. In the first-month trial,
many far-month `no_mark_price` rows are caused by missing current-minute
bid/ask and missing last price, not by wide bid/ask spreads. Far-month rows
with valid but wide two-sided quotes are classified separately as
`wide_spread`.

First-month far-month no-mark diagnosis:

```text
far-month rows: 559020
far-month no_mark_price: 354616
far-month no_mark_price ratio: 63.44%

quote_quality inside far-month no_mark_price:
missing            353813
invalid_bid_ask       429
stale_quote           374
```

Interpretation for early MO data:

```text
The first MO month is an early-listing sample. Far-month contracts were not yet
continuously quoted at every minute. This weakens instantaneous pricing quality
in the early sample, but it does not prove that far-month MO options are
structurally illiquid in later live markets.
```

Planned mark diagnostics:

- `mark_missing_reason`;
- `tradability_quality`;
- `pricing_quality`;
- `market_phase`;
- `days_since_product_launch`;
- `days_since_contract_listing`.

Status: implemented with provisional labels. `days_since_contract_listing` uses
an estimated listing date until exchange listing-date metadata is wired in.

Planned labels:

```text
mark_missing_reason:
missing_bid_ask
missing_bid
missing_ask
missing_last
stale_one_sided
invalid_bid_ask

tradability_quality:
liquid_tight
liquid_wide
thin_but_quoted
one_sided
not_quoted

pricing_quality:
ok
wide_spread_pricing
stale_pricing
no_mark_price
invalid_quote
```

First-month implemented-label distribution:

```text
pricing_quality:
ok                    482976
no_mark_price         418466
wide_spread_pricing    80933
stale_pricing          11678
invalid_quote           2019

tradability_quality:
liquid_tight                     482976
not_quoted                       417276
liquid_wide                       80933
one_sided                          8397
thin_but_quoted                    6044
historical_interest_not_quoted      446

mark_missing_reason:
missing_bid_ask_last  417352
invalid_bid_ask          648
stale_one_sided          466
```

Far-month implemented-label distribution:

```text
pricing_quality:
no_mark_price         354616
ok                    157325
wide_spread_pricing    44310
stale_pricing           2362
invalid_quote            407

tradability_quality:
not_quoted                       353855
liquid_tight                     157325
liquid_wide                       44310
thin_but_quoted                    1928
one_sided                          1308
historical_interest_not_quoted      294
```

This confirms the intended interpretation: far-month early-sample rows are a
mix of `not_quoted`, `liquid_tight`, and `liquid_wide`. They should not be
treated as one undifferentiated low-quality bucket.

#### Futures-Based Forward

Status: implemented for local IM minute data; forward-consistency trial passed.

Goal:

```text
MO option expiry -> matching IM futures contract -> timestamp-aligned futures price
```

Forward priority:

```text
1. matching index futures price
2. high-quality put-call parity forward
3. no_forward / low_forward_confidence
```

Required enriched snapshot fields:

- `futures_symbol`
- `futures_forward`
- `futures_forward_source_price`
- `synthetic_forward`
- `synthetic_forward_pairs`
- `synthetic_forward_iqr`
- `forward`
- `forward_source`
- `forward_quality`
- `parity_forward`
- `parity_forward_iqr`
- `forward_basis_error`
- `forward_basis_bps`
- `forward_consistency_quality`

Implemented work:

- Load IM futures minute prices from `data_store/futures/IM/minute/{trade_date}.parquet`.
- Align futures price by snapshot `timestamp` and option `expiry_date`.
- Select futures price by `micro_price`, then `mid_price`, then `last_price`.
- Extend the pricing trading-day list to cover each expiry when the available
  source snapshot dates are shorter than the far-month expiry.
- Use futures price as the default Black-76 forward when available.
- Keep parity forward as fallback and quality diagnostic.
- Store `forward_basis_error = parity_forward - futures_price` when both are available.
- Add script controls: `--futures-product`, `--no-futures`, and `--output-kind`.
- Save canonical aliases and diagnostics:
  - `futures_forward`
  - `futures_forward_source_price`
  - `synthetic_forward`
  - `synthetic_forward_pairs`
  - `synthetic_forward_iqr`
  - `synthetic_forward_mad`
  - `synthetic_forward_quality`
  - `resolved_forward`
  - `forward_basis_abs`
  - `forward_basis_bps`
  - `forward_consistency_quality`
  - `forward_resolver_reason`
- Preserve no-forward diagnostics while leaving official IV/Greeks empty.

Remaining work:

- Add quality thresholds for large futures-vs-synthetic basis error.
- Promote first-month futures-based run to the production enriched snapshot path.
- Add daily chain-quality report aggregation for forward source and basis error.
- Add quality checks for large futures-vs-synthetic basis error.

#### Forward Consistency Diagnostics

This is a hard quality requirement. For every `timestamp x expiry_date`, the
engine must compare the tradable futures forward with the option-implied
synthetic forward.

Diagnostic grain:

```text
trade_date
timestamp
expiry_date
term_role
```

Required fields:

- `futures_forward`
- `futures_forward_source_price`
- `futures_symbol`
- `futures_quote_quality`
- `synthetic_forward`
- `synthetic_forward_pairs`
- `synthetic_forward_iqr`
- `synthetic_forward_mad`
- `synthetic_forward_quality`
- `resolved_forward`
- `forward`
- `forward_source`
- `forward_quality`
- `forward_basis_error`
- `forward_basis_abs`
- `forward_basis_bps`
- `forward_consistency_quality`
- `forward_resolver_reason`

Definitions:

```text
synthetic_forward = robust median of K + (C - P) / exp(-rT)
forward_basis_error = synthetic_forward - futures_forward
forward_basis_abs = abs(forward_basis_error)
forward_basis_bps = forward_basis_error / futures_forward * 10000
resolved_forward = final Black-76 forward used by IV/Greeks
```

Synthetic-forward construction rules:

- use only call/put pairs from the same `timestamp`, `expiry_date`, and
  `strike_price`;
- require both option legs to have valid `mark_price`;
- prefer ATM-near strikes and liquid strikes;
- exclude stale, missing, crossed, locked, or very wide-spread option quotes;
- compute per-strike synthetic forwards;
- use robust median as `synthetic_forward`;
- use IQR and MAD as stability diagnostics.

Forward resolver rules:

```text
1. futures quote ok, synthetic degraded
   -> use futures_forward
   -> forward_source = futures

2. futures quote degraded, synthetic ok
   -> use synthetic_forward
   -> forward_source = synthetic_parity

3. futures ok, synthetic ok, basis normal
   -> use futures_forward
   -> forward_source = futures

4. futures ok, synthetic ok, basis large
   -> use futures_forward for IV/Greeks
   -> forward_quality = basis_warning
   -> exclude from strategy candidates until reviewed

5. futures and synthetic both degraded
   -> no_forward
   -> do not calculate official IV/Greeks
```

Initial consistency labels:

```text
forward_consistency_quality:
ok
minor_basis
basis_warning
basis_severe
futures_degraded
synthetic_degraded
both_degraded
no_forward
```

Initial basis thresholds are provisional and must be calibrated from MO data:

```text
ok:             abs(forward_basis_bps) <= 5
minor_basis:    5 < abs(forward_basis_bps) <= 15
basis_warning: 15 < abs(forward_basis_bps) <= 30
basis_severe:  abs(forward_basis_bps) > 30
```

Important boundary:

```text
option mark_price: price used to solve option IV
resolved_forward: forward used as Black-76 F
```

These are two different mark systems and both must be saved in the enriched
snapshot. Downstream systems must consume the saved values and must not
re-resolve forward.

Current local-data check:

```text
data_store/futures/IM/minute/
data_store/futures/IM/meta/contract_calendar.parquet
```

The first-month IM files are usable:

```text
2022-07-22 to 2022-08-19: 21/21 trading days available
4/4 expiries matched each day
242/242 minute timestamps aligned each day
IM quote ok ratio: about 99.6%
```

First futures-forward trial:

```text
date: 2022-08-10
output: data_store/snapshots/four_term_enriched_futures_test/MO/2022-08-10.parquet
rows: 47432
forward_sources: futures 47432
ok_iv: 27619
ok_iv_ratio: 58.23%
```

Parity-vs-futures basis on the trial day:

```text
2022-08-19 median basis -1.39, median abs basis 1.40
2022-09-16 median basis -1.04, median abs basis 1.10
2022-12-16 median basis  1.05, median abs basis 1.86
2023-03-17 median basis  2.52, median abs basis 3.35
```

First forward-consistency trial:

```text
date: 2022-08-10
output: data_store/snapshots/four_term_enriched_consistency_test/MO/2022-08-10.parquet
rows: 47432
ok_iv: 27603
ok_iv_ratio: 58.19%
```

Forward resolver distribution:

```text
forward_source:
futures           47236
synthetic_parity     86
none                110

forward_consistency_quality:
ok                  36978
minor_basis          9310
basis_warning         726
synthetic_degraded    222
futures_degraded       86
both_degraded         110
```

Basis bps by expiry:

```text
2022-08-19 median abs bps 1.95, p95 abs bps  3.88
2022-09-16 median abs bps 1.55, p95 abs bps  4.04
2022-12-16 median abs bps 2.68, p95 abs bps  8.82
2023-03-17 median abs bps 4.92, p95 abs bps 15.80
```

### OCE-4: IV + Greeks

Status: implemented with Black-76; basic `greeks_quality` diagnostics are now
available, and solver-detail diagnostics are still pending.

Deliverables:

- `implied_volatility`;
- `iv_method`;
- `iv_quality`;
- `iv_solver_status`;
- `pricing_model`;
- `delta`;
- `gamma`;
- `vega`;
- `theta`;
- `rho`;
- `greeks_model`;
- `greeks_quality`;
- Black-76 diagnostics:
  - `intrinsic_value`
  - `discounted_intrinsic_value`
  - `extrinsic_value`
  - `pricing_error`
  - `solver_iterations`
  - `vega_at_solution`
  - `failure_reason`.

Quality labels from the blueprint:

```text
iv_quality:
ok
no_mark_price
below_intrinsic
above_upper_bound
solver_failed
wide_spread
stale_quote
low_liquidity
near_expiry_unstable

greeks_quality:
ok
no_iv
invalid_iv
near_expiry_unstable
deep_otm_unstable
deep_itm_unstable
model_failed
```

Current implemented `greeks_quality` labels:

```text
ok
no_iv
iv_{iv_quality}
near_expiry_unstable
deep_otm_unstable
deep_itm_unstable
```

First-month trial distribution:

```text
ok                    565255
no_iv                 430797
near_expiry_unstable      20
```

### OCE-5: Surface Coordinates + Buckets

Status: row-level bucket mapping implemented for ATM, 25D, 50D, and ATM
straddle candidates. Moneyness coordinates are implemented; moneyness bucket
labels remain planned.

Deliverables:

- `moneyness`;
- `log_moneyness`;
- `forward_moneyness`;
- `tenor_days`;
- `tenor_years`;
- `term_role`;
- `delta_bucket`;
- `moneyness_bucket`;
- `bucket_ids`;
- `bucket_primary`;
- `bucket_count`;
- `bucket_selection_rank`;
- `bucket_selection_reason`;
- `bucket_target_delta`;
- `bucket_delta_error`;
- `bucket_quality`;
- `bucket_quality_reason`;
- `is_atm_straddle_candidate`;
- `straddle_candidate_id`.

Standard bucket examples:

```text
current_month_ATM_call
current_month_ATM_put
current_month_25D_put
next_month_25D_call
current_month_ATM_straddle
```

Selection rules:

- Eligible rows must have `strategy_candidate_ok = true`, `greeks_quality =
  ok`, and non-null `delta`;
- 50D call/put: choose the eligible call/put closest to delta +/-0.50;
- 25D call/put: choose the eligible call/put closest to delta +/-0.25;
- ATM call/put: first choose the common call/put strike closest to the resolved
  forward, then take the call and put at that same strike;
- ATM straddle: mark both ATM legs only after selecting the same timestamp,
  expiry, and strike by the forward-nearest common strike rule;
- `bucket_ids` can contain multiple semicolon-separated labels when one row is
  both 50D and ATM. `bucket_primary` stores the first assigned label for simple
  downstream filters. ATM and 50D are not required to be the same strike.

Single-day implementation check, MO 2022-08-10:

```text
rows                         47432
bucket_candidate_rows         3803
atm_straddle_candidate_rows   1600
atm_straddle_candidate_count   800

delta_bucket rows:
50D_put   953
50D_call  951
25D_put   950
25D_call  949
```

Expiry-level ATM straddle candidate counts:

```text
2022-08-19    235
2022-09-16    226
2022-12-16    236
2023-03-17    103
```

Interpretation: front-month and next-month bucket coverage is stable. Far-quarter
coverage is lower on this early MO sample because some contracts were newly
listed and did not have enough current-minute two-sided tradable marks.

#### Bucket Fast Recompute

Status: implemented.

Bucket mapping is now separated from IV/Greeks enrichment:

```text
existing enriched snapshot
  -> recompute_bucket_mapping
  -> same enriched snapshot with refreshed bucket fields
  -> refreshed quality/meta sidecars
  -> refreshed strategy quality sidecar
```

Implemented entry points:

```text
option_platform.option_chain.enrichment.recompute_bucket_mapping(...)
scripts/recompute_bucket_mapping.py
```

The fast recompute step changes only:

- `bucket_ids`;
- `bucket_primary`;
- `bucket_count`;
- `delta_bucket`;
- `bucket_selection_rank`;
- `bucket_selection_reason`;
- `bucket_target_delta`;
- `bucket_delta_error`;
- `bucket_quality`;
- `bucket_quality_reason`;
- `is_atm_straddle_candidate`;
- `straddle_candidate_id`.

It must not recalculate or change:

- `mark_price`;
- `forward` / `resolved_forward`;
- `time_to_expiry` / `t_years`;
- `iv`;
- Greeks.

Validation:

```text
MO 2022-08-10 fast recompute:
rows: 47432
bucket_rows: 4216
atm_straddles: 951
non-bucket pricing fields unchanged: true
```

First-month fast recompute:

```text
date range: 2022-07-22 to 2022-08-19
trading days: 21
rows: 996072
elapsed: about 58 seconds
bucket_candidate_rows: 84550
atm_straddle_count: 18783
front_two_straddle_count: 9960
```

Important implementation note:

`value_counts` sidecar writers must aggregate all null-like keys into one
`null` bucket. Pandas can produce both `<NA>` and `NaN` keys after mixed
Parquet/string operations.

#### Bucket Quality Diagnostics

Status: implemented.

Bucket rows now include primary-bucket delta diagnostics:

```text
bucket_target_delta
bucket_delta_error = abs(delta - bucket_target_delta)
bucket_quality
bucket_quality_reason
```

Initial thresholds:

```text
ok:    bucket_delta_error <= 0.05
loose: bucket_delta_error <= 0.10
bad:   bucket_delta_error > 0.10
```

Important interpretation:

`bucket_quality` describes the row's `bucket_primary`. A row can also carry
additional labels in `bucket_ids`; for example, a row can be primary 25D and
also be part of the forward-nearest ATM straddle. Strategy `legs_json` includes
the bucket target, error, quality, and quality reason for each leg.

First-month bucket-quality summary:

```text
bucket rows: 84550
ok:          74246
loose:        8963
bad:          1341
```

By delta bucket:

```text
bucket      rows   ok_ratio  median_error  p95_error
25D_call   18517  97.74%    0.0146        0.0393
25D_put    18436  89.67%    0.0192        0.0822
50D_call   18849  92.28%    0.0196        0.0634
50D_put    18849  92.39%    0.0200        0.0628
ATM_call    4121  49.16%    0.0502        0.0642
ATM_put     5778  48.15%    0.0506        0.0716
```

Interpretation:

25D call quality is very stable; 25D put is still generally usable but has more
loose selections in the first MO month. ATM bucket delta error is expected to be
wider because ATM is selected by forward-nearest common strike, not by 50D.

First-month implementation check, MO 2022-07-22 to 2022-08-19:

```text
trading_days                  21
rows                      996072
iv_ok                     565275
iv_ok_ratio                56.75%
front_two_iv_ok_ratio      82.65%
bucket_candidate_rows      84550
atm_straddle_rows          37566
atm_straddle_count         18783
front_two_bucket_rows      41995
front_two_straddle_count    9960
```

Term-level bucket and IV summary:

```text
term_rank  rows    iv_ok_ratio  bucket_rows  straddle_count
1          203280  86.07%       20121        4971
2          233772  79.68%       21874        4989
3          274428  37.20%       21438        4476
4          284592  35.83%       21117        4347
```

Monthly `delta_bucket` rows:

```text
50D_call  18849
50D_put   18849
25D_call  18517
25D_put   18436
```

### OCE-6: Strategy-Ready Chain

Status: row-level candidate tagging, minimum strategy structure generation,
bucket rule diagnostics, structure-level quality rules, and exception reporting
are implemented.

Deliverables:

- `strategy_leg_candidates`;
- `select_bucket`;
- `build_strategy_candidates`;
- row-level fields:
  - `strategy_candidate_ok`;
  - `strategy_candidate_tier`;
  - `strategy_candidate_reason`;
- candidate structures:
  - ATM straddle;
  - 25D strangle;
  - 25D risk reversal;
  - ATM call/put calendar;
  - butterfly;
- strategy candidate fields:
  - `candidate_id`;
  - `product`;
  - `trade_date`;
  - `timestamp`;
  - `structure_type`;
  - `term_role`;
  - `expiry_date`;
  - `leg_count`;
  - `net_mark`;
  - `net_delta`;
  - `net_gamma`;
  - `net_theta`;
  - `net_vega`;
  - `net_rho`;
  - `candidate_quality`;
  - `candidate_reason`;
  - `legs`.

Important boundary: this module produces candidate legs, not trading signals,
position sizing, or orders.

Implemented API:

```text
OptionChainSnapshotReader.get_bucket_rows(...)
OptionChainSnapshotReader.get_strategy_candidates(...)
OptionChainSnapshotReader.get_strategy_candidates_for_day(...)
OptionChainSnapshotReader.get_strategy_candidate_quality_report(...)
OptionChainSnapshotReader.get_strategy_candidates_for_storage(...)
OptionChainSnapshotReader.load_strategy_candidates_sidecar(...)
OptionChainSnapshotReader.load_strategy_quality_sidecar(...)
build_strategy_candidates(...)
build_strategy_candidate_quality_report(...)
prepare_strategy_candidates_for_storage(...)
scripts/render_bucket_diagnostics_svg.py
scripts/report_option_chain_exceptions.py
```

Reader behavior:

- reads the canonical enriched snapshot by column projection;
- returns only rows with non-null `bucket_ids` for bucket queries;
- matches `bucket_id` against the semicolon-separated `bucket_ids`, not only
  `bucket_primary`;
- supports `term_role`, `delta_bucket`, and `front_terms_only` filters.

Implemented structures:

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

Candidate quality:

```text
ok:
  all legs strategy_candidate_ok, IV ok, Greeks ok, forward consistency ok,
  bucket quality ok, and structure-level diagnostics inside ok thresholds

conditional:
  at least one leg is conditional, at least one selected bucket is loose, or
  structure-level net delta is outside ok threshold but inside reject threshold

rejected:
  missing strategy eligibility, IV/Greeks failure, warning/severe/no forward,
  bad selected bucket, or structure-level net delta outside reject threshold
```

Structure-level quality rules:

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
  directional structure; no net-delta neutrality reject rule
```

Bucket rule diagnostic graph:

```text
scripts/render_bucket_diagnostics_svg.py
output: artifacts/option_chain/mo_bucket_diagnostics_2022-08-10_1000.svg
```

The diagnostic graph is read from the enriched option-chain snapshot. It marks
current-month and next-month 25D, 50D, and ATM selections, displays target delta,
actual delta, delta error, and bucket quality, and links the same-strike ATM
call/put pair. The 2022-08-10 10:00 sample confirms that ATM and 50D can
legitimately be different strikes: next-month ATM straddle uses K7100 while
next-month 50D uses K7200.

Single timestamp check, MO 2022-08-10 10:00:

```text
front bucket rows: 8
strategy candidates: 10

atm_straddle:          current_month, next_month, current_quarter, next_quarter
25d_strangle:          current_month, next_month
25d_risk_reversal:     current_month, next_month
atm_call_calendar:     current_month vs next_month
atm_put_calendar:      current_month vs next_month
```

Single timestamp quality result before structure-level rules:

```text
front-month and next-month candidates: ok
quarter candidates: conditional
```

Daily strategy-quality sidecar:

```text
scripts/report_strategy_candidates.py
output: {trade_date}.strategy_candidates.parquet
output: {trade_date}.strategy_quality.parquet
```

The candidate sidecar stores one row per candidate structure:

- scalar fields for fast filters:
  - `candidate_id`;
  - `timestamp`;
  - `structure_type`;
  - `term_role`;
  - `candidate_quality`;
  - `candidate_pool`;
  - `candidate_pool_reason`;
  - `candidate_expiry_phase`;
  - `net_mark`;
  - `net_delta`;
  - `net_gamma`;
  - `net_theta`;
  - `net_vega`;
  - `net_rho`;
- `legs_json` for leg-level details.

The quality report summarizes:

- candidate count;
- timestamp coverage;
- ok / conditional / rejected counts;
- ok / conditional / rejected ratios;
- median net mark;
- median absolute net delta;
- median net vega;
- p95 absolute net delta;
- overall, by structure, and by structure + term role.
- expiry-phase quality split for normal vs final three trading days.
- standardized quality scopes:
  - `all_phase`: all strategy candidates;
  - `normal_phase`: only `candidate_expiry_phase == normal`;
  - `near_expiry_phase`: `last_3_trading_days` plus `final_trading_day`.

Default production exception checks should use `normal_phase`. `all_phase`
keeps the full historical picture, while `near_expiry_phase` is a separate
observation scope for gamma/theta-dominated behavior.

Candidate pool rules:

```text
primary_pool:
  candidate_quality == ok
  candidate_expiry_phase == normal
  term_role in current_month, next_month, current_next_month

research_pool:
  candidate_quality == conditional, or near-expiry phase, or non-front term

excluded_pool:
  candidate_quality == rejected
```

Reader API:

```text
OptionChainSnapshotReader.get_strategy_candidates_by_pool(...)
OptionChainSnapshotReader.get_primary_strategy_candidates(...)
OptionChainSnapshotReader.get_research_strategy_candidates(...)
OptionChainSnapshotReader.load_strategy_candidates_filtered(...)
```

First-month strategy-candidate quality check, MO 2022-07-22 to 2022-08-19:

```text
trading_days         21
candidate_count   48683
ok_count          32393
conditional_count 14344
rejected_count     1946
weighted_ok_ratio 66.54%

daily ok ratio:
min    32.23%
median 72.54%
max    82.89%
```

Standard quality scopes:

```text
quality_scope       candidates  ok_ratio  rejected_ratio
all_phase           48683       66.54%    4.00%
normal_phase        45221       69.94%    0.60%
near_expiry_phase    3462       22.10%   48.38%
```

Candidate pool distribution:

```text
candidate_pool   candidates
primary_pool     31628
research_pool    15109
excluded_pool     1946
```

Candidate pool reasons:

```text
normal_front_term_quality_ok        31628
candidate_quality_conditional        4503
term_role_current_quarter            4476
term_role_next_quarter               4343
candidate_quality_rejected           1946
expiry_phase_last_3_trading_days     1482
expiry_phase_final_trading_day        305
```

Reader API check:

```text
2022-08-10 primary_pool: 1673
2022-08-10 research_pool: 703
first-month primary_pool + atm_straddle: 7974
first-month primary_pool + current_month + 25d_strangle/risk_reversal: 7543
```

Top candidate quality reasons after structure-level rules:

```text
all_legs_ok                                                            32393
contains_conditional_leg                                                6550
contains_loose_bucket                                                   3958
contains_loose_bucket;contains_conditional_leg;net_delta_loose>0.10     2092
leg_bucket_bad                                                          1944
contains_loose_bucket;net_delta_loose>0.10                              1266
```

Exception daily report:

```text
scripts/report_option_chain_exceptions.py
output: artifacts/option_chain/mo_exception_report_2022-07-22_2022-08-19.md
output: artifacts/option_chain/mo_exception_report_2022-07-22_2022-08-19.csv
```

The report now flags exception days from `normal_phase` by default. The default
thresholds are `ok_ratio < 60%` or `rejected_ratio > 2%`. Near-expiry rows are
still reported, but they no longer contaminate the default exception-day list.

Expiry-phase quality split:

```text
candidate_expiry_phase  conditional  ok     rejected
normal                  13322        31628  271
last_3_trading_days       873          609  901
final_trading_day         149          156  774
```

Interpretation: normal-phase rejected candidates are low, while final-three-day
and final-day candidates explain most of the rejected structures. Production
quality dashboards should therefore report both all-phase quality and
normal-phase quality, and should not use final-three-day behavior as a generic
model-quality failure signal.

Lightweight expiry-phase refresh:

```text
scripts/refresh_expiry_phase_labels.py
```

This script refreshes `remaining_trading_minutes`, `trading_days_to_expiry`,
`expiry_phase`, strategy candidates, and strategy-quality sidecars from existing
enriched snapshots. It does not recompute forward, IV, or Greeks, so label-rule
changes do not require a full Black-76 repricing run.

Structure-level summary:

```text
structure            candidates  ok_ratio
25d_risk_reversal    10001       88.37%
25d_strangle         10001       88.32%
atm_call_calendar     4949       67.41%
atm_put_calendar      4949       65.39%
atm_straddle         18783       43.39%
```

Term-level interpretation:

```text
current_month ATM straddle ok ratio: 97.24%
next_month ATM straddle ok ratio:    99.18%
current_quarter ATM straddle:        conditional
next_quarter ATM straddle:           conditional
```

The low overall ATM-straddle ok ratio is now mainly driven by bucket looseness
and near-expiry gamma/theta behavior, not by a failure of the same-strike ATM
rule. The forward-nearest common-strike ATM rule increases straddle coverage and
is more consistent with real straddle trading than tying ATM to independently
selected 50D call/put legs. This remains consistent with the desk focus on
current-month and next-month trading.

Strategy sidecar storage:

```text
first-month candidate + quality sidecars: 8.5 MB total
2022-08-10 strategy_candidates: 416 KB
2022-08-10 strategy_quality: 11 KB
```

Reader benchmark, MO 2022-08-10 plus first-month sidecars:

```text
single timestamp bucket rows from enriched:     11.04 ms, rows 10
single day candidates generated from enriched: 1799.94 ms, rows 2385
single day candidates sidecar selected columns:   0.67 ms, rows 2385
single day quality sidecar selected columns:      0.48 ms, rows 16
month candidates sidecars selected columns:      13.22 ms, rows 48683
month quality sidecars selected columns:          9.36 ms, rows 336
```

Conclusion:

```text
strategy and backtest systems should read strategy_candidates / strategy_quality
sidecars for repeated scans. They should use enriched snapshots only when a new
candidate rule is being generated or debugged.
```

Initial row-level rule:

```text
standard:
front-term + pricing_quality ok + tradability liquid_tight + Greeks ok

conditional:
wide-spread tradable rows, or far-term tradable rows, with Greeks ok and
acceptable forward consistency

excluded:
no IV/Greeks, no mark price, stale/invalid pricing, one-sided/not-quoted
tradability, or warning/severe forward basis
```

First-month trial distribution:

```text
strategy_candidate_ok:
true   529297
false  466775

strategy_candidate_tier:
standard     314256
conditional  215041
excluded     466775
```

Reason distribution:

```text
greeks_no_iv                430797
front_term_liquid_tight     314256
far_term_liquid_tight       140592
far_term_liquid_wide         38506
front_term_liquid_wide       35943
forward_basis_warning        21254
pricing_stale_pricing        10151
forward_basis_severe          2854
pricing_invalid_quote         1699
near_expiry_unstable            20
```

By-expiry tier summary:

```text
2022-08-19 standard 138355, conditional 28498, excluded 36427
2022-09-16 standard 175901, conditional  7445, excluded 50426
2022-12-16 standard      0, conditional 90819, excluded 183609
2023-03-17 standard      0, conditional 88279, excluded 196313
```

Interpretation:

```text
front two expiries can feed standard strategy scans;
far-month contracts are not excluded by term alone, but enter only as
conditional candidates until liquidity, spread, and listing-stage thresholds
are calibrated on later market phases.
```

### Storage Efficiency

Storage principle:

```text
save one denormalized enriched snapshot
do not save intermediate chain stores
do not require downstream joins for normal use
use Parquet column pruning for speed and storage efficiency
```

Canonical current path:

```text
data_store/snapshots/four_term_enriched/{PRODUCT}/{trade_date}.parquet
```

Future partitioned path if schema migration becomes necessary:

```text
data_store/option_chain/research_snapshot/v1/product={PRODUCT}/trade_date={trade_date}/part.parquet
```

File format:

```text
Parquet + ZSTD compression
```

Daily file grain:

```text
product + trade_date -> one enriched option-chain snapshot file
```

Optional small sidecar files are allowed and do not count as duplicate chain
stores:

```text
data_store/snapshots/four_term_enriched/{PRODUCT}/{trade_date}.meta.json
data_store/snapshots/four_term_enriched/{PRODUCT}/{trade_date}.quality.parquet
```

Sidecar content:

- `schema_version`;
- `model_version`;
- `pricing_model`;
- `time_to_expiry_convention`;
- `risk_free_rate`;
- row count and file size;
- IV/Greeks quality summary;
- forward source and consistency summary;
- contract multiplier adjustment summary;
- strategy candidate summary;
- production timestamp and input data versions.

Implemented sidecar output:

```text
{trade_date}.meta.json
{trade_date}.quality.parquet
{trade_date}.strategy_candidates.parquet
{trade_date}.strategy_quality.parquet
```

Current script behavior:

- snapshot parquet uses ZSTD compression;
- sidecar generation is enabled by default;
- `--no-sidecars` disables sidecar output;
- pandas all-NA concat warning has been removed by normalizing timestamp
  frames before concatenation.

Storage tasks:

- Test Parquet ZSTD compression options. Current production script writes ZSTD.
- Measure file size with all canonical fields.
- Consider dropping only truly unused columns after validation.
- Keep one canonical enriched snapshot layer and avoid extra chain-store copies.

#### First-Month Trial Production

Trial output:

```text
data_store/snapshots/four_term_enriched_month_trial/MO/
```

Date range:

```text
2022-07-22 to 2022-08-19
21 trading days
```

Storage result:

```text
files: 21
rows: 996072
compression: ZSTD
total size: 71.07 MB
single-day size: min 3.11 MB, median 3.39 MB, max 3.60 MB
quality sidecars: 21 files, 0.38 MB total
meta sidecars: 21 files, 24.12 KB total
```

After adding multiplier / mark-quality / greeks-quality fields:

```text
total size: 71.25 MB
rows: 996072
```

Overall pricing quality:

```text
iv_quality:
ok               565275
no_price         416831
below_intrinsic   11341
no_forward         2552
outlier              73

overall iv ok ratio: 56.75%
```

Front-two-expiry quality:

```text
front two expiry iv ok ratio:
min    73.97%
median 83.51%
max    88.07%

front two no-price ratio median: 16.25%
```

Forward source:

```text
futures           991900
synthetic_parity    1620
none                2552
```

Forward consistency:

```text
ok                  701834
minor_basis         216564
basis_warning        59234
basis_severe          7764
synthetic_degraded    6504
both_degraded         2552
futures_degraded      1620
```

By-expiry summary:

```text
expiry      iv_ok_ratio  median_abs_basis_bps  p95_abs_basis_bps
2022-08-19  86.07%       1.16                  3.75
2022-09-16  79.68%       1.67                  6.10
2022-12-16  37.20%       4.42                  20.32
2023-03-17  35.83%       5.00                  24.55
```

Read benchmark on `2022-08-05.parquet`:

```text
full file, all columns:           median 9.74 ms
full file, selected columns:      median 4.50 ms
single timestamp, selected cols:  median 4.50 ms
front two expiries, selected cols: median 7.63 ms
```

Trial conclusion:

```text
current-month and next-month quality is good enough for the next production
step. In this early MO sample, far-month instantaneous pricing quality is weak
mainly because many contracts were newly listed and lacked continuous
current-minute two-sided quotes. This should be treated as an early-market-phase
effect, not a permanent conclusion that far-month options are unusable.
```

Far-month usage rule:

```text
Far-month options should remain available for research, surface diagnostics,
and conditional strategy review. Strategy inclusion should depend on
pricing_quality, tradability_quality, basis quality, and contract listing age,
not only on a fixed far-month exclusion rule.
```

Sidecar validation:

```text
snapshot files: 21
quality files: 21
meta files: 21
schema_version: research_option_chain_snapshot.v0
model_version: black76_forward_consistency.v0
```

### Reader And Benchmark

All downstream systems must access chain data through
`OptionChainSnapshotReader` or a compatible reader interface. They should not
hard-code paths or perform their own raw-data joins.

Required reader methods:

```text
get_chain(product, trade_date, timestamp)
get_expiry_chain(product, trade_date, timestamp, term_role_or_expiry)
get_front_terms(product, trade_date, timestamp, n=2)
get_columns(product, trade_date, columns, filters=None)
get_quality_report(product, trade_date, timestamp=None)
get_contract_metadata(product, trade_date, symbol)
```

Reader must support column projection so strategy, backtest, IV surface, and
risk systems can load only the fields they need.

- Measure read time for:
  - full day selected columns;
  - single timestamp;
  - current-month only;
  - front two expiries only.
- Add reader benchmark script.
- Refactor research/backtest prototypes to use `OptionChainSnapshotReader`.

### Strategy-Oriented Views

- Add reusable chain table renderer for current month and next month.
- Add filters for delta buckets:
  - 0.10
  - 0.16
  - 0.25
  - 0.30
  - 0.50
- Add spread and liquidity filters suitable for strategy scan.

### Downstream Integration

- Stop downstream systems from reading raw or non-enriched snapshots directly.
- Use saved `iv`, `Greeks`, and `t_years` from enriched snapshots as the
  standard input.
- Prepare IV Surface input from enriched snapshots.
- Add risk-oriented fields for portfolio Greeks aggregation.

## Design Reference

### Positioning

The Option Chain Engine is the contract-state bus of the volatility platform.
It gives IV Surface, Research, Strategy, Backtest, Portfolio Risk, Execution,
and Monitoring systems one consistent view of option contracts and quotes.

It owns chain structure and query semantics. It does not own raw market-data
downloads, pricing models, strategy signals, portfolio risk limits, or order
execution.

### Blueprint Alignment

```text
Market Data System
  -> Data Platform / Normalization
  -> Option Chain Engine
  -> IV Surface Engine
  -> Research / Strategy / Backtest / Risk / Execution
```

Option Chain attaches IV/Greeks to each contract; Pricing and Greeks engines
own the mathematical calculation.

### Responsibilities

Responsible for:

- organizing contracts by underlying, expiration, strike, and option right;
- pairing calls and puts into chain rows;
- attaching normalized quotes, OI, volume, quote quality, IV, and Greeks;
- exposing ATM, ITM/OTM, DTE, moneyness, liquidity, spread, bucket, and
  candidate-leg queries;
- producing chain snapshots for research, backtest, risk, and monitoring.

Not responsible for:

- downloading raw external market data;
- repairing parquet files or batch download state;
- fitting IV surfaces;
- generating strategy signals;
- calculating portfolio risk limits;
- placing or cancelling orders.

### Interfaces

Consumes:

- `UnderlyingQuote`
- `OptionContractRef`
- `OptionQuote`
- `OptionGreeks`

Produces:

- `OptionChain`
- `OptionChainRow`
- filtered row sets for downstream engines
- `research_option_chain_snapshot`
- `bucket_mapping`
- `strategy_leg_candidates`
- `chain_quality_report`

Future service interface:

```python
class OptionChainService:
    def get_chain(self, symbol, timestamp=None): ...
    def get_expirations(self, symbol, timestamp=None): ...
    def get_atm(self, symbol, expiration, timestamp=None): ...
    def filter_contracts(self, symbol, criteria, timestamp=None): ...
    def get_snapshot(self, symbol, timestamp): ...
```

Provider interfaces stay outside the engine:

```python
class ContractSource:
    def load_contracts(self, symbol, as_of): ...

class QuoteSource:
    def load_quotes(self, symbol, timestamp): ...

class GreeksSource:
    def load_greeks(self, symbol, timestamp): ...
```

### Internal Modules

```text
option_chain/
  contract_master.py
  builder.py
  chain.py
  adapters/snapshot.py
  mark_price.py
  pricing_inputs.py
  enrichment.py
  reader.py
  quality.py
  surface_coordinates.py
  liquidity.py
  bucket_mapping.py
  strategy_candidates.py
  validation.py
  engine.py
```

Current names can differ from the blueprint, but these responsibilities must be
covered. `pricing/` remains a separate module, while the research-grade chain
must still persist IV and Greeks fields.

Planned or incomplete:

```text
  contract_registry.py
  quote_book.py
  chain_snapshot.py
  chain_query.py
```

### Long-Term Phases

**Real-time chain:** incremental `QuoteBook`, market-event refresh,
`OptionChainUpdated` events, monitoring metrics.

**Fund-level service:** MO/IO/HO/ETF/commodity options through one API;
historical replay and live semantics; versioned snapshots; quality traceability.

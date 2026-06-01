# Option Chain Engine Plan

Single document for system-2 design and implementation progress. Update this
file when scope, status, or next steps change.

## Current Objective

Build an engine-ready option-chain snapshot layer that downstream systems can
read directly without touching slow raw data or recalculating IV/Greeks.

The canonical direction is:

```text
raw market data
  -> four-term snapshot production
  -> enriched option-chain snapshot
  -> fast reader / quality gate / strategy / backtest / risk
```

## Completed

### Architecture And Plans

- Saved the system blueprint PDF under `docs/blueprints/`.
- Engine-ready snapshot schema documented in this file.
- Pricing logic lives in `option_platform/pricing/` (Black-76, enrichment).
- Consolidated option-chain plan and progress in this file (formerly
  `docs_fix/option_chain_progress.md`).

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
```

Latest result:

```text
14 passed
```

## Known Issues

1. Enriched snapshot size is about 3.8x the original snapshot for the first
   month. This is acceptable for the current trial but should be optimized.
2. Current forward is inferred by put-call parity when `futures_price` is empty.
   Later snapshots should use matching index futures prices as the primary
   forward source.
3. Opening snapshots may have wide spreads, so best-timestamp selection should
   remain quality-aware.
4. Execution usability is currently based on first-level bid/ask and spread
   fields. Real execution checks need deeper liquidity and execution-engine
   logic later.
5. Black-76 IV/Greeks quality depends heavily on forward quality. Until IM
   futures minute data is available, parity-implied forward is only a fallback
   and must be diagnosed with `forward_pairs` and `forward_iqr`.

## Next Plan

### Phase 1: Validate Enriched Snapshot Layer

- Run enrichment for the next available month.
- Compare storage growth month by month.
- Measure read time for:
  - full day selected columns;
  - single timestamp;
  - current-month only;
  - front two expiries only.
- Add reader benchmark script.

### Phase 1.5: Add Futures-Based Forward

Status: waiting for index futures minute data.

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
- `futures_price`
- `forward`
- `forward_source`
- `forward_quality`
- `parity_forward`
- `parity_forward_iqr`
- `forward_basis_error`

Planned work:

- Build MO expiry to IM futures contract mapping.
- Download or load IM futures minute prices.
- Align futures price by `timestamp`.
- Use futures price as the default Black-76 forward.
- Keep parity forward as fallback and quality diagnostic.
- Add quality checks for large futures-vs-parity basis error.

### Phase 2: Improve Storage Efficiency

- Test parquet compression options.
- Consider dropping duplicated or unused columns after validation.
- Keep one canonical enriched snapshot layer and avoid extra chain-store copies.

### Phase 3: Strategy-Oriented Views

- Add chain table renderer for current month and next month.
- Add filters for delta buckets:
  - 0.10
  - 0.16
  - 0.25
  - 0.30
  - 0.50
- Add spread and liquidity filters suitable for strategy scan.

### Phase 4: Downstream Integration

- Refactor research/backtest prototypes to use `OptionChainSnapshotReader`.
- Stop downstream systems from reading raw or non-enriched snapshots directly.
- Use saved `iv`, `Greeks`, and `t_years` from enriched snapshots as the
  standard input.

### Phase 5: Risk And Surface Preparation

- Prepare IV Surface input from enriched snapshots.
- Add front-expiry and full-chain quality gates.
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
- exposing ATM, ITM/OTM, DTE, moneyness, liquidity, and spread queries;
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
  builder.py
  chain.py
  adapters/snapshot.py
  enrichment.py
  reader.py
  quality.py
  runtime.py
```

Planned:

```text
  contract_registry.py
  quote_book.py
  chain_snapshot.py
  chain_query.py
  liquidity.py
```

### Long-Term Phases

**Real-time chain:** incremental `QuoteBook`, market-event refresh,
`OptionChainUpdated` events, monitoring metrics.

**Fund-level service:** MO/IO/HO/ETF/commodity options through one API;
historical replay and live semantics; versioned snapshots; quality traceability.

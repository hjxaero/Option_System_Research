# Option Chain Snapshot Plan v1

## Decision

The platform will keep exactly one engine-ready option-chain snapshot layer.

Raw data can be slow to read because it is used for audit, repair, and rebuilds.
Downstream engines must not read raw data and must not recalculate IV/Greeks on
every request.

The persisted option-chain snapshot must be directly usable by Research,
Strategy, Backtest, Risk, IV Surface, and Monitoring.

```text
Raw tick / minute quotes / contracts
  -> Snapshot Builder + Pricing Enrichment
  -> Engine-ready option-chain snapshot parquet
  -> Fast runtime reader / memory cache
  -> Research / Strategy / Backtest / Risk
```

## Storage Rule

Do not persist a second derived chain store such as:

```text
data_store/engine/option_chain/...
```

Instead, the canonical snapshot itself is enriched and directly usable:

```text
data_store/snapshots/four_term/{product}/{trade_date}.parquet
```

or, during migration:

```text
data_store/snapshots/four_term_enriched/{product}/{trade_date}.parquet
```

After validation, `four_term_enriched` can replace `four_term` as the canonical
snapshot layer.

## Snapshot Meaning

An option-chain snapshot file is one trading day's engine-ready option-chain
data. It contains many timestamps, and each timestamp contains all selected
contracts.

One row means:

```text
one timestamp
one option contract
all market, pricing, Greeks, liquidity, and quality fields needed by engines
```

Downstream engines should be able to read this file and immediately use:

- mark price;
- bid/ask;
- spread;
- forward;
- t_years;
- raw IV;
- raw Greeks;
- quote quality;
- IV quality;
- liquidity metrics;
- term role;
- open interest and volume.

## Required Engine-Ready Columns

Core identity:

```text
timestamp
term_role
underlying_symbol
expiry_date
symbol
option_type
strike_price
volume_multiple
```

Market data:

```text
underlying_price
futures_symbol
futures_price
forward
t_years
mark_price
price_source
last_price
bid_price1
ask_price1
bid_volume1
ask_volume1
mid_price
micro_price
spread
spread_bps
quote_time
quote_age_ms
quote_quality
open_interest
volume
```

Pricing and Greeks:

```text
iv
delta
gamma
theta
vega
rho
theoretical_price
iv_method
iv_quality
pricing_model
pricing_error
```

Risk and quality:

```text
margin
moneyness
log_moneyness
atm_distance
liquidity_tier
chain_quality
```

Some fields can be added gradually, but the principle is fixed: engines should
not need raw source files or repeated model calculations to use a chain.

## Production Flow

Snapshot production should do all expensive work once:

```text
read raw/minute quote data
  -> select four terms
  -> align contracts by timestamp
  -> choose mark price
  -> determine forward
  -> calculate t_years by remaining trading minutes
  -> solve raw IV
  -> calculate raw Greeks
  -> calculate liquidity metrics
  -> calculate chain quality labels
  -> write one enriched snapshot parquet
```

The output is the only data layer engines depend on.

## Time To Expiry Rule

`t_years` is a pricing-critical field and must be calculated once during
snapshot enrichment with a unified trading-minute convention.

System rule:

```text
1 trading day = 240 trading minutes
1 trading year = 252 trading days
t_years = remaining_trading_minutes / (252 * 240)
```

Remaining time must decay by trading minutes during the session:

```text
current trading day:
  remaining minutes = 240 - elapsed trading minutes

future full trading days:
  each contributes 240 minutes

expiry day:
  if it is the current day, only remaining trading minutes count
  if it is a future trading day, it contributes 240 minutes
```

All IV, Greeks, surface, strategy, backtest, and risk calculations must consume
the saved `t_years` field from the enriched snapshot. They should not recalculate
time to expiry independently.

The implementation must use:

```python
option_platform.data.time_to_expiry.calculate_t_years_by_trading_minutes
```

This avoids artificial IV and Greeks jumps caused by calendar-day or whole-day
time decay.

## Runtime Flow

Runtime must be fast and lightweight:

```text
read enriched snapshot columns
  -> filter timestamp / expiry / symbol
  -> build in-memory OptionChain object if needed
  -> return data to engine
```

Runtime must not normally:

- infer forward again;
- solve IV again;
- calculate Greeks again;
- read raw minute quote files;
- write another chain parquet.

## Reader Service

Planned module:

```text
option_platform/option_chain/reader.py
```

Primary interface:

```python
class OptionChainSnapshotReader:
    def load_frame(self, product, trade_date, timestamp=None, columns=None): ...
    def get_chain(self, product, trade_date, timestamp): ...
    def get_quality_report(self, product, trade_date, timestamp): ...
    def iter_snapshots(self, product, trade_date, columns=None): ...
```

The reader only reads enriched snapshots and optionally builds convenient
in-memory objects. It does not own pricing logic.

## Cache Policy

Use an in-memory LRU cache for hot reads.

Cache key:

```text
product
trade_date
timestamp
columns
focus_expiries
```

Cache value:

```text
filtered dataframe and/or OptionChain object
```

The cache exists only to avoid repeated disk reads. It is not a persisted data
layer.

## Capacity Policy

To reduce storage usage:

- store one enriched snapshot layer, not both raw-like snapshot and chain store;
- avoid debug CSV/JSON/SVG except when explicitly requested;
- read selected columns whenever possible;
- optionally compress parquet with zstd/snappy;
- keep raw tick/minute archives only where needed for audit or rebuilds.

## Migration Plan

1. Keep current `four_term` snapshots as source-compatible input.
2. Build an enrichment script that fills:
   - `forward`
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
3. Write to `four_term_enriched` first.
4. Compare file size, speed, quality, and sample charts.
5. If validated, promote enriched snapshots as the only snapshot layer.
6. Refactor runtime scripts to read enriched snapshots directly.

## Acceptance Criteria

The first implementation is complete when:

1. one enriched snapshot file can be produced from an existing daily snapshot;
2. engines can read that file without recalculating IV or Greeks;
3. reading one timestamp is fast enough for strategy/risk use;
4. no extra `engine/option_chain` full copy is created;
5. quality reports can be generated from saved snapshot fields;
6. the old runtime pricing path is used only as a migration/enrichment tool.

# Option System Architecture v0

## Goal

The platform is split into small systems with explicit input and output
contracts. Market data, option-chain construction, pricing, strategy, risk,
backtest, execution, portfolio, and UI/API code must evolve independently.

The data platform remains the source of auditable market data assets. Other
systems consume normalized snapshots and core models; they must not know how
TQ, parquet storage, retries, or batch repair work internally.

## System Boundaries

```text
market_data
  Downloads and persists raw or lightly normalized external data.

normalization
  Converts provider-specific fields into stable core objects and snapshot
  schemas.

option_chain
  Builds queryable chains from normalized contracts, quotes, and Greeks.

pricing
  Calculates theoretical values, IV, and Greeks from core objects.

strategy
  Generates candidate trades from chains, portfolio state, and risk context.

risk
  Calculates exposure, margin, scenario PnL, and limits.

backtest
  Replays historical data, fills orders, and records simulated portfolio state.

execution
  Adapts broker APIs into order, cancel, and fill events.

portfolio
  Owns positions, cash, realized/unrealized PnL, and account state.

api
  Exposes application services to UI, notebooks, scripts, or external clients.
```

## Dependency Rules

Allowed shared dependency:

```text
core
```

Core contains stable dataclasses, enums, and validation helpers. It must stay
free of provider SDKs, storage paths, pandas-specific pipeline logic, strategy
rules, broker APIs, and UI concerns.

Preferred dependency flow:

```text
market_data -> normalization -> option_chain -> strategy
                                     |             |
                                     v             v
                                  pricing        risk
                                     |             |
                                     v             v
                                  backtest <--- portfolio
                                     |
                                     v
                                  execution
```

Hard rules:

- Strategy code does not call data providers or read raw files directly.
- Option-chain code does not download market data.
- Pricing code does not know about storage layout, UI, or broker orders.
- Backtest code does not call live broker adapters.
- Execution code does not run strategy selection logic.
- UI/API code orchestrates services but does not own business calculations.

## Data Contracts

The first stable cross-system objects are:

- `OptionContractRef`
- `UnderlyingQuote`
- `OptionQuote`
- `OptionGreeks`
- `OptionChainRow`
- `OptionChain`

The current `option_platform.data.contracts.SnapshotSchema` remains the
canonical persisted minute snapshot schema. The new `option_platform.core`
objects are the in-process boundary used by engines and services.

## First Build Order

1. Keep the existing data platform focused on download, repair, quality, and
   persisted snapshots.
2. Add `core` models as the stable language shared by all engines.
3. Add `option_chain` as a pure in-memory engine that accepts normalized
   contracts, quotes, and optional Greeks.
4. Add adapters from existing snapshot parquet/dataframes into core models.
5. Build strategy, risk, backtest, and execution against the core interfaces.

## Option Chain MVP

The first option-chain engine supports:

- grouping by expiration and strike;
- pairing call and put quotes on the same row;
- DTE, moneyness, mid price, spread, and spread bps;
- ATM selection per expiration;
- filtering by DTE, option type, delta, volume, open interest, and spread.

It deliberately excludes:

- downloading data;
- calculating IV/Greeks;
- strategy-specific candidate generation;
- storage writes.

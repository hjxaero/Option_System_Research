# Option Chain Engine Plan v0

## Positioning

The Option Chain Engine is the contract-state bus of the volatility platform.
It gives IV Surface, Research, Strategy, Backtest, Portfolio Risk, Execution,
and Monitoring systems one consistent view of option contracts and quotes.

It owns chain structure and query semantics. It does not own raw market-data
downloads, pricing models, strategy signals, portfolio risk limits, or order
execution.

## Blueprint Alignment

The architecture blueprint places Option Chain immediately after the market
data and data platform layers:

```text
Market Data System
  -> Data Platform / Normalization
  -> Option Chain Engine
  -> IV Surface Engine
  -> Research / Strategy / Backtest / Risk / Execution
```

The blueprint lists IV and Greeks under Option Chain output. In the decoupled
architecture, Option Chain attaches IV/Greeks to each contract, while Pricing
and Greeks engines own the mathematical calculation.

## Responsibilities

Option Chain Engine is responsible for:

- organizing contracts by underlying, expiration, strike, and option right;
- pairing calls and puts into chain rows;
- attaching normalized quotes, OI, volume, quote quality, IV, and Greeks;
- exposing ATM, ITM/OTM, DTE, moneyness, liquidity, and spread queries;
- producing chain snapshots for research, backtest, risk, and monitoring.

It is not responsible for:

- downloading raw external market data;
- repairing parquet files or batch download state;
- fitting IV surfaces;
- generating strategy signals;
- calculating portfolio risk limits;
- placing or cancelling orders.

## Interfaces

The engine consumes stable core objects:

- `UnderlyingQuote`
- `OptionContractRef`
- `OptionQuote`
- `OptionGreeks`

It produces:

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

This lets the same engine consume live quotes, parquet snapshots, replay data,
or synthetic test data without changing chain logic.

## Internal Modules

```text
option_chain/
  builder.py
  chain.py
  adapters/
    snapshot.py
```

Planned modules:

```text
  contract_registry.py
  quote_book.py
  chain_snapshot.py
  chain_query.py
  liquidity.py
```

## MVP Scope

The first implementation should support:

1. core contract, quote, Greeks, and chain-row models;
2. building a chain from normalized in-memory objects;
3. adapting existing four-term snapshot dataframes into `OptionChain`;
4. expiration, strike, and call/put alignment;
5. ATM, DTE, moneyness, spread, OI, volume, and delta filtering;
6. attaching existing IV and Greeks fields from the data platform;
7. tests that keep query behavior stable for downstream systems.

## Phase 2: Real-Time Chain

After the historical data platform stabilizes:

- introduce incremental `QuoteBook` updates;
- support chain refresh by market event;
- attach Pricing / Greeks Engine outputs by contract id;
- emit `OptionChainUpdated` events;
- publish chain quality metrics to Monitoring.

Candidate events:

```text
ContractUniverseUpdated
QuoteUpdated
GreeksUpdated
OptionChainUpdated
LiquidityStateChanged
```

## Phase 3: Fund-Level Chain Service

The fund-level service should support:

- MO, IO, HO, ETF options, and commodity options through one interface;
- consistent historical replay and live semantics;
- versioned chain snapshots;
- data-quality traceability;
- shared consumption by research, strategy, backtest, risk, and execution.

The target state is one Option Chain API for research, backtest, live trading,
and real-time risk.

# Pricing Model Plan v0

## Positioning

Pricing / Greeks Engine is an independent system. It calculates theoretical
prices, raw implied volatility, and raw Greeks from normalized market inputs.
The Option Chain Engine only attaches and exposes those outputs.

This keeps the platform decoupled:

```text
Option Chain Engine
  provides contract + quote + forward

Pricing / Greeks Engine
  calculates raw IV and raw Greeks

IV Surface Engine
  fits smooth IV and surface Greeks

Option Chain Engine
  attaches raw/smooth values for query and downstream consumption
```

## First Model

For MO and other index futures options, the first model is Black-76:

```text
F = forward or futures price
K = strike
T = time to expiry in years
r = risk-free rate
sigma = volatility
```

Outputs:

- theoretical price;
- forward/futures delta;
- gamma;
- theta;
- vega;
- rho;
- raw implied volatility from market price.

## Price Input Policy

The data platform decides the mark price before model calculation:

1. valid bid/ask: mid or micro price;
2. valid but wide bid/ask: keep price and mark `wide_spread`;
3. last inside spread: `last_inside_spread`;
4. last only: `last_fallback`;
5. no valid price: `no_price`.

The pricing engine consumes that market price and preserves quality flags. It
does not silently interpolate missing prices.

## Quality Labels

Initial IV quality labels:

- `ok`
- `no_price`
- `below_intrinsic`
- `expired`
- `zero_time`
- `invalid_forward`
- `invalid_strike`
- `invalid_volatility`
- `wide_spread`
- `stale_quote`
- `solve_failed`
- `outlier`

## MVP Scope

1. Implement Black-76 price and Greeks.
2. Implement bisection implied volatility.
3. Return explicit quality and method metadata.
4. Keep all calculations independent from data storage and option-chain logic.
5. Attach results to `OptionGreeks` later through a separate adapter/service.

## Later Extensions

- Black-Scholes with dividend yield for ETF options;
- American option binomial tree where exercise style matters;
- surface-smoothed Greeks from IV Surface Engine;
- stochastic volatility and local volatility models for research only;
- model comparison reports for monitoring and validation.

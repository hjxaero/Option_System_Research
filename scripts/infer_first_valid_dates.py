from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from option_platform.common.settings import PlatformPaths
from option_platform.data.contract_dates import (
    infer_first_valid_dates_from_quote_root,
    load_first_valid_date_cache,
    save_first_valid_date_cache,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Infer per-symbol first valid quote dates from local minute quote parquet files.")
    parser.add_argument("--product", default="MO")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--output")
    parser.add_argument("--merge-existing", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = PlatformPaths.from_root(PROJECT_ROOT)
    output = (
        Path(args.output)
        if args.output
        else paths.data_root / "contracts" / args.product.upper() / "first_valid_dates.json"
    )
    inferred = infer_first_valid_dates_from_quote_root(paths.data_root, args.product, args.start, args.end)
    if args.merge_existing:
        existing = load_first_valid_date_cache(output)
        for symbol, trade_date in inferred.items():
            previous = existing.get(symbol)
            if previous is None or trade_date < previous:
                existing[symbol] = trade_date
        inferred = existing
    save_first_valid_date_cache(inferred, output)
    print(f"symbols={len(inferred)} output={output}")


if __name__ == "__main__":
    main()

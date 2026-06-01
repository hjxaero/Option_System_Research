# IM 股指期货分钟盘口 — 独立存储 Demo

## 设计理解

| 维度 | MO 期权分钟盘口 | IM 股指期货分钟盘口 |
|------|-----------------|---------------------|
| 业务实体 | 大量期权合约（四期限 × 行权价） | 少量月份合约（当月/次月等） |
| 存储组织 | `quotes/minute/MO/{symbol}/{trade_date}.parquet`（按合约分文件） | **独立树** `futures/IM/`，**按交易日单文件** |
| 与 MO 关系 | 按 **`YYMM` 月份码配对**（MO2601↔IM2601） | **不**嵌在 MO 路径；配对写在 `meta/contract_calendar` 的 `contract_month` |
| 时间轴 | `target_time` = 日盘 241 分钟 | **同一套** `generate_session_minutes`（`09:30–11:30`、`13:00–15:00`） |
| 下游关联 | MO 行 → 解析月份码 → 同码 IM 价 | **`contract_month` + `trade_date` + `target_time`**；存储目录仍与 MO 分离 |

要点：**IM 是独立资产线**；与 MO 共享的只是 **交易所日盘分钟网格**（对齐用），不是目录结构或 manifest。

### 月份配对（业务语义，已确认）

同一 **合约月份码**（CFFEX 品种代码里的 `YYMM`，如 `2601`）下，MO 与 IM 是一组定价关系：

| 组 | MO（期权，示意） | IM（期指） | 含义 |
|----|------------------|------------|------|
| 2601 组 | `CFFEX.MO2601-C-6000` 等 | `CFFEX.IM2601` | 2026 年 1 月到期 MO 链 → 用 **IM2601** 作 forward |
| 2602 组 | `CFFEX.MO2602-P-7000` 等 | `CFFEX.IM2602` | 2026 年 2 月到期 MO 链 → 用 **IM2602** |

- **不是**「全市场 MO 共用一个当日主力 IM」；四期限下 **每个 MO 到期月** 对应 **同码 IM**。
- 存储仍独立：IM 按日一个文件，文件内可含 **多个 `symbol`**（2601、2602、2603… 各 241 分钟行块）。
- 下游 join：`contract_month`（从 MO/IM `symbol` 解析）+ `trade_date` + `target_time` → 取该月 IM 盘口价。

---

## 目录 Demo

```text
data_store/
  futures/
    IM/
      meta/
        contract_calendar.parquet      # 每日挂牌合约与推荐定价合约（可选多行/日）
      minute/
        2025-05-27.parquet             # 该交易日全部 IM 分钟盘口（见下表）
        2025-05-28.parquet
      state/
        2025-05-27.json                # 增量游标（可选）
      quality/
        2025-05-27.json                # 当日 ok_ratio 等（可选）
```

**不按 MO 的 `{symbol}/{trade_date}` 扇出**：IM 活跃合约少，**按日一个 parquet** 更利于读 forward；换月日同一文件内可出现多个 `symbol`（每行仍是一个 `(symbol, target_time)`）。

---

## `minute/{trade_date}.parquet` 列定义（Demo）

| 列 | 类型 | 说明 |
|----|------|------|
| `trade_date` | date / string | 交易日 `YYYY-MM-DD` |
| `symbol` | string | Tq 合约，如 `CFFEX.IM2506` |
| `expiry_date` | string | 合约到期日（元数据，便于审计） |
| `target_time` | datetime64[ns] | **对齐分钟**（与 MO 相同网格） |
| `quote_time` | datetime64[ns] | 对齐采用的 tick 时间（`<= target_time` 最近一条） |
| `quote_age_ms` | float | `target_time - quote_time`（毫秒） |
| `bid_price1` / `ask_price1` | float | 一档盘口 |
| `bid_volume1` / `ask_volume1` | int | 一档量 |
| `last_price` | float | 最新价（fallback） |
| `mid_price` / `micro_price` | float | 由盘口推导 |
| `spread` / `spread_bps` | float | 价差 |
| `price_source` | string | `micro` / `mid` / `last_fallback` / `missing` |
| `quote_quality` | string | `ok` / `wide_spread` / `stale` / `missing` / … |
| `volume` / `open_interest` | float | 期货 tick 若有则保留 |

**主键（逻辑）**：`(trade_date, symbol, target_time)`。同一交易日文件内通常有 **2～4 个 `symbol`**（对应当日四期限涉及的 MO 月份，各一条 IM）。

可选列 `contract_month`（`YYMM`，如 `2506`）与 `symbol` 冗余但便于 join，可与 MO 侧解析规则一致。

---

## `meta/contract_calendar.parquet`（Demo）

| trade_date | contract_month | symbol | expiry_date | note |
|------------|----------------|--------|-------------|------|
| 2025-05-27 | 2506 | CFFEX.IM2506 | 2025-06-20 | 与 `MO2506-*` 同组 |
| 2025-05-27 | 2507 | CFFEX.IM2507 | 2025-07-18 | 与 `MO2507-*` 同组（次月） |
| 2025-05-27 | 2509 | CFFEX.IM2509 | 2025-09-19 | 与 `MO2509-*` 同组（季月） |
| 2026-01-15 | 2601 | CFFEX.IM2601 | 2026-01-16 | 与 `MO2601-*` 同组 |

每个 `contract_month` 在该 `trade_date` 至多一行；E3 下载时按当日 MO 四期限涉及的月份 **批量拉 IM** 写入同一 `minute/{trade_date}.parquet`。

---

## 分钟文件内容样例（3 行示意）

完整交易日为 **241 行 × 当日 symbol 数**（通常 1，换月日 2+）。

| trade_date | symbol | target_time | quote_time | quote_age_ms | bid_price1 | ask_price1 | micro_price | price_source | quote_quality |
|------------|--------|-------------|------------|--------------|------------|------------|-------------|--------------|---------------|
| 2025-05-27 | CFFEX.IM2506 | 2025-05-27 09:30:00 | 2025-05-27 09:30:00 | 0 | 5123.0 | 5123.2 | 5123.08 | micro | ok |
| 2025-05-27 | CFFEX.IM2506 | 2025-05-27 09:31:00 | 2025-05-27 09:31:00 | 0 | 5124.0 | 5124.4 | 5124.16 | micro | ok |
| 2025-05-27 | CFFEX.IM2506 | 2025-05-27 15:00:00 | 2025-05-27 15:00:00 | 0 | 5118.6 | 5119.0 | 5118.76 | micro | ok |

---

## 与 MO 对齐、存储独立：Join 示意

```python
import re

def mo_contract_month(mo_symbol: str) -> str:
    # CFFEX.MO2601-C-6000 -> "2601"
    m = re.search(r"\.MO(\d{4})-", mo_symbol)
    return m.group(1) if m else ""

mo_snap = read_parquet("snapshots/...")  # symbol, timestamp, expiry_date, ...
im_day = read_parquet("futures/IM/minute/2025-05-27.parquet")

mo_snap = mo_snap.assign(contract_month=mo_snap["symbol"].map(mo_contract_month))
fwd = im_day.rename(columns={"micro_price": "futures_price", "quote_quality": "futures_quote_quality"})
merged = mo_snap.merge(
    fwd,
    on=["contract_month", "target_time"],  # im_day 需带 contract_month 或由 symbol 解析
    how="left",
    suffixes=("", "_im"),
)
# 2601 组 MO 只会撞上 IM2601；2602 组只会撞上 IM2602
```

---

## 生成本地 Demo 文件

```bash
# 合成 demo（旧路径 data_store/_demo/...）
python scripts/write_im_storage_demo.py

# 正式管线（需 TQ_USER / TQ_PASS）
PYTHONPATH=. python scripts/build_im_minute_quotes.py --start 2025-05-27 --end 2025-05-27
```

产出（默认，可 gitignore）：

- `data_store/_demo/futures/IM/meta/contract_calendar.parquet`
- `data_store/_demo/futures/IM/minute/2025-05-27.parquet`（241 行合成数据）

仓库内另有 **3 行 CSV 样例**（无需跑脚本）：`docs_fix/examples/im_minute_2025-05-27_head.csv`、`docs_fix/examples/im_contract_calendar_head.csv`。

用 DuckDB / pandas 查看生成文件（需 pyarrow 时方为 `.parquet`，否则脚本会写 `.csv`）：

```bash
PYTHONPATH=. python3 scripts/write_im_storage_demo.py
```

---

## 与 `data_catalog.json` 的关系（待 E1）

建议在 catalog 增加 **独立** `IM` 产品块与路径模板，例如：

```json
"futures_minute": "futures/{product}/minute/{trade_date}.parquet",
"futures_contract_calendar": "futures/{product}/meta/contract_calendar.parquet"
```

**不要**复用 MO 的 `quotes/minute/{product}/...` 模板，避免语义上把 IM 当成「第三种 MO 合约」。

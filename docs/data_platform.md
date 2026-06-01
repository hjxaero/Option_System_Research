# 数据中台 v0

## 定位

数据中台只负责把外部行情变成稳定、可复用、可审计的数据资产。策略、回测和实盘都从这里取数据，不各自重复拉行情、算 Greeks 或处理合约换月。

## 第一阶段范围

- 数据源：天勤 `tqsdk`
- 首个品种：MO 中证1000股指期权
- 数据粒度：1 分钟
- 合约范围：当月、次月、当季、次季四个到期日
- 核心产物：分钟盘口、期权链快照 parquet
- 派生字段：mark price、IV、Delta、Gamma、Theta、Vega、卖方保证金
- 存储路径：`data_store/`

## 盘口与定价

天勤 `Quote`/`Tick` 对象包含 `bid_price1`、`ask_price1`、`bid_volume1`、`ask_volume1`。历史区间可通过 `get_tick_data_series()` 获取 tick 序列，但这是专业版接口。

1 分钟 K 线只有最新价 OHLC，不适合直接作为期权 IV 定价输入。新的定价优先级是：

1. 买一/卖一有效且价差正常：用盘口微价格或中间价。
2. 盘口有效但价差过宽：保留价格，但标记 `iv_quality=wide_spread`。
3. 最新价位于买卖价之间：可作为降级输入，标记 `last_inside_spread`。
4. 只有最新价：仅作低质量 fallback，标记 `last_fallback`。
5. 无有效价格：不计算 IV，不做静默插值。

所有快照必须保存 `price_source`、`bid_price1`、`ask_price1`、`mid_price`、`micro_price`、`spread_bps` 和 `iv_quality`。

## 已知盘口质量限制

MO 的深度虚值、远月或低活跃合约可能长期没有有效买一/卖一，历史 tick 能正常下载，但对齐到标准分钟后仍会出现大量 `missing`、`stale` 或 `low_liquidity`。这类问题属于市场流动性限制，不再视为下载失败。

处理规则：

1. 原始分钟快照仍完整保存，保留 `quote_quality`、`quote_age_ms`、`spread_bps` 等字段。
2. 修复清单中的 `missing_file` 必须优先补齐；补齐后若只剩 `low_usable|high_missing`、`high_stale` 等低流动性问题，标注为已知限制。
3. IV 和 Greeks 默认只消费有效盘口或明确降级的价格，不对无锚点的深虚值缺口做静默插值。
4. IV 曲面默认剔除这类节点，必要时保留为 `no_price`、`stale_quote`、`low_liquidity` 或 `surface_excluded`。
5. 后续若有更好的交易所深度行情、做市商报价源或曲面模型，再独立升级这部分质量修复逻辑。

## 四期限合约池

标准期限角色：

- `current_month`
- `next_month`
- `current_quarter`
- `next_quarter`

如果月度合约与季度合约重合，季度角色向后顺延，保证在市场挂牌足够时保存四个不同到期日。

## 分层

1. `sources`
   外部数据源适配器。账号密码只能从环境变量读取，不能写入代码。

2. `contracts`
   统一合约主数据和快照字段契约。

3. `snapshots`
   期权链快照生成。当前先通过 `legacy_tq_mo` 包住旧项目成熟逻辑，后续逐步把旧模块迁入新中台。

4. `quality`
   数据完整性检查、空文件检查、尾部时间戳检查。

5. `storage`
   统一目录和命名规则。

## 数据库目录

```text
data_store/
  contracts/{product}/{trade_date}.parquet
  ticks/{product}/{symbol}/{trade_date}.parquet
  quotes/minute/{product}/{symbol}/{trade_date}.parquet
  snapshots/four_term/{product}/{trade_date}.parquet
  snapshots/four_term_enriched/{product}/{trade_date}.parquet
  surfaces/iv_nodes/{product}/{trade_date}.parquet
  quality/iv_surface/{product}/{trade_date}.json
  quality/{product}/{trade_date}.json
```

平台规则见 [project_rules.md](project_rules.md)。  
系统 2 快照见 [option_chain_snapshot_plan.md](option_chain_snapshot_plan.md)；系统 3 计划与进度见 [iv_surface_engine_plan.md](iv_surface_engine_plan.md)。

## 盘中更新

分钟盘口更新入口：

```powershell
python scripts/update_daily_minute_quotes.py --symbol CFFEX.MO2606-C-6000 --date 2026-05-27
```

四期限全合约批量更新入口：

```powershell
# 盘中：只更新最近 30 分钟
python scripts/update_four_term_minute_quotes.py --date 2026-05-27 --window-minutes 30

# 调试：只跑前 20 个合约
python scripts/update_four_term_minute_quotes.py --date 2026-05-27 --window-minutes 30 --max-contracts 20

# 收盘后：完整补齐当日
python scripts/update_four_term_minute_quotes.py --date 2026-05-27 --full-refresh
```

四期限快照生成入口：

```powershell
# 从已下载的分钟盘口生成每日四期限期权链快照
python scripts/build_four_term_snapshots.py --start 2026-01-05 --end 2026-01-31

# 预览，不写文件
python scripts/build_four_term_snapshots.py --start 2026-01-05 --end 2026-01-31 --dry-run

# 强制重建已经完整的快照
python scripts/build_four_term_snapshots.py --start 2026-01-05 --end 2026-01-31 --force
```

更新流程：

1. 下载当日 tick。
2. 对齐到标准分钟时间轴。
3. 与已有 parquet 合并。
4. 按 `symbol + target_time` 去重，保留质量更高、`quote_time` 更新的记录。
5. 写临时 parquet 后原子替换。
6. 写状态文件到 `data_store/quality/{product}/{symbol}/{date}.state.json`。

盘中窗口模式会从窗口起点向前回看 tick，避免窗口第一分钟缺少前序盘口；是否可用仍由 `quote_age_ms` 和 `quote_quality` 决定。

## 断点续下与续算

分钟盘口层和快照层都必须支持断点续跑。

分钟盘口层：

1. 文件粒度是 `quotes/minute/{product}/{symbol}/{trade_date}.parquet`。
2. 批量下载默认启用 `--skip-complete`。
3. 已存在且行数、基础质量达标的合约日文件会跳过。
4. 中断后重跑同一命令，只补未完成或低质量文件。

四期限快照层：

1. 文件粒度是 `snapshots/four_term/{product}/{trade_date}.parquet`。
2. 生成快照前先检查当日四期限预期合约的分钟盘口文件是否齐全。
3. 如果有缺失或行数过短的分钟盘口文件，当日快照标记为 incomplete，不生成半成品快照。
4. 已存在快照必须满足：
   - 合约集合等于当日四期限预期合约集合。
   - 行数不低于 `合约数 * min_minutes`。
   - `symbol + timestamp` 无重复。
   - `timestamp` 日期等于交易日。
5. 满足以上条件时默认跳过；需要重建时使用 `--force`。

## 全历史下载规则

MO 全历史从已过期合约开始，天勤可通过 `query_quotes(expired=True)` 查询历史合约。当前已验证 MO 合约缓存可覆盖 `2022-08-19` 到 `2027-03-19` 到期日。

全历史不能一次性无脑按 `expiry_date >= trade_date` 全扫，原因是早期或深虚值行权价可能长期没有有效盘口。处理方式：

1. 刷新全历史合约缓存：

```powershell
python scripts/build_month_four_term_minute_quotes.py `
  --start 2022-07-22 --end 2022-08-31 `
  --refresh-contracts --dry-run
```

2. 每个分段下载后，从本地 parquet 推断首个有效行情日：

```powershell
python scripts/infer_first_valid_dates.py --product MO --start 2022-07-22 --end 2022-08-31
```

3. 后续分段下载带上首个有效行情日 cache 和重试参数：

```powershell
python scripts/build_month_four_term_minute_quotes.py `
  --start 2022-07-22 --end 2022-08-31 `
  --workers 6 `
  --first-valid-date-cache data_store/contracts/MO/first_valid_dates.json `
  --retry-attempts 3 --retry-sleep-seconds 3
```

4. 失败的合约日会输出到 `{prefix}_failures.csv`，后续按失败计划重跑。
5. 推荐按月分块跑全历史，不建议一次跑多年任务。

## 周期质量试跑

首次下载一个周期前，建议先限制合约数或天数，确认账号权限、速度和盘口质量：

```powershell
python scripts/probe_mo_cycle_quality.py --as-of 2026-05-27 --max-days 1 --max-contracts 20
```

确认稳定后再下载完整周期：

```powershell
python scripts/probe_mo_cycle_quality.py --as-of 2026-05-27 --max-contracts 0 --max-days 0
```

报告输出：

```text
data_store/quality/MO/cycle_probe/
  MO_<start>_<expiry>_summary.json
  MO_<start>_<expiry>_by_symbol.csv
```

## 运行示例

先在 PowerShell 设置天勤账号：

```powershell
$env:TQ_USER="your_user"
$env:TQ_PASS="your_password"
```

预览任务：

```powershell
python scripts/build_mo_snapshots.py --end 2026-05-27 --dry-run
```

下载单合约 tick 并聚合成分钟盘口：

```powershell
python scripts/download_tq_ticks.py --symbol CFFEX.MO2606-C-6000 --start 2026-05-26 --end 2026-05-27
```

## 迁移原则

旧项目 `E:\Option_Sell_Research` 里已经有可用的数据生产逻辑。新中台第一步保留旧逻辑作为兼容入口，同时新增四期限、盘口定价、质量标签模块。等这些边界稳定后，再把旧的 `data_loader`、`snapshot_builder`、`binomial_tree`、`trading_calendar`、`unified_margin_calculator` 分批迁入，并替换掉只基于最新价的 IV 计算。

# Option System Research 项目规则

本项目是期权量化私募系统的基础工程，当前阶段只做 **数据中台**。旧项目 `Option_Sell_Research` 的规则只作为经验来源；本项目拥有独立规则。

## 1. 项目定位

1. 当前主线是建设高质量期权数据中台。
2. 第一品种是 MO 中证1000股指期权。
3. 第一目标不是双卖策略、不是回测引擎，而是可复用、可审计、可扩展的数据底座。
4. 后续策略、回测、实盘、风控都必须从数据中台读取标准数据。

## 2. 分层边界

```text
option_platform/
  common/          # 配置、路径、通用工具
  data/
    sources/       # 外部数据源适配
    storage/       # 存储布局
    quality/       # 数据质量检查
    snapshots/     # 期权链快照
    contracts.py   # 数据契约
scripts/           # 命令入口
docs/              # 架构、规则、上下文
tests/             # 自动化测试
```

规则：

1. `scripts/` 只放命令入口，不堆业务逻辑。
2. 业务逻辑优先放入 `option_platform/`。
3. 旧项目代码只能通过边界模块兼容调用，不能直接复制研究脚本成为主路径。
4. 新增数据规则必须配轻量测试。

## 3. TqSdk 使用规则

1. 回答或编写 TqSdk 代码前，遵循已下载技能包：
   `.codex_tmp/tqsdk-trading-and-data/tqsdk-trading-and-data/SKILL.md`
2. `get_quote`、`get_kline_serial`、`get_tick_serial` 返回 live reference，需要 `wait_update()` 推动更新。
3. 长历史行情优先考虑 `DataDownloader`。
4. 精确历史盘口可用 `get_tick_data_series()`，但需确认账号权限。
5. `TqApi` 必须显式关闭，优先使用项目内 `tq_api()` 上下文管理器。
6. 账号、密码、token 只能来自环境变量或本地未入库配置。

## 4. 数据库目录

标准目录：

```text
data_store/
  contracts/{product}/{trade_date}.parquet
  ticks/{product}/{symbol}/{trade_date}.parquet
  quotes/minute/{product}/{symbol}/{trade_date}.parquet
  snapshots/four_term/{product}/{trade_date}.parquet
  quality/{product}/{trade_date}.json
```

规则：

1. `data_store/` 默认不入库。
2. parquet 字段使用英文小写蛇形命名。
3. 所有数据文件含义必须能从 `configs/data_catalog.json` 解释。
4. 原始层、标准层、派生层分开保存，不互相覆盖。

## 5. 时间轴规则

1. 每个交易日先生成标准分钟时间轴，再把 tick 盘口对齐到时间轴。
2. MO 默认分钟时间轴：
   - `09:30` 到 `11:30`
   - `13:00` 到 `15:00`
3. 对齐规则：取 `quote_time <= target_time` 的最近一条 tick。
4. 必须保存：
   - `target_time`
   - `quote_time`
   - `quote_age_ms`
5. 默认 `quote_age_ms > 60000` 标记为 `stale`。

## 5.1 盘中更新规则

1. 盘中更新必须是增量、幂等、可恢复的。
2. 不允许每分钟重算全历史；默认只更新当前交易日当前合约的数据文件。
3. 盘中默认更新最近 N 分钟，收盘后用完整补齐。
4. 窗口更新必须从窗口起点向前回看 tick，避免窗口第一分钟丢失前序盘口。
5. 更新后按 `symbol + target_time` 去重。
6. 同一 `target_time` 有多条记录时，优先保留：
   - `quote_quality` 更高的记录
   - 质量相同则保留 `quote_time` 更新的记录
7. parquet 写入必须先写临时文件，再原子替换正式文件，避免半写文件。
8. 每次更新必须写状态文件，记录：
   - `last_target_time`
   - `last_quote_time`
   - `rows`
   - `updated_at`
9. 盘中策略跟踪只能读取已经落盘且通过合并规则的数据，不直接读半成品临时文件。

## 5.2 断点续跑规则

1. 分钟盘口下载按 `symbol + trade_date` 续跑。
2. 已完成分钟盘口文件默认跳过，不重复下载。
3. 四期限快照按 `product + trade_date` 续算。
4. 快照生成前必须确认当日四期限所有预期合约的分钟盘口文件存在且行数达标。
5. 不允许在分钟盘口缺失时生成半成品快照。
6. 已完成快照默认跳过；完整性检查至少包含：
   - 合约集合等于当日四期限预期合约集合。
   - 行数达标。
   - `symbol + timestamp` 无重复。
   - `timestamp` 只属于该交易日。
7. 所有 parquet 写入必须先写临时文件，再原子替换正式文件。
8. 需要重建时必须显式使用 `--force` 或等价参数。

## 5.3 全历史下载规则

1. 全历史下载必须按月份或更小区间分块，不允许默认启动多年长任务。
2. 查询历史合约时必须包含已过期合约。
3. 下载排程不能只依赖 `expiry_date >= trade_date`。
4. 对长期无有效盘口的合约，使用 `first_valid_dates.json` 记录首个有效行情日。
5. 带首个有效行情日 cache 下载时，跳过早于该日期的合约日。
6. 每个合约日下载必须支持重试，默认至少 2 次。
7. 重试后仍失败的合约日必须写入失败计划 CSV，便于后续定向重跑。
8. 全历史过程允许保留低流动性缺口，但必须用质量标签和 repair/failure 清单显式记录。

## 6. 合约池规则

标准快照保存四个到期日：

- `current_month`
- `next_month`
- `current_quarter`
- `next_quarter`

规则：

1. 每条快照必须保存 `term_role`。
2. 如果月度和季度重合，季度角色向后顺延，尽量保证四个不同到期日。
3. 合约选择逻辑属于数据中台，不属于策略。

## 7. 盘口定价规则

IV 和 Greeks 的价格输入优先来自盘口，不优先用最新价。

优先级：

1. 买卖一有效且有深度：`micro_price`
2. 买卖一有效：`mid_price`
3. 最新价在买卖价之间：`last_inside_spread`
4. 只有最新价：`last_fallback`

必须保存：

- `bid_price1`
- `ask_price1`
- `bid_volume1`
- `ask_volume1`
- `mid_price`
- `micro_price`
- `spread_bps`
- `price_source`
- `quote_quality`
- `iv_quality`

禁止：

1. 用 1 分钟 K 线模拟盘口来计算高质量 IV。
2. 把最新价计算出来的 IV 标记为正常盘口 IV。
3. 盘口无效、过旧或价差异常时静默填充为正常值。
4. 标准快照表必须保存 `mark_price`，不能只保存旧式 `price` 字段。

曲面字段与质量标签见 `docs/iv_surface_engine_plan.md` 与 `option_platform/data/contracts.py`（`IvSurfaceSchema`）。

## 8. IV 缺失规则

1. 直接求解成功标记为 `calc`。
2. 插值结果必须标记为 `interp`。
3. 不允许跨到期日插值。
4. 不允许对两端无锚点的深虚值/深实值合约做无标签外推。
5. 回测默认只使用质量合格的 IV，低质量 IV 需要策略显式声明。
6. 深虚值、远月或低活跃合约在历史 tick 完整下载后仍长期无有效盘口时，标注为已知流动性限制，不再视为下载失败。
7. `missing_file` 必须修复；修复后剩余的 `low_usable|high_missing`、`high_stale`、`low_liquidity` 默认只能进入原始快照层，不能进入默认 IV 曲面。

## 8.0 到期时间 T 规则

1. IV 和 Greeks 的 `T` 必须按交易分钟流逝计算。
2. MO 第一阶段约定一天 240 分钟，一年 252 个交易日。
3. `T = 剩余交易分钟 / (252 * 240)`。
4. 禁止在每天开盘时因为日历天变化直接减去一整天。
5. 夜间和非交易时段不扣减交易分钟，避免人为制造 IV 跳跃。
6. 快照时间轴可以包含 `09:30`、`11:30`、`13:00`、`15:00` 这些状态点，但 T 的日内衰减严格按 `09:30-11:30` 和 `13:00-15:00` 合计 240 分钟计算。

## 8.1 IV 曲面规则

1. IV 曲面从标准快照表派生，不覆盖原始快照。
2. 曲面表必须同时保存 `raw_iv` 和 `smooth_iv`。
3. 第一阶段只允许期限内线性插值，不做 SVI/SABR/SSVI。
4. 插值节点必须标记 `interpolated`。
5. 不允许跨到期日补值。
6. 曲面宁愿有洞，也不把脏数据平滑成正常数据。

## 9. 文档规则

1. 与用户沟通、项目文档、架构说明使用简体中文。
2. 代码标识符、CLI 参数、parquet 列名使用英文。
3. 复杂公式先白话定义变量，再写公式。
4. 敏感默认值必须在相关 README 或设计文档中显式列出。
5. 跨模块架构决策写入 `docs/`，不把长聊天记录逐字粘贴进文档。

## 10. 测试规则

1. 新增核心数据规则必须有测试。
2. 当前最低验证命令：

```powershell
E:\Normal_Venv\Scripts\python.exe -m pytest
E:\Normal_Venv\Scripts\python.exe -m compileall option_platform scripts tests
```

3. 涉及 TqSdk 网络或权限的测试不直接放入普通单元测试，应做成可手动运行的脚本或集成测试。

## 11. 旧项目迁移规则

1. `E:\Option_Sell_Research` 是历史研究项目，不是新项目主路径。
2. 可以复用旧算法思想和部分成熟实现。
3. 不继续扩展旧 `archive/` 或旧策略脚本。
4. 旧 `snapshot_builder` 只能作为过渡兼容层，目标是迁移到盘口驱动、四期限、质量标签的新快照生成器。

# 市场数据系统 Agent — 计划与进度

> **权威台账**：市场数据 Agent 的工作计划、执行进度、阻塞与下一步 **以本文件为准**。  
> 每完成一项任务（或一次可汇报的阶段）后 **必须更新** 本文件（含「最后更新」时间与变更记录）。  
> 范围：**分钟盘口原始层** — MO 期权 + 定价用股指期货 **IM**（不含快照 / IV / 曲面）。  
> IM 专项计划见 **§6**。

最后更新：**2026-06-02**（用户续跑 P0：重启第 33 窗下载 + 看门狗）

---

## 1. 使命与边界

| 项 | 说明 |
|----|------|
| 交付物 A | `quotes/minute/MO/{symbol}/{trade_date}.parquet`（MO 四期限期权） |
| 交付物 B | `futures/IM/minute/{trade_date}.parquet` + `futures/IM/meta/contract_calendar.parquet`（见 storage demo 文档） |
| MO 目标区间 | `2022-07-22` → `2026-05-30`（10 日分窗，进行中） |
| IM 目标区间 | 与 MO **交易日对齐**；合约按日解析主力/近月（见 §6） |
| 编排 | MO：`build_windowed_four_term_minute_quotes.py`；IM：待建（§6，复用分钟对齐管线） |
| 不在范围 | 快照、IV/Greeks、曲面、将 IM 并入 MO parquet、策略/回测/实盘 |

规则：`.cursor/rules/market-data-agent.mdc`

---

## 2. 总体计划

### 阶段 A — 工程能力（已完成）

- [x] 四期限分窗下载 `build_windowed_four_term_minute_quotes.py`
- [x] 单窗下载 `build_month_four_term_minute_quotes.py`（worker 内 **跨日** `update_symbol_range_minute_quotes`）
- [x] `--skip-complete`、manifest 续跑、`first_valid_dates.json`
- [x] 质量：`generate_repair_plan` / `repair_minute_quotes_from_plan`
- [x] 默认 `workers=4`，`min-workers=4`；`caffeinate -dims` 长跑建议

### 阶段 B — 全历史分钟盘口下载（进行中）

- [ ] 141 个 10 日窗全部 manifest 完成
- [ ] 各窗 `failed_symbols` 扫尾（按 `*_failures.csv`）
- [ ] 全区间分钟层 repair 计划（按需，非每窗必做）

### 阶段 C — 已覆盖区间质量巩固（部分完成）

- [x] `2022-07-22`～`2022-10-19` 聚焦补拉（5014 合约-日，`failed_symbols=0`）
- [x] 第 8 窗 failures 定向重下（177 合约 → **12** 仍失败，`MO_20220930_20221009_retry_failures.csv`）
- [ ] 第 8 窗余 **12** 合约二次扫尾（可选）
- [ ] 各窗零星 failures 合并补拉（可选）

### 阶段 D — 交付验收（未开始）

- [ ] MO 全历史下载完成后，生成 **分钟层** 区间质量摘要（非快照 gate）
- [ ] 更新 `first_valid_dates.json` 全区间
- [ ] 向用户移交：manifest、failures 索引、已知流动性限制说明

### 阶段 E — 股指期货 IM 分钟盘口（新需求，未开始）

> **背景**：`configs/data_catalog.json` 已定义 MO 的 `pricing_future_product: "IM"`，但 `four_term` 快照里 `futures_price` 仍为 NA；下游 IV/曲面/链引擎需要 **可靠 forward**，应来自 **IM 期货盘口分钟价**，而非指数现货或期权推导。

- [ ] **E1** 设计与契约（见 §6.2）
- [ ] **E2** 冒烟：单日/单合约 tick → 分钟对齐质量
- [ ] **E3** 实现下载与存储（复用 `tq_minute_quotes` + `live_update`）
- [ ] **E4** 按 MO 日历分窗拉全历史 IM（独立 manifest，**不与 MO 下载并行**）
- [ ] **E5** IM 质量 repair + 分钟层报告；输出「MO 日 × timestamp → IM symbol / 盘口价」索引供下游

**与 P0 关系**：P0（MO）继续优先；IM 在 **MO 单流水线空闲时** 或 **MO 达里程碑后** 启动，避免 Tq FileLock 冲突。

---

## 3. 当前进度快照

| 指标 | 数值 |
|------|------|
| 分窗进度 | **33 / 141**（23.4%） |
| 日历覆盖（manifest 已完成） | **2022-07-22** ～ **2023-06-16** |
| 当前窗 | **第 34 窗**：`2023-06-17` ～ `2023-06-26`（**进行中**） |
| 本地 parquet 文件数 | 约 **45,672** |
| 后台任务 | **P0 全历史下载 + 看门狗**（`start_mo_download_with_watchdog.sh`，workers=4） |

Manifest：`data_store/quality/MO/batch_10d/MO_20220722_20260530_w10_manifest.json`  
日志：`data_store/quality/MO/batch_10d/full_history.log`

### 3.1 已完成分窗

| # | 区间 | 耗时 | saved | failed_symbols | 备注 |
|---|------|------|-------|----------------|------|
| 1 | 2022-07-22～07-31 | 6.8 min | 453 | 8 | |
| 2 | 2022-08-01～08-10 | 6.5 min | 708 | 2 | |
| 3 | 2022-08-11～08-20 | 3.0 min | 675 | 3 | |
| 4 | 2022-08-21～08-30 | 2.5 min | 752 | 3 | |
| 5 | 2022-08-31～09-09 | 51.8 min | 1559 | 7 | 冷数据窗 |
| 6 | 2022-09-10～09-19 | 40.6 min | 1203 | 17 | |
| 7 | 2022-09-20～09-29 | 62.2 min | 1680 | 15 | |
| 8 | 2022-09-30～10-09 | 5.2 min | 294 | **177→12** | P1 已补拉 906 日；余 12 合约见 `*_retry_failures.csv` |
| 9 | 2022-10-10～10-19 | 20.7 min | 1007 | 3 | |
| 10～32 | 2022-10-20～2023-06-06 | 见 manifest | 见 manifest | 见 manifest | 明细见 `window_metrics`（第 8 窗仍余 12 失败合约） |

### 3.2 质量补拉（分钟层）

| 区间 | 状态 | 说明 |
|------|------|------|
| 2022-07-22～2022-10-19 | **已完成** | `repair` 5014 日写入；报告 `MO_20220722_20221019_after_repair_summary.json` |

### 3.3 已知风险 / 阻塞

1. **第 8 窗余 12 失败**：P1 后从 177 降至 12；清单 `MO_20220930_20221009_retry_failures.csv`。  
2. **第 12 窗**：原 3 失败已补拉完成（`window12_retry.log`）。  
3. **勿并行 download**：Tq FileLock；同时只跑一条流水线。  
4. **`workers=2`**：实测易锁冲突，续跑统一用 **4**。

---

## 4. 下一步（优先级）

| 优先级 | 动作 | 命令/入口 |
|--------|------|-----------|
| P0 | 续跑 MO 全历史 | `build_windowed_four_term_minute_quotes.py`（**进行中**，勿并行 IM） |
| P0a | 研究「每窗耗时」与是否需要“窗内超时重启” | 看门狗重启前 **清理 orphan worker**（`monitor_mo_download_watchdog.py`）；`restart-if-window-elapsed` 仍待办 |
| P4 | IM 股指期货分钟盘口 | §6 阶段 E1→E5（待立项实施） |
| P1 | ~~补第 8 窗 failures~~ | **已完成**（906 saved，12 仍失败） |
| P1b | 余 12 合约再试 | `window8_failures_symbols.txt` 子集或读 `*_retry_failures.csv` |
| P2 | 各窗 failures 扫尾 | 合并 `batch_10d/*_failures.csv` |
| P3 | 全历史完成后再做区间 repair | `generate_repair_plan` + `repair_minute_quotes_from_plan` |

续跑示例（**下载 + 看门狗一条命令**，推荐）：

```bash
cd /Users/hjx_aero/Option_System_Research
bash scripts/start_mo_download_with_watchdog.sh
```

看门狗：`scripts/monitor_mo_download_watchdog.py`（进程意外停止自动重启；每完成 1 窗重启下载进程；**只** kill `build_windowed` / `build_month`）。日志：`batch_10d/watchdog.log`。

---

## 6. 新需求：股指期货（IM）分钟盘口计划

### 6.1 为什么要做

| 问题 | 说明 |
|------|------|
| 衍生数据质量 | IV、Greeks、曲面、链上 forward 依赖 **标的期货价**；仅用指数或期权反推不可靠 |
| 项目配置 | `pricing_future_product: "IM"`（中证1000股指期货，CFFEX） |
| 现状 | MO 分钟盘口在拉；**无** IM 分钟盘口资产；快照列 `futures_price` / `underlying_price` 占位 NA |
| Agent 边界 | 本 Agent 负责 **IM 原始分钟盘口**；写入快照/算 IV 属其他 Agent |

### 6.2 目标与存储

**目标**：对每个 MO 交易日、每个标准分钟 `target_time`，提供可审计的 IM **盘口**（bid/ask/mid/micro、质量标签），供下游按 `trade_date` + `timestamp` join。

**存储（独立资产线，仅时间轴与 MO 对齐）**：

- 详细 Demo：**`docs_fix/im_futures_minute_storage_demo.md`**；本地样例：`python scripts/write_im_storage_demo.py` → `data_store/_demo/futures/IM/`
- **不按 MO 的** `quotes/minute/MO/{symbol}/{date}` 组织；IM 用 **`futures/IM/minute/{trade_date}.parquet`**（按日单文件）+ **`futures/IM/meta/contract_calendar.parquet`**（定价合约日历）
- **对齐**：`target_time` 仍用 `generate_session_minutes`（241 点/日）；join 键为 `trade_date` + `target_time`，存储路径与 MO manifest 无耦合

### 6.3 合约选择（已确认：按月份码配对）

**规则（用户确认）**：MO 与 IM 按 **同一 `YYMM` 月份码** 成组，例如 **MO2601 期权链 ↔ IM2601 期指**，**MO2602 ↔ IM2602**；不是「全 MO 共用一张当日主力 IM」。

| MO 侧 | IM 侧 |
|--------|--------|
| `CFFEX.MO2601-C-6000` 等 | `CFFEX.IM2601` |
| `CFFEX.MO2602-P-7000` 等 | `CFFEX.IM2602` |

**v1 实现要点**：

1. 从 Tq 拉 `CFFEX.IM*`（含 `expired=True`）缓存；`contract_month` = 品种代码中的 4 位 `YYMM`。
2. 每个 `trade_date`：根据当日 MO 四期限涉及的 **到期月份集合**，解析出对应 IM 列表（通常 2～4 个 `symbol`），写入 **同一** `futures/IM/minute/{trade_date}.parquet`。
3. `meta/contract_calendar.parquet`：每行 `(trade_date, contract_month, symbol, expiry_date)`，供审计与下游 join。
4. 禁止把不同 `contract_month` 的 IM 价混给另一月 MO（避免 forward 错月）。

连续主力、指数现货不在 v1 范围。

### 6.4 实施阶段（建议顺序）

| 阶段 | 内容 | 产出 | 状态 |
|------|------|------|------|
| **E1** | `data_catalog.json` IM 块 + `option_platform/data/futures/*` | 已完成 | [x] |
| **E2** | 冒烟：`build_im_minute_quotes.py --dry-run` 或单日拉取（需 Tq） | 质量报告 | 待做 |
| **E3** | `scripts/build_im_minute_quotes.py`：MO 四期限 → 同码 IM、skip-complete、manifest | 已实现 | [x] |
| **E4** | 全历史：日期范围 **对齐 MO manifest 已覆盖段**，再随 MO 扩窗；独立 `IM_*_manifest.json` | 与 MO 同跨度 parquet | 待做 |
| **E5** | `generate_repair_plan` / repair；产出 `quality/IM/` 摘要；文档说明下游 join 键 | 移交下游 | 待做 |

**工程复用**（不重复造轮子）：

- `option_platform/data/sources/tq_minute_quotes.py`（tick 拉取与对齐）
- `option_platform/data/live_update.py` → `update_symbol_range_minute_quotes(..., product="IM")`
- `option_platform/data/cleaning.py`（盘口分级）
- 质量与 repair：`quality/repair.py` 同逻辑，product 参数化

**验收标准（分钟层，非 IV）**：

1. 任意 MO 已覆盖交易日，存在对应 IM 合约的 minute parquet，且 `quote_quality=ok` 占比可接受（IM 流动性通常优于深虚值 MO）。
2. `missing_file` 可 repair；repair 后 failures 清单可追溯。
3. 对任意 MO 合约行，可按 `contract_month` + `(trade_date, target_time)` 取到 **同码** IM 的 `micro_price`/`mid_price`。

### 6.5 风险与约束

1. **勿与 MO `build_windowed` 并行**：同账户 Tq FileLock；IM 下载排队在 MO 流水线之外时段。
2. **换月**：v1 按日指定合约，不在本 Agent 做连续主力复权价。
3. **指数现货 `SSE.000852`**：非本需求范围；若后续要现货盘口，单独立项。
4. **专业版 tick**：与 MO 相同，依赖 `get_tick_data_series` 权限。

### 6.6 待用户确认

- [x] **月份配对**：MO`YYMM` ↔ IM`YYMM`（如 2601 一组、2602 一组）；见 §6.3
- [x] **IM 存储形态**：独立 `futures/IM/` 按日单文件（见 storage demo）
- [ ] IM 全历史是否与 MO **同起止日**（`2022-07-22` 起）？
- [ ] MO P0 与 IM E4 **串行** 是否接受（先 MO 后 IM，或 MO 每完成 N 窗插一批 IM）？

---

## 5. 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06-01 | 初版：固化 Agent 台账；进度 9/141 窗；记录 07-22～10-19 质量补拉完成；标注第 8 窗 failures 待扫尾 |
| 2026-06-01 | 规则：`market-data-agent.mdc` 增加「以本文件为准、每任务后更新」强制条款 |
| 2026-06-01 | 启动 P1：第 8 窗 `2022-09-30`～`2022-10-09`，177 失败合约定向 `build_month`（`--no-skip-complete`） |
| 2026-06-01 | P1 完成：`saved_days=906`，`failed_symbols=12`（原 177）；报告 `MO_20220930_20221009_retry_summary.json` |
| 2026-06-01 | 用户确认 P0：启动 `build_windowed` 续跑（9/141 已完成，下一窗 `2022-10-20`～`2022-10-29`） |
| 2026-06-01 | 用户要求中断后重启 P0；监控 `full_history.log` + manifest |
| 2026-06-01 | 新需求：为可靠衍生数据增加 **IM 股指期货分钟盘口**；新增 §6 与阶段 E；扩展 Agent 使命（MO+IM 原始层） |
| 2026-06-01 | 确认配对规则：**MO2601↔IM2601**（按 `YYMM` 分组，非单日主力）；更新 storage demo §月份配对 |
| 2026-06-01 | 文档布局：`docs/` 仅 Agent 计划；架构/规则/IM demo 迁至 `docs_fix/` |
| 2026-06-01 | 蓝图 PDF 保留在 `docs/blueprints/` |
| 2026-06-01 | 用户要求停 P0；workers 4 vs 6 实测（36 合约×2 日）：4=196s/0 失败，6=188s/1 超时失败 → **仍建议 workers=4** |
| 2026-06-02 | 第 12 窗补拉：`2022-11-09`～`11-18` 余 3 合约（`window12_failures_symbols.txt`）→ **saved_days=24，failed_symbols=0** |
| 2026-06-01 | IM E1/E3：`option_platform/data/futures/` + `scripts/build_im_minute_quotes.py` + 单测 |
| 2026-06-02 | 用户「续下 MO」：`bash scripts/start_mo_download_with_watchdog.sh`；manifest **32/141** 完成，续跑 **第 33 窗** `2023-06-07`～`2023-06-16`；日志 `batch_10d/full_history.log` |
| 2026-06-02 | 用户关闭后台 Python：清理 `build_*` / `monitor_mo_download` 及 **5 组** 孤儿 `multiprocessing` worker（第 33 窗仍未完成） |
| 2026-06-02 | 用户「先补拉」：第 8 窗 12 合约 retry2 **saved_days=72，failed_symbols=0**；Step2 `missing_file` repair 已启动后用户嫌慢 |
| 2026-06-02 | 停 `repair_minute_quotes_from_plan`（`missing_file` 1284 行）；改 **按窗 failures 补拉** `repair_mo_failures_by_window.sh`（25 窗 / 日志 `repair_by_window.log`） |
| 2026-06-02 | 按窗 failures 补拉 **完成**：25/25 窗，`saved_days=2010`，**`failed_symbols=0`**（约 6.6 min）；无 `*_failures_retry_failures.csv` |
| 2026-06-02 | 新增 failures 台账同步：`sync_mo_window_failures.py` + `failure_records.py`；25 窗 active failures 归档为 `*.resolved.csv`（避免重复补拉） |
| 2026-06-02 | 用户续跑 P0：`start_mo_download_with_watchdog.sh`；manifest **32/141**，从第 **33** 窗 `2023-06-07`～`2023-06-16` 起 |
| 2026-06-02 | 看门狗：重启下载前 `pkill` 项目 venv 的 orphan `multiprocessing` worker（缓解多窗后降速） |
| 2026-06-02 | `option_platform/common/process_pool.py`：`build_month` / repair 进程池 SIGTERM 时 `shutdown(cancel_futures=True)`，减少 orphan worker 根因 |
| 2026-06-02 | 新增 `scripts/launch_mo_download_daemon.py`：用 `start_new_session=True` 完全脱离会话拉起 下载/看门狗/孤儿监控（macOS 无 `setsid`，旧 `nohup &` 会随 shell 退出被杀）；`--restart` 先清理旧进程与 orphan worker。`launch_mo_download_daemon.sh` 改为薄包装委托该脚本 |

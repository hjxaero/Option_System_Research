# 市场数据系统 Agent — 计划与进度

> **权威台账**：市场数据 Agent 的工作计划、执行进度、阻塞与下一步 **以本文件为准**。  
> 每完成一项任务（或一次可汇报的阶段）后 **必须更新** 本文件（含「最后更新」时间与变更记录）。  
> 范围：**仅** `data_store/quotes/minute/MO/` 分钟盘口原始层（不含快照 / IV / 曲面）。

最后更新：**2026-06-01**（P0 全历史续跑已启动，从第 10 窗）

---

## 1. 使命与边界

| 项 | 说明 |
|----|------|
| 交付物 | `quotes/minute/MO/{symbol}/{trade_date}.parquet` |
| 目标区间 | `2022-07-22` → `2026-05-30`（全历史，10 日分窗） |
| 编排 | `scripts/build_windowed_four_term_minute_quotes.py` + manifest |
| 不在范围 | 快照、IV/Greeks、曲面、策略/回测/实盘 |

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

- [ ] 全历史下载完成后，生成 **分钟层** 区间质量摘要（非快照 gate）
- [ ] 更新 `first_valid_dates.json` 全区间
- [ ] 向用户移交：manifest、failures 索引、已知流动性限制说明

---

## 3. 当前进度快照

| 指标 | 数值 |
|------|------|
| 分窗进度 | **9 / 141**（6.4%） |
| 日历覆盖（manifest 已完成） | **2022-07-22** ～ **2022-10-19** |
| 下一窗 | **第 10 窗**：`2022-10-20` ～ `2022-10-29` |
| 本地 parquet 文件数 | 约 **14,956** |
| 后台任务 | **P0 全历史下载中**（`build_windowed`，workers=4，从第 10 窗起） |

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

### 3.2 质量补拉（分钟层）

| 区间 | 状态 | 说明 |
|------|------|------|
| 2022-07-22～2022-10-19 | **已完成** | `repair` 5014 日写入；报告 `MO_20220722_20221019_after_repair_summary.json` |

### 3.3 已知风险 / 阻塞

1. **第 8 窗余 12 失败**：P1 后从 177 降至 12（多为 Tq 超时）；清单 `MO_20220930_20221009_retry_failures.csv`。  
2. **勿并行 download**：Tq FileLock；同时只跑一条流水线。  
3. **`workers=2`**：实测易锁冲突，续跑统一用 **4**。

---

## 4. 下一步（优先级）

| 优先级 | 动作 | 命令/入口 |
|--------|------|-----------|
| P0 | 续跑全历史（从第 10 窗） | `build_windowed_four_term_minute_quotes.py`（用户确认后后台） |
| P1 | ~~补第 8 窗 failures~~ | **已完成**（906 saved，12 仍失败） |
| P1b | 余 12 合约再试 | `window8_failures_symbols.txt` 子集或读 `*_retry_failures.csv` |
| P2 | 各窗 failures 扫尾 | 合并 `batch_10d/*_failures.csv` |
| P3 | 全历史完成后再做区间 repair | `generate_repair_plan` + `repair_minute_quotes_from_plan` |

续跑示例（**需用户确认后执行**）：

```bash
cd /Users/hjx_aero/Option_System_Research && source Normal/bin/activate
caffeinate -dims python scripts/build_windowed_four_term_minute_quotes.py \
  --start 2022-07-22 --end 2026-05-30 \
  --window-days 10 --workers 4 --min-workers 4 \
  --skip-complete --infer-first-valid \
  --first-valid-date-cache data_store/contracts/MO/first_valid_dates.json \
  2>&1 | tee -a data_store/quality/MO/batch_10d/full_history.log
```

---

## 5. 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06-01 | 初版：固化 Agent 台账；进度 9/141 窗；记录 07-22～10-19 质量补拉完成；标注第 8 窗 failures 待扫尾 |
| 2026-06-01 | 规则：`market-data-agent.mdc` 增加「以本文件为准、每任务后更新」强制条款 |
| 2026-06-01 | 启动 P1：第 8 窗 `2022-09-30`～`2022-10-09`，177 失败合约定向 `build_month`（`--no-skip-complete`） |
| 2026-06-01 | P1 完成：`saved_days=906`，`failed_symbols=12`（原 177）；报告 `MO_20220930_20221009_retry_summary.json` |
| 2026-06-01 | 用户确认 P0：启动 `build_windowed` 续跑（9/141 已完成，下一窗 `2022-10-20`～`2022-10-29`） |

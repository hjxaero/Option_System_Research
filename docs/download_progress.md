# MO 分钟盘口下载进度

最后更新：2026-05-28

## 工程能力（已实现）

| 脚本 | 用途 |
|------|------|
| `scripts/build_month_four_term_minute_quotes.py` | 四期限批量下载；`--workers N` 多进程；`--skip-complete` 续跑 |
| `scripts/report_minute_quote_quality.py` | 从本地 parquet 汇总质量 |
| `scripts/benchmark_tq_workers.py` | 压测不同 worker 数量 |
| `option_platform/data/live_update.py` | `should_skip_minute_quote_update`、按 symbol 续跑 |

`.cursor/rules/option-data-platform.mdc`：项目 Agent 规则。

## 性能结论（本机 + 当前账号）

- 瓶颈：`get_tick_data_series` 网络往返，非本地 pandas/parquet。
- **推荐 `--workers 4~6`**；超过 8 提速不明显。
- 天勤官方无固定「最大线程数」；文档称连接过多可能失败。实测 **1~20 进程均可连**，甜点约 **6 进程**。
- **5 个交易日（2026-01-12~16）全量四期限**：6 进程约 **9 分 39 秒**（1310 次新下 + 120 跳过）。

## 本地数据覆盖（`data_store/quotes/minute/MO/`）

总计约 **2113** 个 parquet，**286** 个合约目录。

| 交易日 | parquet 数 | 状态 |
|--------|------------|------|
| 2026-01-01 | 107 | 休市/无行情占位 |
| 2026-01-02 | 147 | 休市/无行情占位 |
| 2026-01-05 | 285 | 基本完成 |
| 2026-01-06 ~ 09 | 各 36 | 部分 |
| 2026-01-12 ~ 16 | 各 **286** | **已完成** |
| 2026-01-19 ~ 30 | — | **未下载** |

目标范围：**2026-01-05 ~ 2026-01-31**（20 个交易日，从 1/5 起有行情）。

## 质量（最近一次 5 日报告）

文件：`data_store/quality/MO/month_probe/MO_20260112_20260116_summary.json`

- `ok_ratio` ≈ 67%
- `missing_ratio` ≈ 18%
- 整月尚未跑完，**暂不做全月 quality gate**

## 续跑命令

```powershell
$env:TQ_USER = "你的账号"
$env:TQ_PASS = "你的密码"

# 确认无残留下载进程后再跑
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'build_month' }

E:\Normal_Venv\Scripts\python.exe -u scripts\build_month_four_term_minute_quotes.py `
  --start 2026-01-05 --end 2026-01-31 --workers 6

# 完成后
E:\Normal_Venv\Scripts\python.exe scripts\report_minute_quote_quality.py `
  --start 2026-01-05 --end 2026-01-31
E:\Normal_Venv\Scripts\python.exe scripts\check_quality_gate.py `
  "E:\Option_System_Research\data_store\quality\MO\month_probe\MO_20260105_20260131_summary.json"
```

## 下一步

1. 续跑整月分钟盘口至 1/19~1/30 齐全。
2. 全月 `check_quality_gate` 通过后，进入新口径四期限快照 / IV 管线。
3. 勿同时启动多个 `build_month_*` 任务（曾导致 18+ 进程卡顿）。

## 日志

- `data_store/quality/MO/month_probe/bench_5d_w6.log` — 5 日 6 进程实测
- `data_store/benchmark_workers/benchmark_results.json` — worker 压测

# IV Surface Engine — 计划与进度

> **权威台账**：波动率曲面 Agent（系统 3）的工作计划、执行进度、阻塞与下一步 **以本文件为准**。  
> 每完成一项任务（或一次可汇报的阶段）后 **必须更新** 本文件（含「最后更新」时间与变更记录）。  
> 范围：**仅** enriched 快照 → IV 曲面节点（`raw_iv` / `smooth_iv`）与曲面质量摘要（不含分钟下载、链 enrichment、策略/回测）。

最后更新：**2026-06-01**（规则与台账配置完成；v0 实现未开始）

规则：`.cursor/rules/iv-surface-agent.mdc`  
字段与质量标签：`docs/project_rules.md`、`option_platform/data/contracts.py`（`IvSurfaceSchema`）

---

## 1. 使命与边界

| 项 | 说明 |
|----|------|
| 系统编号 | **系统 3** — IV Surface Engine |
| 上游（系统 2） | `data_store/snapshots/four_term_enriched/{PRODUCT}/{trade_date}.parquet` |
| 交付物 | `data_store/surfaces/iv_nodes/{PRODUCT}/{trade_date}.parquet` |
| 质量摘要 | `data_store/quality/iv_surface/{PRODUCT}/{trade_date}.json` |
| 首品种 | **MO**（与平台一致） |
| 不在范围 | Tq 下载、四期限选约、raw IV 求解、链 `OptionChain` 语义、策略/风控/执行 |

核心原则（与 `project_rules.md` 一致）：

1. 曲面从快照派生，不覆盖 enriched 快照。  
2. 保留 `raw_iv` 与 `smooth_iv` 两列；质量标签优先于完整度。  
3. v0 仅期限内透明处理（排序、outlier、call/put 对照、线性插值）。  
4. 不跨到期插值；不对无锚点深端外推。

---

## 2. 总体计划

### 阶段 A — 配置与契约（进行中）

- [x] Agent 规则：`.cursor/rules/iv-surface-agent.mdc`
- [x] 计划与进度台账：本文件
- [x] 系统边界：本文件与 `.cursor/rules/iv-surface-agent.mdc` 定义 `iv_surface` 范围
- [x] 总规则 Agent 分工：`option-data-platform.mdc`
- [x] `configs/data_catalog.json` 登记曲面路径（`iv_surface_nodes` / `iv_surface_quality`）
- [ ] `IvSurfaceSchema` 增加 `surface_method`（实现 v0 时同步）

### 阶段 B — Transparent Surface v0（未开始）

- [ ] 完善 `build_raw_surface_nodes`（`forward` / `futures_price` / `underlying_price` 兼容）
- [ ] 实现 `build_iv_surface`（锚点门控 + 期限内线性插值 + 标签）
- [ ] 异常尖刺剔除（`outlier`）
- [ ] 同 strike call/put IV 偏离（`call_put_mismatch`）
- [ ] `summarize_iv_surface_quality` → 写 `quality/iv_surface/*.json`
- [ ] CLI：`scripts/build_iv_surface_nodes.py`
- [ ] CLI：`scripts/check_iv_surface_quality.py`
- [ ] 扩展 `tests/test_iv_surface.py`（插值、禁止跨到期、excluded）

### 阶段 C — 首日验收（未开始）

- [ ] 选取 1 个已有 `four_term_enriched` 的 `trade_date` 跑通全日
- [ ] 人工抽查：ATM 附近 raw vs smooth、插值标签、深虚值空洞
- [ ] 记录覆盖率基线（**不以 100% 为目标**）

### 阶段 D — Research Surface Views（未开始）

- [ ] 按 `log_moneyness` / `delta` / `expiry` 的读取辅助函数或脚本
- [ ] raw vs smooth 稳定性对比（研究用手动脚本）

### 阶段 E — 下游对接（未开始）

- [ ] Strategy / Backtest 约定：只读 `iv_nodes` + 质量过滤
- [ ] 固定曲面版本与生成参数（可复现）
- [ ] Phase 3+：评估 SVI/SSVI（**不替代** raw/smooth 节点表）

---

## 3. 当前进度快照

| 指标 | 状态 |
|------|------|
| Agent 规则 | **已配置** |
| 进度台账 | **已配置**（本文件） |
| `build_raw_surface_nodes` | **已有**（仅投影，`smooth_iv` 恒为空） |
| `build_iv_surface` / v0 平滑 | **未开始** |
| 曲面 parquet 落盘 | **未开始** |
| 质量摘要 JSON | **未开始** |
| CLI | **未开始** |
| 单元测试 | **仅基础投影**（`tests/test_iv_surface.py`） |
| 上游 enriched 数据 | **依赖系统 2**；全历史 enriched 未作为本阶段阻塞项登记 |

### 3.1 代码与文档索引

```text
option_platform/data/iv_surface.py    # 当前仅 build_raw_surface_nodes
option_platform/data/contracts.py     # IvSurfaceSchema
tests/test_iv_surface.py
docs/project_rules.md                 # IV/曲面质量硬约束
docs/option_chain_snapshot_plan.md    # enriched 输入列
option_platform/pricing/              # Black-76 定价（系统 2 enrichment 复用）
```

### 3.2 存储约定（目标路径）

与 `configs/data_catalog.json` 对齐（实现落盘时强制使用）：

```text
data_store/surfaces/iv_nodes/{PRODUCT}/{trade_date}.parquet
data_store/quality/iv_surface/{PRODUCT}/{trade_date}.json
```

写入规范：先写临时文件再原子替换；与系统 1 分钟层相同幂等纪律。

### 3.3 已知风险 / 依赖

1. **系统 2 未 enriched 的交易日**：系统 3 无法产出曲面；应报缺失清单而非回退读 `quotes/minute/`。  
2. **列名迁移**：`forward` vs `futures_price` 需输入兼容。  
3. **流动性**：深虚值/远月长期无有效 `iv_quality=ok`，曲面天然稀疏，验收看 **标签正确性** 而非覆盖率 100%。  
4. **v0 插值**：只补同期限中间缺口，不补两端无锚点区域。

---

## 4. 下一步（优先级）

| 优先级 | 动作 | 入口 / 备注 |
|--------|------|----------------|
| P0 | 实现 `build_iv_surface` + 质量标签 | `option_platform/data/iv_surface.py` |
| P0 | 补充单元测试（插值、跨到期禁止、excluded） | `tests/test_iv_surface.py` |
| P1 | 单日 CLI + 质量摘要 JSON | `scripts/build_iv_surface_nodes.py` |
| P1 | 登记 `data_catalog.json` 曲面路径 | `configs/data_catalog.json` |
| P2 | 选 1 日 enriched 试跑 + 人工检查 | 需系统 2 已有该日 `four_term_enriched` |
| P3 | Research 读取视图 / 可视化脚本 | 阶段 D |

验收标准（阶段 B 完成时）：

- `pytest tests/test_iv_surface.py` 通过；无锚点时不产生伪 `smooth_iv`。  
- 插值行 `surface_quality=interpolated`（或等价）且 `surface_method=linear_interp`。  
- 质量摘要含：有效节点、剔除、插值、outlier、call_put_mismatch 计数。  
- 同一输入可复现输出 parquet。

---

## 5. 变更记录

| 日期 | 摘要 |
|------|------|
| 2026-06-01 | 创建系统 3 规则与计划文档初稿。 |
| 2026-06-01 | **配置完成**：对齐系统 1·2 Agent 风格；结构化台账（阶段 A–E、进度快照、下一步）；规则中明确交付路径、默认工作流与强制更新纪律。 |
| 2026-06-01 | `data_catalog.json` 增加 `four_term_enriched`、`iv_surface_nodes`、`iv_surface_quality`；`data_platform.md` / 三系统 Agent 规则交叉引用。 |

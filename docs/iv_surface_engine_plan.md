# IV Surface Engine — 机构级建设计划与进度

> **权威台账**：波动率曲面 Agent（系统 3）的职责、路线图、执行进度、阻塞与下一步以本文件为准。  
> 每完成一项任务或一个可汇报阶段后，必须更新「最后更新」「当前进度」「变更记录」。  
> 范围：只负责 enriched option-chain snapshot → IV 曲面节点、平滑曲面、质量摘要、研究/风控可消费视图；不负责分钟下载、四期限选约、raw IV 求解、策略下单。

最后更新：**2026-06-01**（升级为机构级建设计划；实现仍未开始）  

规则：`.cursor/rules/iv-surface-agent.mdc`  
字段与质量标签：`docs_fix/project_rules.md`、`docs/iv_surface_pipeline.md`（若存在）、`option_platform/data/contracts.py`

---

## 1. 战略定位

系统 3 是期权平台的 **波动率状态引擎**。它不是简单画一张 IV 曲面，而是把分散、嘈杂、带流动性缺口的期权报价，转化为可研究、可回测、可监控、可风控的波动率状态。

顶级私募机构通常不会把 IV 曲面当成一个孤立模型，而会把它建设成一条完整生产线：

```text
enriched option-chain snapshot
  -> raw IV nodes
  -> quality gate
  -> arbitrage / consistency checks
  -> transparent smoothing
  -> model surface
  -> surface diagnostics
  -> research features / risk scenarios / strategy inputs
```

本项目第一阶段坚持一个原则：**宁愿曲面有洞，也不把脏数据平滑成看似合理的交易信号**。

## 2. 系统边界

| 项 | 说明 |
|----|------|
| 系统编号 | 系统 3 — IV Surface Engine |
| 上游 | 系统 2 enriched option-chain snapshot |
| 首品种 | MO（中证1000股指期权） |
| 核心输出 | `raw_iv` / `smooth_iv` 曲面节点、质量摘要、研究视图 |
| 目标消费者 | Research、Strategy、Backtest、Risk、Monitoring |
| 不在范围 | Tq 下载、分钟修复、四期限选约、raw IV 求解、下单执行 |

标准输入：

```text
data_store/snapshots/four_term_enriched/{PRODUCT}/{trade_date}.parquet
```

标准输出：

```text
data_store/surfaces/iv_nodes/{PRODUCT}/{trade_date}.parquet
data_store/quality/iv_surface/{PRODUCT}/{trade_date}.json
```

依赖纪律：

1. 系统 3 只读系统 2 的 enriched snapshot，不直接读 `quotes/minute/`。
2. 系统 3 不重算 raw IV / Greeks；原始数学求解属于 Pricing / Greeks。
3. 系统 3 不覆盖上游快照；所有结果另存为派生层。
4. 所有平滑、插值、剔除都必须可解释、可复现、可审计。

## 3. 目标状态

### 3.1 生产级能力

系统 3 最终应具备：

- 单日、区间、增量三种生成模式。
- raw node、smooth node、model params、quality summary 分层落盘。
- 完整质量标签：无价格、低流动性、过期、异常尖刺、call/put mismatch、插值、外推、套利约束失败。
- 研究与生产共用同一套曲面版本，避免 notebook 里另起炉灶。
- 同一输入、同一参数、同一代码版本可复现输出。
- 支持回测按历史时间点读取当时可用曲面，不能使用未来信息。

### 3.2 机构级目标

长期目标不是只生成一个 `smooth_iv`，而是形成四层资产：

| 层 | 目标 |
|----|------|
| Raw Layer | 保存原始 IV 节点和所有质量标签 |
| Clean Layer | 过滤可用锚点，标记剔除原因 |
| Smooth Layer | 透明平滑、插值和缺口保留 |
| Model Layer | SVI / SSVI 等参数化曲面，带拟合误差和约束检查 |

下游默认消费 Smooth Layer；研究和风控可按需要消费 Raw / Clean / Model Layer。

## 4. 数据契约

### 4.1 输入字段

| 字段 | 必需 | 说明 |
| --- | --- | --- |
| `timestamp` | 是 | 标准分钟时间点 |
| `expiry_date` | 是 | 到期日 |
| `term_role` | 是 | 四期限角色 |
| `strike_price` | 是 | 行权价 |
| `option_type` | 是 | `call` / `put` |
| `iv` | 是 | 原始反解 IV |
| `iv_quality` | 是 | 原始 IV 质量标签 |
| `t_years` | 是 | 交易分钟口径到期时间 |
| `forward` | 推荐 | 首选 moneyness 输入 |
| `futures_price` | 兼容 | `forward` 缺失时使用 |
| `underlying_price` | 兼容 | 最后兜底，不作为最优 forward |
| `delta` | 推荐 | delta 曲面与质量检查 |
| `quote_quality` | 推荐 | 报价质量联动过滤 |
| `spread_bps` | 推荐 | 流动性与开盘异常识别 |
| `volume` / `open_interest` | 推荐 | 低流动性标签 |

### 4.2 输出字段

| 字段 | 说明 |
| --- | --- |
| `timestamp` | 标准分钟时间点 |
| `expiry_date` | 到期日 |
| `term_role` | 四期限角色 |
| `strike_price` | 行权价 |
| `option_type` | `call` / `put` |
| `moneyness` | `strike_price / forward` |
| `log_moneyness` | `ln(moneyness)` |
| `delta` | 期权 delta |
| `t_years` | 年化到期时间 |
| `raw_iv` | 原始反解 IV |
| `smooth_iv` | 平滑/插值后 IV |
| `iv_quality` | 原始 IV 质量标签 |
| `surface_quality` | 曲面质量标签 |
| `surface_method` | `raw`、`linear_interp`、`svi_fit`、`excluded` 等 |
| `surface_version` | 曲面生成版本 |
| `fit_error` | 模型层拟合误差，v0 可为空 |
| `exclusion_reason` | 剔除原因 |

## 5. 质量体系

### 5.1 节点质量分层

| 等级 | 说明 | 默认用途 |
| --- | --- | --- |
| `anchor` | 可作为拟合锚点的高质量 raw IV | 平滑与模型拟合 |
| `usable_degraded` | 可研究但不默认拟合，如 wide spread | 人工分析、降权拟合 |
| `excluded` | 保留但不参与拟合 | 审计、缺口分析 |
| `interpolated` | 期限内插值得到 | 下游可用但必须带标签 |
| `outlier` | 异常尖刺或一致性失败 | 不参与默认消费 |

### 5.2 必做检查

P0 检查：

- `raw_iv` 有限且大于 0。
- `t_years` 有限且大于 0。
- `moneyness` / `log_moneyness` 有限。
- `iv_quality=ok` 才能默认作为 anchor。
- 同一 `timestamp × expiry × option_type` 内不跨期限插值。
- 两端无锚点时不外推。

P1 检查：

- 同 strike call/put IV 偏离。
- 同期限相邻 strike 尖刺。
- 开盘宽价差导致的曲面突变。
- 前后分钟曲面跳变。
- ATM 附近覆盖率。

P2 检查：

- 垂直价差单调性。
- 蝶式套利 / convexity 近似检查。
- calendar arbitrage 检查。
- total variance 随期限非下降检查。
- 模型拟合残差稳定性。

## 6. 建模路线

### 6.1 Transparent Surface v0

目标：先得到可信、透明、不会污染研究的曲面节点。

处理流程：

```text
project raw nodes
  -> select anchors
  -> mark exclusions
  -> detect outliers
  -> same-expiry linear interpolation
  -> summarize quality
```

规则：

- 只在同一到期、同一 option_type 内插值。
- 插值必须两侧都有 anchor。
- `smooth_iv` 不覆盖 `raw_iv`。
- 所有插值节点标记 `surface_quality=interpolated`。
- 无锚点区域保留空洞。

### 6.2 Clean Smile v1

目标：得到稳定的到期内 smile。

能力：

- moneyness / log-moneyness 网格标准化。
- ATM 附近优先锚点。
- 异常尖刺剔除与邻域修复。
- call/put 合并规则：优先 OTM 侧，ATM 附近做一致性校验。
- 基于 quote quality / spread / liquidity 的权重。

### 6.3 Parametric Surface v2

目标：为研究、风控和 scenario 提供更平滑的参数化曲面。

候选模型：

- SVI：单期限 smile 参数化。
- SSVI：跨期限一致性更强。
- Total variance interpolation：以总方差而非 IV 直接插值。
- Delta surface：便于策略按 delta 选腿。

原则：

- 参数化结果不能替代 raw/smooth 节点表。
- 每次拟合必须保存参数、输入锚点数量、残差、失败原因。
- 模型层必须有 no-arbitrage 诊断，失败时降级到 Smooth Layer。

### 6.4 Real-Time Surface v3

目标：盘中分钟级更新，服务监控、风险和策略扫描。

能力：

- 只更新当前交易日、当前分钟后的增量结果。
- 支持前一曲面 warm start。
- 开盘/收盘特殊质量规则。
- 曲面跳变报警。
- 回滚到最近稳定曲面。

## 7. 存储与版本

建议目录：

```text
data_store/
  surfaces/
    iv_nodes/{PRODUCT}/{trade_date}.parquet
    iv_params/{PRODUCT}/{trade_date}.parquet
    iv_grids/{PRODUCT}/{trade_date}.parquet
  quality/
    iv_surface/{PRODUCT}/{trade_date}.json
```

版本字段：

- `surface_version`
- `input_snapshot_version`
- `model_family`
- `model_params_hash`
- `generated_at`
- `code_version`（后续可接 git commit）

写入纪律：

1. 先写临时文件，再原子替换。
2. 同一输入重复生成必须幂等。
3. 参数变化必须体现在 `surface_version` 或质量摘要中。
4. 回测固定读取历史已生成版本，不使用未来重算版本。

## 8. 质量摘要

每日质量 JSON 至少包含：

```text
product
trade_date
surface_version
input_path
output_path
timestamps
total_nodes
anchor_nodes
excluded_nodes
interpolated_nodes
outlier_nodes
call_put_mismatch_nodes
atm_coverage_ratio
front_expiry_anchor_ratio
median_fit_error
max_fit_error
warnings
generated_at
```

分组维度：

- 全日。
- 每个 `timestamp`。
- 每个 `expiry_date`。
- current month / next month / current quarter / next quarter。
- ATM 附近 bucket。

## 9. 监控与报警

P0 报警：

- 输入 enriched snapshot 缺失。
- 必备字段缺失。
- 全日 anchor 数过低。
- front expiry ATM 覆盖缺失。
- 生成文件为空。

P1 报警：

- 某期限 anchor ratio 低于阈值。
- 同 strike call/put mismatch 超阈值。
- 曲面相邻分钟跳变过大。
- 开盘宽价差导致拟合失败。

P2 报警：

- calendar arbitrage 频繁出现。
- 模型拟合残差持续变大。
- 策略常用 delta bucket 无可用节点。

## 10. 研究闭环

研究层不应该直接绕过系统 3 自己清洗 IV。所有研究特征应从曲面资产派生：

- ATM IV。
- 25D / 10D skew。
- Term structure slope。
- Front vs next expiry spread。
- Smile curvature。
- Realized vs implied vol spread。
- Surface shock features。
- IV rank / percentile。
- Intraday surface jump。

研究输出应反哺系统 3：

- 哪些质量标签对策略 PnL 影响最大。
- 哪些期限/strike 区域最容易污染信号。
- 哪些模型误差会导致回测偏差。
- 哪些曲面特征应进入风险监控。

## 11. 风控接口

风控使用曲面时必须知道曲面质量。

P0 输出：

- `smooth_iv` 节点。
- ATM IV。
- expiry-level quality score。
- 可用/不可用标签。

P1 输出：

- Delta bucket IV。
- Term structure。
- Smile skew / curvature。
- Surface shock scenarios。

P2 输出：

- Vol stress grid。
- Scenario PnL 所需的曲面 bump。
- Vanna / Volga 近似输入。
- 曲面异常时的风控降级信号。

## 12. 工程实现计划

### Phase A — 配置与契约

- [x] Agent 规则：`.cursor/rules/iv-surface-agent.mdc`
- [x] 计划与进度台账：本文件
- [x] 系统边界：`docs/system_architecture.md`
- [x] 总规则 Agent 分工：`.cursor/rules/option-data-platform.mdc`
- [x] `configs/data_catalog.json` 登记曲面路径
- [ ] `IvSurfaceSchema` 增加 `surface_method`、`surface_version`、`exclusion_reason`

### Phase B — Transparent Surface v0

- [ ] 完善 `build_raw_surface_nodes`
- [ ] 实现 `build_iv_surface`
- [ ] 实现 anchor selection
- [ ] 实现 `surface_excluded`
- [ ] 实现同期限线性插值
- [ ] 实现 outlier 标记
- [ ] 实现 call/put mismatch 标记
- [ ] 实现 `summarize_iv_surface_quality`
- [ ] 扩展 `tests/test_iv_surface.py`

### Phase C — 单日生产闭环

- [ ] CLI：`scripts/build_iv_surface_nodes.py`
- [ ] CLI：`scripts/check_iv_surface_quality.py`
- [ ] 选一个已有 enriched 的交易日跑通。
- [ ] 保存 parquet 与质量 JSON。
- [ ] 人工检查 ATM 附近 raw vs smooth。
- [ ] 记录第一版质量基线。

### Phase D — 月度批处理

- [ ] 支持日期区间批处理。
- [ ] 支持 `--skip-complete`。
- [ ] 支持失败清单。
- [ ] 汇总月度质量报告。
- [ ] 与系统 2 enriched 月度结果对齐。

### Phase E — Research Views

- [ ] 增加 `load_surface_nodes`。
- [ ] 增加 ATM IV 读取。
- [ ] 增加 delta bucket 读取。
- [ ] 增加 skew / term structure 特征。
- [ ] 增加可视化检查脚本。

### Phase F — Clean Smile v1

- [ ] OTM 优先合并 call/put。
- [ ] 权重体系：spread、quote age、volume、OI、ATM distance。
- [ ] 更稳健的 outlier 检测。
- [ ] 标准 log-moneyness 网格。
- [ ] 平滑参数保存。

### Phase G — Parametric Surface v2

- [ ] SVI 单期限拟合实验。
- [ ] SSVI / total variance 跨期限实验。
- [ ] 拟合残差与 no-arbitrage 诊断。
- [ ] 模型失败降级策略。
- [ ] 参数表 `iv_params` 落盘。

### Phase H — Production Monitoring

- [ ] 质量日报。
- [ ] 曲面跳变监控。
- [ ] anchor coverage 监控。
- [ ] 下游策略常用 bucket 覆盖监控。
- [ ] 异常曲面降级规则。

## 13. 测试矩阵

单元测试：

- 空 DataFrame 返回标准列。
- 缺必备字段报错。
- `forward` / `futures_price` / `underlying_price` 优先级。
- `moneyness` 非法时置空。
- `iv_quality != ok` 不作为 anchor。
- 同期限中间缺口插值。
- 不跨到期插值。
- 不对两端无锚点外推。
- outlier 标记。
- call/put mismatch 标记。
- 质量摘要计数。

集成测试：

- 单日 enriched snapshot → surface parquet。
- 质量 JSON 字段完整。
- 重复生成幂等。
- 缺输入文件时输出清晰错误。

回归测试：

- 固定小样本曲面输出稳定。
- 关键标签不被误改。
- 后续模型升级不破坏 v0 raw/smooth 契约。

## 14. 验收标准

Phase B 验收：

- `pytest tests/test_iv_surface.py` 通过。
- 无有效锚点时不产生伪 `smooth_iv`。
- 插值节点有明确 `surface_quality` 与 `surface_method`。
- 质量摘要能解释每个剔除/插值/异常节点数量。

Phase C 验收：

- 单日 MO 曲面文件可生成。
- 输出 parquet 可被下游稳定读取。
- 质量 JSON 能说明 front expiry、ATM 附近和全链覆盖。
- 人工抽查 raw vs smooth 没有明显污染。

Phase D 验收：

- 月度批处理可续跑。
- 失败清单可复现。
- 月度质量报告能区分数据缺口、流动性缺口、模型失败。

Phase G 验收：

- 参数化模型有残差、约束、失败降级。
- 参数化结果不覆盖 raw/smooth 节点表。
- 回测可锁定曲面版本。

## 15. 当前进度

| 指标 | 状态 |
|------|------|
| Agent 规则 | 已配置 |
| 权威计划 | 已配置，本文件 |
| `build_raw_surface_nodes` | 已有基础投影 |
| v0 平滑/插值 | 未开始 |
| 曲面 parquet 落盘 | 未开始 |
| 质量摘要 JSON | 未开始 |
| CLI | 未开始 |
| 单元测试 | 仅基础投影 |

当前代码索引：

```text
option_platform/data/iv_surface.py
option_platform/data/contracts.py
tests/test_iv_surface.py
docs/iv_surface_pipeline.md
docs_fix/project_rules.md
```

当前风险：

1. enriched snapshot 的 `forward` / `futures_price` 字段存在迁移差异，需要兼容。
2. 深虚值、远月、低流动性节点天然缺 IV，验收不能追求 100% 覆盖。
3. v0 插值只能补中间缺口，不能补两端无锚点区域。
4. 参数化模型必须等 raw/smooth 节点质量稳定后再引入。

近期优先级：

| 优先级 | 动作 | 入口 |
|--------|------|------|
| P0 | 实现 `build_iv_surface` | `option_platform/data/iv_surface.py` |
| P0 | 扩展曲面测试 | `tests/test_iv_surface.py` |
| P0 | 增加 `surface_method` / `exclusion_reason` 契约 | `option_platform/data/contracts.py` |
| P1 | 单日 CLI | `scripts/build_iv_surface_nodes.py` |
| P1 | 质量摘要 JSON | `option_platform/data/iv_surface.py` |
| P2 | 单日真实 enriched 检查 | 依赖系统 2 输出 |

## 16. 变更记录

| 日期 | 摘要 |
|------|------|
| 2026-06-01 | 创建系统 3 规则与计划文档初稿。 |
| 2026-06-01 | 配置完成：对齐系统 1/2 Agent 风格；明确交付路径、默认工作流与强制更新纪律。 |
| 2026-06-01 | `data_catalog.json` 增加 `four_term_enriched`、`iv_surface_nodes`、`iv_surface_quality`；`data_platform.md` / 三系统 Agent 规则交叉引用。 |
| 2026-06-01 | 升级为机构级建设计划：补充目标状态、质量体系、建模路线、存储版本、监控报警、研究闭环、风控接口、工程阶段、测试矩阵和验收标准。 |

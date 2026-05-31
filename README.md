# Option System Research

期权量化系统的数据中台工作区。

第一阶段目标：

- 建立统一的数据契约和存储目录
- 接入天勤数据源
- 生成期权分钟级快照
- 标准化 IV、Greeks、保证金、质量检查
- 为后续回测、实盘、风控共用同一份数据底座

详见 [数据中台设计](docs/data_platform.md)。

旧项目规则提炼见 [旧规则概况](docs/legacy_rules_summary.md)，当前项目规则见 [项目规则](docs/project_rules.md)。

期权快照清洗与 IV 曲面设计见 [IV 曲面管线](docs/iv_surface_pipeline.md)。

MO 分钟盘口下载进度见 [download_progress.md](docs/download_progress.md)。

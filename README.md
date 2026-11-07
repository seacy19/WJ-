# WJ策略

WJ 策略研究仓库：策略文档、筛选/回测/审计脚本、历史研究快照，以及年度妖股扫描模块。

## 目录导航

```
├── docs/            策略文档（权威版本）
│   └── archive/     历史版本与草稿（v1.4 草稿/红标、整合版、复原稿）
├── scripts/         全部脚本
│   ├── backtest/    回测主流程（backtest_wj_strategy.py 及云端/5分钟线回填）
│   ├── screening/   盘前/盘中筛选（按日期归档的快照脚本）
│   ├── audit/       复盘审计、行情与财务探测
│   ├── docs_build/  策略文档构建与抽取
│   ├── mcp/         行情 MCP 配置与连通性测试
│   └── research/    其他研究（ww_qlib 等）
├── results/         历史研究快照
│   ├── screens/     各期筛选结果（JSON/CSV/MD）
│   ├── audit/       各期审计与探测输出
│   └── archive/     大体量历史材料（长文信号、渲染 PDF）
├── yaogu/           年度妖股扫描模块
│   └── 2026/        2026 年妖股全扫描（数据+脚本+交付 Excel，见子目录 README）
├── wj_backtest_results*/  各版回测汇总（交易明细、信号、净值曲线）
├── ww_research_results/   ww 研究产物
└── mcp_servers/     行情 MCP 服务源代码
```

## 当前权威策略版本

- [WJ补涨策略 v2：数值化新版规则](docs/WJ补涨策略_v2_数值化规则_2026-11-07.md)：当前补涨分支规则；十年完整回测尚未验证。
- [WJ策略 v1.4 EXPMA 整合正式版](docs/WJ策略_v1.4_EXPMA整合正式版.md)：其余策略分支及 EXPMA 说明；同名 DOCX 为排版版本。**补涨分支与 v2 冲突时以 v2 为准。**
- [WJ情绪龙头策略_独立完整版](docs/WJ情绪龙头策略_独立完整版.md)：情绪龙头分支。
- 历史版本（v1.4 草稿、红色标注版、2026-06-30 整合版等）已归档至 `docs/archive/`，仅供溯源。

## 脚本使用说明

- 回测主入口：`scripts/backtest/backtest_wj_strategy.py`（路径已适配仓库根目录，直接 `python scripts/backtest/backtest_wj_strategy.py` 即可；缓存写入 `wj_backtest_cache/`，结果写入 `wj_backtest_results/`）。
- `scripts/screening/`、`scripts/audit/` 下的脚本多为**按日期归档的历史快照**，记录当时研究过程，路径与数据快照对应，不建议直接复跑；新研究请基于回测主入口或最新筛选脚本改造。
- 各脚本开头的 TuShare 初始化段为项目约定写法，刻意保持逐字一致，不做抽取合并。

## 运行环境

核心脚本使用 Python、pandas、numpy 和 TuShare Pro；妖股扫描模块另需 openpyxl；行情 MCP 服务使用 `mcp` 等依赖。需要数据服务的脚本通过环境变量读取凭证（`TUSHARE_TOKEN` / `TUSHARE_PRO_TOKEN` / `IFIND_API_KEY`），不要把真实密钥写入仓库。

## 敏感信息

API 密钥、环境文件、本机缓存、数据库及渲染预览不纳入版本管理（见 `.gitignore`）。若发现历史文档或研究输出中存在个人信息或凭证，应在分享仓库前进一步审查。

# 2026 年 A 股妖股全扫描

统计区间：2026-01-01 至 2026-11-06，沪深京 A 股全市场 5578 只。沿用 2025 年名单口径：

- **筛选**：任意连续 5 个交易日累计涨幅 ≥50%（标准化口径：主板 ×1.0、创业板 ×0.5、科创板 ×0.5、北交所 ×1/3），或连续涨停 ≥6 天
- **剔除**：事件期间已 ST/*ST（baostock 逐日 isST + 名称核验）、上市不足 20 个交易日的新股一字板
- **结果**：177 个事件 / 167 只股票（主板 166、创业板 10、北交所 1）；双达标 37、纯涨幅 140

## 文件说明

| 文件 | 说明 |
|---|---|
| `2026年妖股名单_截至20261106.xlsx` | 最终交付：事件汇总（177 行）/ 逐日明细（476 行）/ 口径说明 |
| `compute.py` | 事件计算：读取 `data/kline*` 日线，输出 `data/events.csv` 与 `data/hits.csv` |
| `build_xlsx.py` | 由 events.csv + hits.csv + reasons*.py 生成 Excel |
| `download_bs.py` | baostock 后复权日线下载（单进程，含官方 isST 字段） |
| `download_xq.py` | 雪球前复权日线下载（需 Cookie） |
| `data/universe.json` | 全市场名单（新浪 hs_a，5578 只） |
| `data/events.csv` | 事件汇总源数据 |
| `data/hits.csv` | 逐日明细源数据 |
| `data/reasons.py` | A 档：连板事件逐只调研的上涨原因 |
| `data/reasons_b.py` | B 档：纯涨幅事件按月度主线批量归类 |

## 复现流程

1. `download_bs.py` / `download_xq.py` 下载日线到 `data/kline2/`、`data/kline3/`（北交所用新浪接口，原始数据体积约数百 MB，未纳入版本管理）
2. `python compute.py` 生成 events/hits
3. `python build_xlsx.py` 生成交付 Excel

注：腾讯 ifzq.gtimg.cn 行情接口 2026 年已封禁（501），baostock 不可并发登录（会被拉黑名单），详见 Excel「口径说明」表。

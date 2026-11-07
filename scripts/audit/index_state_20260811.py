import json
import os
from pathlib import Path

import pandas as pd
import tushare as ts


SECRET_FILE = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11"
    r"\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\.market_data_mcp_secrets.json"
)
secrets = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
pro = ts.pro_api(secrets.get("TUSHARE_TOKEN") or secrets.get("TUSHARE_PRO_TOKEN"))
END_DATE = os.environ.get("WJ_TRADE_DATE", "20260810")
codes = {
    "000001.SH": "上证指数",
    "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",
    "000300.SH": "沪深300",
}
rows = []
for code, name in codes.items():
    df = pro.index_daily(ts_code=code, start_date="20260101", end_date=END_DATE)
    df = df.sort_values("trade_date").copy()
    c = df["close"].astype(float)
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema50 = c.ewm(span=50, adjust=False).mean()
    rows.append({
        "code": code,
        "name": name,
        "date": df.iloc[-1]["trade_date"],
        "close": float(c.iloc[-1]),
        "pct": float(df.iloc[-1]["pct_chg"]),
        "ret5": (float(c.iloc[-1]) / float(c.iloc[-6]) - 1) * 100,
        "ret20": (float(c.iloc[-1]) / float(c.iloc[-21]) - 1) * 100,
        "ema12": float(ema12.iloc[-1]),
        "ema50": float(ema50.iloc[-1]),
        "ema12_above_50": bool(ema12.iloc[-1] > ema50.iloc[-1]),
    })
print(json.dumps(rows, ensure_ascii=False, indent=2))

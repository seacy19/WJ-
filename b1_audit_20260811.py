import json
import os
from pathlib import Path

import pandas as pd
import tushare as ts


SECRET_FILE = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11"
    r"\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\.market_data_mcp_secrets.json"
)
END_DATE = os.environ.get("WJ_TRADE_DATE", "20260810")
secrets = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
pro = ts.pro_api(secrets.get("TUSHARE_TOKEN") or secrets.get("TUSHARE_PRO_TOKEN"))
basic = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name,industry,market,list_date")
cal = pro.trade_cal(exchange="SSE", start_date="20260701", end_date=END_DATE, is_open="1", fields="cal_date")
dates = sorted(cal["cal_date"].tolist())[-16:]
frames = [
    pro.daily(trade_date=d, fields="ts_code,trade_date,close,pct_chg,amount")
    for d in dates
]
df = pd.concat(frames, ignore_index=True).merge(basic, on="ts_code", how="left")
df = df[~df["name"].fillna("").str.contains("ST")].copy()


def is_limit(code, pct):
    if code.startswith(("300", "301", "688")):
        return pct >= 19.5
    if code.startswith(("8", "9")):
        return pct >= 29.0
    return pct >= 9.5


rows = []
for code, g in df.groupby("ts_code"):
    g = g.sort_values("trade_date").reset_index(drop=True)
    if len(g) < 11 or g.iloc[-1]["trade_date"] != END_DATE:
        continue
    flags = [is_limit(code, float(x)) for x in g["pct_chg"]]
    streak = 0
    for flag in reversed(flags):
        if not flag:
            break
        streak += 1
    prior_streak = 0
    for flag in reversed(flags[:-1]):
        if not flag:
            break
        prior_streak += 1
    ret10 = (float(g.iloc[-1]["close"]) / float(g.iloc[-11]["close"]) - 1) * 100
    ret20 = None
    if len(g) >= 16:
        ret15 = (float(g.iloc[-1]["close"]) / float(g.iloc[-16]["close"]) - 1) * 100
    else:
        ret15 = None
    row = g.iloc[-1]
    if ret10 >= 40 or streak >= 3 or prior_streak >= 3:
        rows.append({
            "code": code,
            "name": row["name"],
            "industry": row["industry"],
            "close": float(row["close"]),
            "pct": float(row["pct_chg"]),
            "ret10": ret10,
            "ret15": ret15,
            "streak": streak,
            "prior_streak": prior_streak,
            "break_today": prior_streak > 0 and streak == 0,
            "b1_pass": ret10 >= 50 or streak >= 6 or prior_streak >= 6,
        })

rows.sort(key=lambda x: max(x["ret10"], x["streak"] * 10, x["prior_streak"] * 10), reverse=True)
Path(os.environ.get("WJ_OUTPUT", "b1_audit_20260811_output.json")).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(rows, ensure_ascii=False, indent=2))

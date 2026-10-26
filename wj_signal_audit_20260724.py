import json
import os
import sqlite3
from collections import defaultdict
from pathlib import Path

DB = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11"
    r"\019f51ce-cedd-79c2-a614-e0177210b81a\data\tushare_cache.sqlite"
)
END = "20260723"

with sqlite3.connect(DB) as conn:
    rows = conn.execute(
        "select params_json,rows_json from api_cache where api_name='daily' "
        "order by fetched_at desc"
    ).fetchall()
    basics_rows = conn.execute(
        "select rows_json from api_cache where api_name='daily_basic' "
        "and params_json like '%20260723%' order by fetched_at desc"
    ).fetchall()
    stock_rows = conn.execute(
        "select rows_json from api_cache where api_name='stock_basic' "
        "order by fetched_at desc"
    ).fetchall()

by_date = {}
for p, r in rows:
    params = json.loads(p)
    date = params.get("trade_date")
    data = json.loads(r)
    if (
        date
        and date <= END
        and date not in by_date
        and len(data) > 5000
        and data
        and "vol" in data[0]
    ):
        by_date[date] = data

dates = sorted(by_date)[-21:]
hist = defaultdict(list)
for date in dates:
    for row in by_date[date]:
        hist[row["ts_code"]].append(row)


def is_limit(row):
    code = row["ts_code"]
    pct = float(row["pct_chg"])
    if code.startswith(("300", "301", "688")):
        return pct >= 19.5
    if code.endswith(".BJ"):
        return pct >= 29.5
    return pct >= 9.5


leaders = []
for code, bars in hist.items():
    bars.sort(key=lambda x: x["trade_date"])
    if len(bars) < 11 or bars[-1]["trade_date"] != END:
        continue
    closes = [float(x["close"]) for x in bars]
    ret10 = (closes[-1] / closes[-11] - 1) * 100
    flags = [is_limit(x) for x in bars]
    prior_streak = 0
    for flag in reversed(flags[:-1]):
        if not flag:
            break
        prior_streak += 1
    current_streak = 0
    for flag in reversed(flags):
        if not flag:
            break
        current_streak += 1
    if ret10 >= 50 or current_streak >= 6 or prior_streak >= 6:
        leaders.append(
            {
                "code": code,
                "ret10": round(ret10, 2),
                "pct": bars[-1]["pct_chg"],
                "close": bars[-1]["close"],
                "prior_limit": flags[-2],
                "today_limit": flags[-1],
                "prior_streak": prior_streak,
                "current_streak": current_streak,
                "break_trigger": flags[-2] and not flags[-1],
            }
        )

leaders.sort(key=lambda x: (x["break_trigger"], x["ret10"]), reverse=True)

basics = {}
for (raw,) in basics_rows:
    for row in json.loads(raw):
        basics.setdefault(row["ts_code"], row)
stocks = {}
for (raw,) in stock_rows:
    for row in json.loads(raw):
        stocks.setdefault(row["ts_code"], row)
target_industry = stocks.get("001258.SZ", {}).get("industry")
same_line = []
for code, bars in hist.items():
    bars.sort(key=lambda x: x["trade_date"])
    if len(bars) < 21 or bars[-1]["trade_date"] != END:
        continue
    if stocks.get(code, {}).get("industry") != target_industry:
        continue
    closes = [float(x["close"]) for x in bars]
    vols = [float(x["vol"]) for x in bars]
    ret20 = (closes[-1] / closes[-21] - 1) * 100
    vol_mult = vols[-1] / (sum(vols[-6:-1]) / 5)
    basic = basics.get(code, {})
    if ret20 <= 20 and vol_mult >= 1.2 and float(bars[-1]["amount"]) >= 100000:
        same_line.append(
            {
                "code": code,
                "close": closes[-1],
                "pct": bars[-1]["pct_chg"],
                "ret20": round(ret20, 2),
                "vol_mult": round(vol_mult, 2),
                "mv_yi": round(float(basic.get("total_mv") or 0) / 10000, 2),
                "turn": basic.get("turnover_rate"),
            }
        )
same_line.sort(key=lambda x: x["vol_mult"], reverse=True)
print(
    json.dumps(
        {"dates": dates, "leaders": leaders, "same_line": same_line},
        ensure_ascii=False,
        indent=2,
    )
)

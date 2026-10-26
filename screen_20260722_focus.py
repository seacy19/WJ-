import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import tushare as ts


DB = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11"
    r"\019f51ce-cedd-79c2-a614-e0177210b81a\data\tushare_cache.sqlite"
)
END_DATE = os.environ.get("WJ_END_DATE", "20260722")
FETCH_LATEST = os.environ.get("WJ_FETCH_LATEST") == "1"
SECRET_FILE = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11"
    r"\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\.market_data_mcp_secrets.json"
)


def latest_rows(conn, api_name, predicate):
    rows = conn.execute(
        "SELECT params_json, rows_json FROM api_cache WHERE api_name=? ORDER BY fetched_at DESC",
        (api_name,),
    ).fetchall()
    for params_json, rows_json in rows:
        params = json.loads(params_json)
        if not predicate(params):
            continue
        yield params, json.loads(rows_json)


def limit_up(row, name):
    pct = float(row.get("pct_chg") or 0)
    code = row["ts_code"]
    if "ST" in (name or "").upper():
        return pct >= 4.8
    if code.startswith(("300", "301", "688")):
        return pct >= 19.5
    if code.endswith(".BJ"):
        return pct >= 29.5
    return pct >= 9.5


with sqlite3.connect(DB) as conn:
    by_date = {}
    for params, rows in latest_rows(
        conn, "daily", lambda p: bool(p.get("trade_date")) and p["trade_date"] <= END_DATE
    ):
        date = params["trade_date"]
        if date not in by_date and len(rows) > 5000 and rows and "vol" in rows[0]:
            by_date[date] = rows
    basics = {}
    for params, rows in latest_rows(
        conn, "daily_basic", lambda p: p.get("trade_date") == END_DATE
    ):
        for row in rows:
            basics.setdefault(row["ts_code"], row)

    stocks = {}
    for _, rows in latest_rows(conn, "stock_basic", lambda p: True):
        for row in rows:
            stocks.setdefault(row["ts_code"], row)
        if stocks:
            break

if FETCH_LATEST:
    secrets = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
    token = secrets.get("TUSHARE_TOKEN") or secrets.get("TUSHARE_PRO_TOKEN")
    if not token:
        raise RuntimeError("TuShare token not found")
    pro = ts.pro_api(token)
    start_date = (datetime.strptime(END_DATE, "%Y%m%d") - timedelta(days=45)).strftime("%Y%m%d")
    trade_dates = pro.trade_cal(
        exchange="",
        is_open="1",
        start_date=start_date,
        end_date=END_DATE,
        fields="cal_date,is_open",
    )["cal_date"].astype(str).sort_values().tail(21).tolist()
    for trade_date in trade_dates:
        if trade_date not in by_date:
            by_date[trade_date] = pro.daily(trade_date=trade_date).to_dict("records")
    if not basics:
        basics = {
            row["ts_code"]: row
            for row in pro.daily_basic(trade_date=END_DATE).to_dict("records")
        }
    stocks = {
        row["ts_code"]: row
        for row in pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,area,industry,market,list_date",
        ).to_dict("records")
    }

dates = sorted(by_date)[-21:]

histories = defaultdict(list)
for date in dates:
    for row in by_date[date]:
        histories[row["ts_code"]].append(row)

items = []
for code, hist in histories.items():
    hist.sort(key=lambda x: x["trade_date"])
    if hist[-1]["trade_date"] != END_DATE:
        continue
    if len(hist) < 21:
        continue
    meta = stocks.get(code, {})
    name = meta.get("name", "")
    if "ST" in name.upper() or "退" in name:
        continue
    basic = basics.get(code, {})
    closes = [float(x["close"]) for x in hist]
    vols = [float(x["vol"]) for x in hist]
    today = hist[-1]
    row = {
        "code": code,
        "name": name,
        "industry": meta.get("industry"),
        "close": float(today["close"]),
        "pct": float(today["pct_chg"]),
        "amount": float(today["amount"]) / 100000,
        "turn": basic.get("turnover_rate"),
        "vr": basic.get("volume_ratio"),
        "mv": (basic.get("total_mv") or 0) / 10000,
        "pe": basic.get("pe"),
        "pb": basic.get("pb"),
        "ma5": sum(closes[-5:]) / 5,
        "ma10": sum(closes[-10:]) / 10,
        "ma20": sum(closes[-20:]) / 20,
        "vol_mult": vols[-1] / (sum(vols[-6:-1]) / 5),
        "ret10": (closes[-1] / closes[-11] - 1) * 100,
        "ret20": (closes[-1] / closes[-21] - 1) * 100,
        "limit": limit_up(today, name),
        "prev_limit": limit_up(hist[-2], name),
    }
    consec = 0
    for day in reversed(hist):
        if limit_up(day, name):
            consec += 1
        else:
            break
    prior_consec = 0
    for day in reversed(hist[:-1]):
        if limit_up(day, name):
            prior_consec += 1
        else:
            break
    row["consec"] = consec
    row["prior_consec"] = prior_consec
    items.append(row)

limit_counts = Counter(x["industry"] for x in items if x["limit"])


def brief(rows, n=30):
    keys = [
        "code", "name", "industry", "close", "pct", "amount", "turn", "vr",
        "vol_mult", "mv", "pe", "pb", "ma5", "ma10", "ma20", "ret10", "ret20",
        "limit", "prev_limit",
        "consec", "prior_consec",
    ]
    return [{k: x.get(k) for k in keys} for x in rows[:n]]


emotion = [
    x for x in items
    if x["limit"]
    and 50 <= x["mv"] <= 300
    and 5 <= (x["turn"] or 0) <= 15
    and (x["vr"] or 0) >= 1.15
    and limit_counts[x["industry"]] >= 3
]
emotion.sort(key=lambda x: (limit_counts[x["industry"]], x["amount"]), reverse=True)

large = [
    x for x in items
    if 700 <= x["mv"] <= 1350 and x["amount"] >= 5 and -5 <= x["pct"] <= 10.1
]
large.sort(
    key=lambda x: (
        x["close"] >= x["ma20"],
        x["close"] >= x["ma10"],
        x["vol_mult"],
        x["pct"],
    ),
    reverse=True,
)

qualified_leaders = [
    x for x in items
    if x["ret10"] >= 50 or x["consec"] >= 6 or x["prior_consec"] >= 6
]
qualified_leaders.sort(
    key=lambda x: (x["consec"], x["prior_consec"], x["ret10"], x["amount"]),
    reverse=True,
)

trend_pool = [
    x for x in items
    if x["mv"] >= 200
    and x["amount"] >= 5
    and x["close"] >= x["ma5"] >= x["ma10"] >= x["ma20"]
    and 2 <= x["ret20"] <= 30
    and x["pct"] >= -2
]
trend_pool.sort(
    key=lambda x: (
        x["pct"],
        x["ret20"],
        x["amount"],
    ),
    reverse=True,
)

new_energy_buzhang = [
    x for x in items
    if x["industry"] == "新型电力"
    and x["code"] != "001258.SZ"
    and x["ret20"] <= 20
    and x["amount"] >= 0.5
]
new_energy_buzhang.sort(
    key=lambda x: (x["vol_mult"], x["amount"]),
    reverse=True,
)

semiconductor_buzhang = [
    x for x in items
    if x["industry"] == "半导体"
    and x["mv"] <= 100
    and x["ret20"] <= 20
    and x["amount"] >= 0.5
]
semiconductor_buzhang.sort(
    key=lambda x: (x["vol_mult"], x["amount"]),
    reverse=True,
)

old_line = {"化学制药", "中成药", "生物制药", "医疗保健"}
same_line = [
    x for x in items
    if x["industry"] in old_line
    and x["mv"] <= 150
    and x["ret20"] <= 20
    and x["pct"] <= 7
    and x["amount"] >= 1
    and x["vol_mult"] >= 1.2
]
same_line.sort(key=lambda x: (x["vol_mult"], x["amount"]), reverse=True)

new_lines = {industry for industry, count in limit_counts.items() if count >= 3}
cross_line = [
    x for x in items
    if x["industry"] in new_lines
    and x["mv"] <= 150
    and x["ret20"] <= 20
    and -2 <= x["pct"] <= 7
    and x["amount"] >= 1
    and x["vol_mult"] >= 1.3
]
cross_line.sort(
    key=lambda x: (limit_counts[x["industry"]], x["vol_mult"], x["amount"]),
    reverse=True,
)

print(json.dumps({
    "dates": dates,
    "raw_breadth": {
        "up": sum(float(x.get("pct_chg") or 0) > 0 for x in by_date[END_DATE]),
        "down": sum(float(x.get("pct_chg") or 0) < 0 for x in by_date[END_DATE]),
        "flat": sum(float(x.get("pct_chg") or 0) == 0 for x in by_date[END_DATE]),
        "up5": sum(float(x.get("pct_chg") or 0) >= 5 for x in by_date[END_DATE]),
        "down5": sum(float(x.get("pct_chg") or 0) <= -5 for x in by_date[END_DATE]),
        "amount_trillion": sum(float(x.get("amount") or 0) for x in by_date[END_DATE]) / 1e9,
    },
    "breadth": {
        "up": sum(x["pct"] > 0 for x in items),
        "down": sum(x["pct"] < 0 for x in items),
        "flat": sum(x["pct"] == 0 for x in items),
        "up5": sum(x["pct"] >= 5 for x in items),
        "down5": sum(x["pct"] <= -5 for x in items),
        "limit_up": sum(x["limit"] for x in items),
        "amount_trillion": sum(x["amount"] for x in items) / 10000,
    },
    "limit_counts": limit_counts.most_common(),
    "all_limits": brief(
        sorted(
            [x for x in items if x["limit"]],
            key=lambda x: (x["consec"], x["amount"]),
            reverse=True,
        ),
        80,
    ),
    "qualified_leaders": brief(qualified_leaders, 20),
    "trend_pool": brief(trend_pool, 50),
    "new_energy_buzhang": brief(new_energy_buzhang, 50),
    "semiconductor_buzhang": brief(semiconductor_buzhang, 50),
    "emotion": brief(emotion),
    "same_line_complement": brief(same_line),
    "cross_line_complement": brief(cross_line),
    "large_cap": brief(large, 40),
}, ensure_ascii=False, indent=2))

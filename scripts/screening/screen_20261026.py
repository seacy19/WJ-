"""Read-only full-market scan for WJ strategy, execution date 2026-10-26."""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, ".tushare_runtime")
import pandas as pd
import tushare as ts

END = "20261023"
SECRET = Path(r"C:\Users\seacy\.codex\visualizations\2026\07\11\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\.market_data_mcp_secrets.json")
OUT = Path("screen_20261026_output.json")

secret = json.loads(SECRET.read_text(encoding="utf-8"))
pro = ts.pro_api(secret.get("TUSHARE_TOKEN") or secret.get("TUSHARE_PRO_TOKEN"))

calendar = pro.trade_cal(exchange="SSE", start_date="20260601", end_date=END, is_open="1", fields="cal_date")
dates = sorted(calendar.cal_date.tolist())[-81:]
daily_fields = "ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount"
frames = [pro.daily(trade_date=d, fields=daily_fields) for d in dates]
bars = pd.concat(frames, ignore_index=True)
quote_path = Path('quote_check_20261026_output.json')
quote_overlay = []
if not bars.trade_date.eq(END).any() and quote_path.exists():
    quotes = json.loads(quote_path.read_text(encoding='utf8'))
    code_map = {c[:6]:c for c in bars.ts_code.unique()}
    for x in quotes:
        if x['code'] not in code_map or not x['time'].startswith(END):
            continue
        code=code_map[x['code']]
        quote_overlay.append({'ts_code':code,'trade_date':END,'open':x['open'],'high':x['high'],'low':x['low'],'close':x['last'],'pre_close':x['previous'],'pct_chg':x['change_pct'],'vol':x['volume']/100 if code.startswith('688') else x['volume'],'amount':x['amount_yi']*100000})
    bars = pd.concat([bars,pd.DataFrame(quote_overlay)],ignore_index=True)
requested_end = END
END = str(bars.trade_date.max())
dates = [d for d in dates if d <= END]
meta = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name,industry,market,list_date")
valuation = pro.daily_basic(trade_date=END, fields="ts_code,trade_date,turnover_rate,volume_ratio,pe_ttm,pb,total_mv,circ_mv")
if valuation.empty and quote_overlay:
    valuation=pd.DataFrame([{'ts_code':code_map[x['code']],'trade_date':END,'turnover_rate':x['turn'],'volume_ratio':float('nan'),'pe_ttm':x['pe'],'pb':float('nan'),'total_mv':(x['mv_yi'] or 0)*10000,'circ_mv':float('nan')} for x in quotes if x['code'] in code_map])

today = bars[bars.trade_date.eq(END)].merge(meta, on="ts_code", how="left").merge(
    valuation.drop(columns="trade_date"), on="ts_code", how="left"
)
today = today[~today.name.fillna("").str.contains("ST|退", case=False, regex=True)].copy()
records = {code: grp.sort_values("trade_date").to_dict("records") for code, grp in bars.groupby("ts_code")}

def is_limit(row):
    code = str(row["ts_code"])
    pct = float(row["pct_chg"])
    if code.startswith(("300", "301", "688")):
        return pct >= 19.5
    if code.endswith(".BJ"):
        return pct >= 29.5
    return pct >= 9.5

rows = []
for item in today.to_dict("records"):
    code = item["ts_code"]
    h = records.get(code, [])
    if len(h) < 21:
        continue
    closes = [float(x["close"]) for x in h]
    highs = [float(x["high"]) for x in h]
    vols = [float(x["vol"]) for x in h]
    flags = [is_limit(x) for x in h]
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
    def ret(n):
        return 100 * (closes[-1] / closes[-n-1] - 1) if len(closes) >= n + 1 else None
    def prior_ret(n):
        return 100 * (closes[-2] / closes[-n-2] - 1) if len(closes) >= n + 2 else None
    def ma(n):
        return sum(closes[-n:]) / n if len(closes) >= n else None
    vol_multiple = vols[-1] / (sum(vols[-6:-1]) / 5) if len(vols) >= 6 and sum(vols[-6:-1]) else None
    p_ret10 = prior_ret(10)
    leader_prior = (p_ret10 is not None and p_ret10 >= 50) or prior_streak >= 6
    high_open_low_close = float(h[-1]["open"]) > float(h[-2]["close"]) and float(h[-1]["close"]) < float(h[-1]["open"])
    break_today = leader_prior and ((flags[-2] and not flags[-1]) or high_open_low_close)
    def maybe(v, digits=2):
        return round(float(v), digits) if pd.notna(v) else None
    row = {
        "code": code,
        "name": item.get("name"),
        "industry": item.get("industry"),
        "market": item.get("market"),
        "close": maybe(item.get("close")),
        "pct": maybe(item.get("pct_chg")),
        "amount_yi": round(float(item.get("amount", 0)) / 100000, 2),
        "mv_yi": round(float(item["total_mv"]) / 10000, 2) if pd.notna(item.get("total_mv")) else None,
        "turn": maybe(item.get("turnover_rate")),
        "vr": maybe(item.get("volume_ratio")),
        "pe_ttm": maybe(item.get("pe_ttm")),
        "pb": maybe(item.get("pb")),
        "ret5": maybe(ret(5)),
        "ret10": maybe(ret(10)),
        "ret20": maybe(ret(20)),
        "ret40": maybe(ret(40)),
        "ma5": maybe(ma(5)),
        "ma10": maybe(ma(10)),
        "ma20": maybe(ma(20)),
        "ma40": maybe(ma(40)),
        "ma60": maybe(ma(60)),
        "prior20_high": round(max(highs[-21:-1]), 2),
        "prior60_high": round(max(highs[-61:-1]), 2) if len(highs) >= 61 else None,
        "vol_multiple": maybe(vol_multiple),
        "limit_today": flags[-1],
        "limit_yesterday": flags[-2],
        "streak": streak,
        "prior_streak": prior_streak,
        "prior_ret10": maybe(p_ret10),
        "leader_prior": leader_prior,
        "break_today": break_today,
    }
    rows.append(row)

limit_industry = Counter(x["industry"] for x in rows if x["limit_today"])
limit_market = Counter(x["market"] for x in rows if x["limit_today"])

def market_day(d):
    q = bars[bars.trade_date.eq(d)]
    vals = q.pct_chg.astype(float)
    return {
        "date": d,
        "up": int((vals > 0).sum()),
        "down": int((vals < 0).sum()),
        "flat": int((vals == 0).sum()),
        "limit_approx": int(sum(is_limit(x) for x in q.to_dict("records"))),
        "amount_yi": round(float(q.amount.astype(float).sum()) / 100000, 1),
        "median_pct": round(float(vals.median()), 2),
    }

def curve_ok(x):
    vals = [x.get(k) for k in ("ma5", "ma10", "ma20", "ma40", "ma60")]
    return all(v is not None for v in vals) and x["close"] > x["ma20"] > x["ma40"] > x["ma60"]

limits = sorted([x for x in rows if x["limit_today"]], key=lambda x: (x["streak"], x["amount_yi"]), reverse=True)
strong = sorted([x for x in rows if x["pct"] >= 7 or x["limit_today"]], key=lambda x: (x["pct"], x["amount_yi"]), reverse=True)
a1 = sorted([
    x for x in rows
    if 50 <= (x["mv_yi"] or 0) <= 300
    and 5 <= (x["turn"] or 0) <= 15
    and (x["vol_multiple"] or 0) >= 1
    and (x["limit_today"] or x["pct"] >= 7)
], key=lambda x: (x["limit_today"], x["streak"], x["amount_yi"]), reverse=True)
leaders = sorted([
    x for x in rows if (x["ret10"] is not None and x["ret10"] >= 50) or x["streak"] >= 6 or x["leader_prior"]
], key=lambda x: (x["break_today"], x["ret10"] or -999), reverse=True)
low_rise = sorted([
    x for x in rows
    if x["ret20"] is not None and x["ret20"] <= 20
    and x["ret10"] is not None and x["ret10"] <= 15
    and (x["vol_multiple"] or 0) >= 1.2
    and 0 <= x["pct"] <= 5
    and 20 <= (x["mv_yi"] or 0) <= 400
    and x["amount_yi"] >= 1
], key=lambda x: (limit_industry[x["industry"]], x["vol_multiple"], x["amount_yi"]), reverse=True)
trend = sorted([
    x for x in rows
    if curve_ok(x)
    and x["ret20"] is not None and -3 <= x["ret20"] <= 25
    and x["ret5"] is not None and -5 <= x["ret5"] <= 12
    and x["amount_yi"] >= 5
    and (x["mv_yi"] or 0) >= 100
    and x["close"] >= 0.95 * x["prior60_high"]
], key=lambda x: (x["amount_yi"], x["ret20"]), reverse=True)

indices = {}
for code in ["000001.SH", "399001.SZ", "399006.SZ", "000300.SH", "000905.SH", "000852.SH"]:
    q = pro.index_daily(ts_code=code, start_date="20260101", end_date=END, fields="ts_code,trade_date,close,pct_chg")
    if q.empty:
        continue
    q = q.sort_values("trade_date")
    close = q.close.astype(float)
    indices[code] = {
        "close": round(float(close.iloc[-1]), 2),
        "pct": round(float(q.pct_chg.iloc[-1]), 2),
        "ret5": round(100 * (float(close.iloc[-1]) / float(close.iloc[-6]) - 1), 2),
        "ret20": round(100 * (float(close.iloc[-1]) / float(close.iloc[-21]) - 1), 2),
        "expma12": round(float(close.ewm(span=12, adjust=False).mean().iloc[-1]), 2),
        "expma50": round(float(close.ewm(span=50, adjust=False).mean().iloc[-1]), 2),
    }

result = {
    "execution_date": "20261026",
    "requested_data_date": requested_end,
    "quote_overlay_rows":len(quote_overlay),
    "data_date": END,
    "trade_dates": dates,
    "market_5d": [market_day(d) for d in dates[-5:]],
    "indices": indices,
    "industry_limit_counts": limit_industry.most_common(),
    "market_limit_counts": dict(limit_market),
    "limits": limits,
    "strong": strong[:160],
    "a1_pool": a1,
    "b1_leaders": leaders,
    "low_rise_pool": low_rise[:180],
    "trend_pool": trend[:180],
}
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

preview = {
    "execution_date": result["execution_date"],
    "data_date": result["data_date"],
    "market_5d": result["market_5d"],
    "indices": result["indices"],
    "industry_limit_counts": result["industry_limit_counts"][:25],
    "limits": result["limits"][:80],
    "a1_pool": result["a1_pool"][:60],
    "b1_leaders": result["b1_leaders"][:60],
    "low_rise_pool": result["low_rise_pool"][:60],
    "trend_pool": result["trend_pool"][:60],
}
print(json.dumps(preview, ensure_ascii=False))

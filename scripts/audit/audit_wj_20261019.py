"""Read-only TuShare screening audit for the 2026-10-19 WJ premarket review."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, ".tushare_runtime")
import pandas as pd
import tushare as ts

SECRET = Path(r"C:\Users\seacy\.codex\visualizations\2026\07\11\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\.market_data_mcp_secrets.json")
data = json.loads(SECRET.read_text(encoding="utf-8"))
pro = ts.pro_api(data.get("TUSHARE_TOKEN") or data.get("TUSHARE_PRO_TOKEN"))
end = "20261016"
calendar = pro.trade_cal(exchange="SSE", start_date="20260901", end_date=end, is_open="1", fields="cal_date")
dates = sorted(calendar.cal_date.tolist())[-21:]
frames = [pro.daily(trade_date=d, fields="ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount") for d in dates]
bars = pd.concat(frames, ignore_index=True)
meta = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name,industry,market,list_date")
valuation = pro.daily_basic(trade_date=end, fields="ts_code,trade_date,turnover_rate,volume_ratio,pe_ttm,pb,total_mv")
today = bars[bars.trade_date.eq(end)].merge(meta, on="ts_code", how="left").merge(valuation.drop(columns="trade_date"), on="ts_code", how="left")
today = today[~today.name.fillna("").str.contains("ST|退", case=False, regex=True)].copy()
records = {code: grp.sort_values("trade_date").to_dict("records") for code, grp in bars.groupby("ts_code")}

def limit(row):
    code = row["ts_code"]
    if code.startswith(("300", "301", "688")):
        return row["pct_chg"] >= 19.5
    if code.endswith(".BJ"):
        return row["pct_chg"] >= 29.5
    return row["pct_chg"] >= 9.5

out = []
for item in today.to_dict("records"):
    code = item["ts_code"]
    history = records[code]
    if len(history) < 2:
        continue
    closes = [float(x["close"]) for x in history]
    vols = [float(x["vol"]) for x in history]
    flags = [limit(x) for x in history]
    streak = 0
    for flag in reversed(flags):
        if not flag: break
        streak += 1
    prior_streak = 0
    for flag in reversed(flags[:-1]):
        if not flag: break
        prior_streak += 1
    ret10 = 100 * (closes[-1] / closes[-11] - 1) if len(history) >= 11 else None
    prior_ret10 = 100 * (closes[-2] / closes[-12] - 1) if len(history) >= 12 else None
    ret20 = 100 * (closes[-1] / closes[-21] - 1) if len(history) >= 21 else None
    vol_multiple = vols[-1] / (sum(vols[-6:-1]) / 5) if sum(vols[-6:-1]) else None
    high_open_low_close = history[-1]["open"] > history[-2]["close"] and history[-1]["close"] < history[-1]["open"]
    leader_now = (ret10 is not None and ret10 >= 50) or streak >= 6
    leader_prior = (prior_ret10 is not None and prior_ret10 >= 50) or prior_streak >= 6
    break_today = leader_prior and ((flags[-2] and not flags[-1]) or high_open_low_close)
    row = {
        "code": code, "name": item["name"], "industry": item["industry"], "market": item["market"],
        "close": round(closes[-1], 2), "pct": round(float(item["pct_chg"]), 2),
        "amount_yi": round(float(item["amount"]) / 100000, 2),
        "mv_yi": round(float(item["total_mv"]) / 10000, 2) if pd.notna(item["total_mv"]) else None,
        "turn": round(float(item["turnover_rate"]), 2) if pd.notna(item["turnover_rate"]) else None,
        "vr": round(float(item["volume_ratio"]), 2) if pd.notna(item["volume_ratio"]) else None,
        "pe_ttm": round(float(item["pe_ttm"]), 2) if pd.notna(item["pe_ttm"]) else None,
        "ma5": round(sum(closes[-5:]) / 5, 2), "ma10": round(sum(closes[-10:]) / 10, 2),
        "ma20": round(sum(closes[-20:]) / 20, 2),
        "prior_20_high": round(max(float(x["high"]) for x in history[-21:-1]), 2),
        "vol_multiple": round(vol_multiple, 2) if vol_multiple else None,
        "ret10": round(ret10, 2) if ret10 is not None else None,
        "prior_ret10": round(prior_ret10, 2) if prior_ret10 is not None else None,
        "ret20": round(ret20, 2) if ret20 is not None else None,
        "limit_today": flags[-1], "limit_yesterday": flags[-2],
        "streak": streak, "prior_streak": prior_streak, "break_today": break_today,
        "leader_now": leader_now, "leader_prior": leader_prior,
    }
    out.append(row)

limit_counts = Counter(x["industry"] for x in out if x["limit_today"])
watch = {"002253.SZ", "600560.SH", "000099.SZ", "300411.SZ", "688583.SH"}
watch_names = {"天成自控", "华建集团", "中信海直", "金盾股份", "司南导航"}
result = {
    "date": end, "dates": dates, "universe": len(out),
    "market": {"up": sum(x["pct"] > 0 for x in out), "down": sum(x["pct"] < 0 for x in out),
               "limits_approx": sum(x["limit_today"] for x in out),
               "amount_yi": round(sum(x["amount_yi"] for x in out), 1)},
    "industry_limit_counts": limit_counts.most_common(25),
    "b1_strength": sorted([x for x in out if x["leader_now"] or x["leader_prior"]], key=lambda x: (x["break_today"], x["ret10"] or -999), reverse=True),
    "a1_quant_pool": sorted([x for x in out if 50 <= (x["mv_yi"] or 0) <= 300 and 5 <= (x["turn"] or 0) <= 15 and (x["vol_multiple"] or 0) > 1 and x["close"] > x["prior_20_high"] and limit_counts[x["industry"]] >= 3], key=lambda x: x["amount_yi"], reverse=True)[:60],
    "a1_full": sorted([x for x in out if 50 <= (x["mv_yi"] or 0) <= 300 and 5 <= (x["turn"] or 0) <= 15 and (x["vol_multiple"] or 0) > 1 and x["close"] > x["prior_20_high"] and x["pct"] >= 5], key=lambda x: x["amount_yi"], reverse=True),
    "prior_names": [x for x in out if x["code"] in watch or x["name"] in watch_names],
    "low_rise": sorted([x for x in out if x["ret20"] is not None and x["ret20"] <= 20 and (x["vol_multiple"] or 0) >= 1.2 and 0 <= x["pct"] <= 5 and (x["mv_yi"] or 0) <= 150 and x["amount_yi"] >= 1], key=lambda x: (limit_counts[x["industry"]], x["vol_multiple"]), reverse=True)[:80],
}
Path("audit_wj_20261019_output.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
preview = {key: value for key, value in result.items() if key not in {"a1_quant_pool", "a1_full", "low_rise"}}
preview["a1_quant_pool"] = result["a1_quant_pool"][:20]
preview["low_rise"] = result["low_rise"][:15]
print(json.dumps(preview, ensure_ascii=False, separators=(",", ":")))

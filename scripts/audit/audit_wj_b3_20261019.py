"""Inspect B3 bottom and volume conditions for same-line and cross-line stocks."""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".tushare_runtime")
import tushare as ts

secret = Path(r"C:\Users\seacy\.codex\visualizations\2026\07\11\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\.market_data_mcp_secrets.json")
s = json.loads(secret.read_text(encoding="utf-8"))
pro = ts.pro_api(s.get("TUSHARE_TOKEN") or s.get("TUSHARE_PRO_TOKEN"))
codes = [
    "000892.SZ", "603258.SH", "603999.SH", "301025.SZ", "301052.SZ",
    "603533.SH", "300364.SZ", "300133.SZ", "000607.SZ", "601999.SH",
    "601811.SH", "603636.SH", "300094.SZ", "600467.SH", "002069.SZ",
    "000798.SZ", "603668.SH", "603085.SH", "600629.SH", "000099.SZ",
    "300411.SZ", "688592.SH", "300581.SZ", "600316.SH",
]
meta = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name,industry").set_index("ts_code")
val = pro.daily_basic(trade_date="20261016", fields="ts_code,total_mv,turnover_rate").set_index("ts_code")
output = []
for code in codes:
    d = pro.daily(ts_code=code, start_date="20260601", end_date="20261016", fields="ts_code,trade_date,open,high,low,close,pct_chg,vol,amount")
    if d.empty: continue
    d = d.sort_values("trade_date").reset_index(drop=True)
    closes = d.close.astype(float)
    prev = d.iloc[:-1]
    before = d.iloc[-61:-1]
    if len(prev) < 21: continue
    prev20 = (float(prev.iloc[-1].close) / float(prev.iloc[-21].close) - 1) * 100
    today20 = (float(d.iloc[-1].close) / float(d.iloc[-21].close) - 1) * 100
    max_close = float(before.close.max())
    min_close = float(before.close.min())
    peak_index = before.close.astype(float).idxmax()
    drop_after_peak = 100 * (1 - float(before.loc[peak_index:, "close"].min()) / max_close)
    t = d.iloc[-1]
    output.append({
        "code": code, "name": meta.loc[code, "name"] if code in meta.index else None,
        "industry": meta.loc[code, "industry"] if code in meta.index else None,
        "close": round(float(t.close), 2), "pct": round(float(t.pct_chg), 2),
        "ret20_pre": round(prev20, 2), "ret20_today": round(today20, 2),
        "range60_pre_pct": round(100 * (max_close / min_close - 1), 2),
        "drop_after_peak_pct": round(drop_after_peak, 2),
        "volume_multiple": round(float(t.vol) / float(prev.vol.astype(float).iloc[-5:].mean()), 2),
        "prior_3_amount_max_yi": round(float(prev.amount.astype(float).iloc[-3:].max()) / 100000, 2),
        "mv_yi": round(float(val.loc[code, "total_mv"]) / 10000, 2) if code in val.index else None,
        "turn": round(float(val.loc[code, "turnover_rate"]), 2) if code in val.index else None,
        "ma5": round(float(closes.iloc[-5:].mean()), 2),
        "ma10": round(float(closes.iloc[-10:].mean()), 2),
        "amount_yi": round(float(t.amount) / 100000, 2),
        "bars": len(d),
    })
Path("audit_wj_b3_20261019_output.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
print(len(output))

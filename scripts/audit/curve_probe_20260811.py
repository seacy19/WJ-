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
START_DATE = os.environ.get("WJ_START_DATE", "20250601")
CODES = [
    "601899.SH", "603993.SH", "600362.SH", "601600.SH", "600988.SH",
    "600489.SH", "600547.SH", "000975.SZ", "002155.SZ", "000426.SZ",
    "600276.SH", "000963.SZ", "002422.SZ", "688235.SH", "300347.SZ",
    "300759.SZ", "002821.SZ", "603259.SH", "300122.SZ", "600196.SH",
    "600887.SH", "605499.SH", "603156.SH", "000858.SZ", "600809.SH",
    "000333.SZ", "000651.SZ", "600690.SH", "600519.SH", "600600.SH",
    "601138.SH", "300308.SZ", "300502.SZ", "300394.SZ", "002475.SZ",
    "300476.SZ", "600183.SH", "603228.SH", "603296.SH", "002463.SZ",
    "300124.SZ", "688041.SH", "688256.SH", "688008.SH", "688012.SH",
    "600893.SH", "000768.SZ", "600760.SH", "600150.SH", "601989.SH",
    "600031.SH", "000425.SZ", "601100.SH", "600406.SH", "002028.SZ",
    "600900.SH", "601088.SH", "601225.SH", "601898.SH", "601668.SH",
    "002827.SZ", "002096.SZ", "002683.SZ", "002226.SZ", "002037.SZ",
    "603227.SH", "003002.SZ",
    "300161.SZ", "002248.SZ", "002685.SZ", "688305.SH", "601882.SH",
    "000837.SZ", "688558.SH", "688697.SH", "301603.SZ",
    "603501.SH", "603893.SH", "300661.SZ", "301269.SZ", "688469.SH",
    "603087.SH", "603939.SH", "688336.SH",
]
if os.environ.get("WJ_CODES"):
    CODES = [code.strip() for code in os.environ["WJ_CODES"].split(",") if code.strip()]


secrets = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
token = secrets.get("TUSHARE_TOKEN") or secrets.get("TUSHARE_PRO_TOKEN")
pro = ts.pro_api(token)
basic = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name,industry").set_index("ts_code")
db = pro.daily_basic(
    trade_date=END_DATE,
    fields="ts_code,trade_date,turnover_rate,volume_ratio,pe_ttm,pb,total_mv",
).set_index("ts_code")


rows = []
for code in CODES:
    try:
        df = ts.pro_bar(api=pro, ts_code=code, start_date=START_DATE, end_date=END_DATE, adj="qfq")
        if df is None or df.empty:
            continue
        df = df.sort_values("trade_date").reset_index(drop=True)
        c = df["close"].astype(float).reset_index(drop=True)
        v = df["vol"].astype(float).reset_index(drop=True)
        last = float(c.iloc[-1])
        mas = {w: float(c.iloc[-w:].mean()) for w in (5, 10, 20, 60, 120, 250)}
        slopes = {}
        for w in (20, 60, 120, 250):
            old = float(c.iloc[-(w + 20):-20].mean())
            slopes[w] = (mas[w] / old - 1) * 100
        order = [last] + [mas[w] for w in (5, 10, 20, 60, 120, 250)]
        full = all(order[i] >= order[i + 1] for i in range(len(order) - 1))
        long = last >= mas[20] >= mas[60] >= mas[120] >= mas[250]
        meta = basic.loc[code]
        val = db.loc[code] if code in db.index else None
        rows.append({
            "code": code, "name": meta["name"], "industry": meta["industry"],
            "open": float(df.iloc[-1]["open"]),
            "high": float(df.iloc[-1]["high"]),
            "low": float(df.iloc[-1]["low"]),
            "close": last, "pct": float(df.iloc[-1]["pct_chg"]),
            "market_cap_yi": None if val is None else float(val["total_mv"] / 10000),
            "pe_ttm": None if val is None or pd.isna(val["pe_ttm"]) else float(val["pe_ttm"]),
            "turnover": None if val is None else float(val["turnover_rate"]),
            "volume_ratio": None if val is None or pd.isna(val["volume_ratio"]) else float(val["volume_ratio"]),
            **{f"ma{w}": mas[w] for w in (5, 10, 20, 60, 120, 250)},
            **{f"slope{w}": slopes[w] for w in (20, 60, 120, 250)},
            "ret5": (last / float(c.iloc[-6]) - 1) * 100,
            "ret10": (last / float(c.iloc[-11]) - 1) * 100,
            "ret20": (last / float(c.iloc[-21]) - 1) * 100,
            "full_curve": full, "long_curve": long,
            "all_slopes_up": all(slopes[w] > 0 for w in slopes),
            "high250": float(c.iloc[-250:].max()),
            "drawdown250": (last / float(c.iloc[-250:].max()) - 1) * 100,
            "history_high": float(c.max()),
            "history_high_date": str(df.loc[c.idxmax(), "trade_date"]),
            "history_drawdown": (last / float(c.max()) - 1) * 100,
            **{f"high{w}": float(c.iloc[-w:].max()) for w in (20, 60, 120)},
            **{f"low{w}": float(c.iloc[-w:].min()) for w in (20, 60, 120)},
            **{f"range{w}": (float(c.iloc[-w:].max()) / float(c.iloc[-w:].min()) - 1) * 100 for w in (20, 60, 120)},
            "high60_date": str(df.iloc[-60:].loc[df.iloc[-60:]["close"].astype(float).idxmax(), "trade_date"]),
            "low60_date": str(df.iloc[-60:].loc[df.iloc[-60:]["close"].astype(float).idxmin(), "trade_date"]),
            "prev3_max_amount_yi": float(df.iloc[-4:-1]["amount"].astype(float).max() / 100000),
            "vol5_ratio": float(v.iloc[-1] / v.iloc[-6:-1].mean()),
        })
    except Exception as exc:
        rows.append({"code": code, "error": str(exc)})

Path(os.environ.get("WJ_OUTPUT", "curve_probe_20260811_output.json")).write_text(
    json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps({"count": len(rows)}, ensure_ascii=False))

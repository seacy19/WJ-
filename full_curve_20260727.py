import json
import os
from pathlib import Path

import pandas as pd
import tushare as ts


SECRET_FILE = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11"
    r"\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\.market_data_mcp_secrets.json"
)
END_DATE = os.environ.get("WJ_END_DATE", "20260727")
CANDIDATES = [
    "002879.SZ", "002300.SZ", "002298.SZ", "002498.SZ", "000533.SZ",
    "002156.SZ", "603893.SH", "688361.SH", "603228.SH", "603296.SH",
    "600584.SH", "002185.SZ",
    "002028.SZ", "300480.SZ", "603690.SH", "300458.SZ",
    "603129.SH", "002414.SZ", "600760.SH", "600926.SH", "600066.SH",
    "000425.SZ", "002241.SZ", "688002.SH", "605117.SH", "000938.SZ",
    "300750.SZ",
    "601179.SH", "600406.SH", "600312.SH", "002270.SZ",
    "600176.SH", "301526.SZ", "603256.SH", "002080.SZ",
    "002409.SZ", "002353.SZ", "688111.SH", "002415.SZ",
    "300896.SZ", "300628.SZ", "000862.SZ", "601606.SH",
    "002384.SZ", "002475.SZ", "603369.SH", "605499.SH",
    "600415.SH", "603486.SH", "000893.SZ", "000568.SZ",
    "600519.SH", "600690.SH", "601229.SH", "601888.SH",
    "600941.SH", "600660.SH", "600031.SH", "600674.SH",
    "000333.SZ", "600036.SH", "601088.SH", "600756.SH",
    "002212.SZ", "002279.SZ", "001358.SZ", "002173.SZ",
    "600775.SH",
]


def ma_at(closes: pd.Series, window: int, offset: int = 0):
    end = len(closes) - offset
    if end < window:
        return None
    return float(closes.iloc[end - window:end].mean())


secrets = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
token = secrets.get("TUSHARE_TOKEN") or secrets.get("TUSHARE_PRO_TOKEN")
pro = ts.pro_api(token)
basic = pro.stock_basic(
    exchange="",
    list_status="L",
    fields="ts_code,name,industry",
).set_index("ts_code")

rows = []
for code in CANDIDATES:
    df = ts.pro_bar(
        api=pro,
        ts_code=code,
        start_date="20250601",
        end_date=END_DATE,
        adj="qfq",
    ).sort_values("trade_date")
    if df.empty:
        continue
    closes = df["close"].astype(float).reset_index(drop=True)
    vols = df["vol"].astype(float).reset_index(drop=True)
    mas = {w: ma_at(closes, w) for w in (5, 10, 20, 60, 120, 250)}
    slopes = {
        f"ma{w}_slope20_pct": (
            (mas[w] / ma_at(closes, w, 20) - 1) * 100
            if mas[w] is not None and ma_at(closes, w, 20) is not None
            else None
        )
        for w in (20, 60, 120, 250)
    }
    last = float(closes.iloc[-1])
    high250 = float(closes.iloc[-250:].max()) if len(closes) >= 250 else float(closes.max())
    low250 = float(closes.iloc[-250:].min()) if len(closes) >= 250 else float(closes.min())
    meta = basic.loc[code] if code in basic.index else {}
    row = {
        "code": code,
        "name": meta.get("name", ""),
        "industry": meta.get("industry", ""),
        "close": last,
        "pct": float(df.iloc[-1]["pct_chg"]),
        **{f"ma{w}": mas[w] for w in (5, 10, 20, 60, 120, 250)},
        **slopes,
        "ret20_pct": (last / float(closes.iloc[-21]) - 1) * 100 if len(closes) >= 21 else None,
        "ret60_pct": (last / float(closes.iloc[-61]) - 1) * 100 if len(closes) >= 61 else None,
        "ret120_pct": (last / float(closes.iloc[-121]) - 1) * 100 if len(closes) >= 121 else None,
        "ret250_pct": (last / float(closes.iloc[-251]) - 1) * 100 if len(closes) >= 251 else None,
        "high250": high250,
        "drawdown250_pct": (last / high250 - 1) * 100,
        "low250": low250,
        "vol5_ratio": float(vols.iloc[-1] / vols.iloc[-6:-1].mean()),
        "amount_bn": float(df.iloc[-1]["amount"]) / 100000,
    }
    long_mas = [mas[w] for w in (20, 60, 120, 250)]
    row["curve_order_pass"] = all(x is not None for x in long_mas) and (
        last >= mas[20] >= mas[60] >= mas[120] >= mas[250]
    )
    row["all_long_slopes_up"] = all(
        slopes[f"ma{w}_slope20_pct"] is not None
        and slopes[f"ma{w}_slope20_pct"] > 0
        for w in (20, 60, 120, 250)
    )
    rows.append(row)

selected_names = {
    name.strip()
    for name in os.environ.get("WJ_NAMES", "").split(",")
    if name.strip()
}
if selected_names:
    rows = [row for row in rows if row["name"] in selected_names]
print(json.dumps(rows, ensure_ascii=False, indent=2))

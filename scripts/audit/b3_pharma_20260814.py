import json
from pathlib import Path

import pandas as pd
import tushare as ts


SECRET_FILE = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11"
    r"\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\.market_data_mcp_secrets.json"
)
END_DATE = "20260813"
OUT = Path("b3_pharma_20260814_output.json")
INDUSTRIES = {"生物制药", "化学制药", "中成药", "医疗保健", "医药商业"}

secrets = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
pro = ts.pro_api(secrets.get("TUSHARE_TOKEN") or secrets.get("TUSHARE_PRO_TOKEN"))
basic = pro.stock_basic(
    exchange="", list_status="L", fields="ts_code,name,industry,market,list_date"
)
basic = basic[basic["industry"].isin(INDUSTRIES)]
basic = basic[~basic["name"].fillna("").str.contains("ST")].set_index("ts_code")
db = pro.daily_basic(
    trade_date=END_DATE,
    fields="ts_code,total_mv,pe_ttm,pb,turnover_rate,volume_ratio",
).set_index("ts_code")
cal = pro.trade_cal(
    exchange="SSE", start_date="20260601", end_date=END_DATE, is_open="1", fields="cal_date"
)
dates = sorted(cal["cal_date"].tolist())[-31:]
frames = [
    pro.daily(
        trade_date=d,
        fields="ts_code,trade_date,open,high,low,close,pct_chg,vol,amount",
    )
    for d in dates
]
daily = pd.concat(frames, ignore_index=True)
daily = daily[daily["ts_code"].isin(basic.index)].copy()

rows = []
for code, g in daily.groupby("ts_code"):
    g = g.sort_values("trade_date").reset_index(drop=True)
    if len(g) < 22 or g.iloc[-1]["trade_date"] != END_DATE:
        continue
    c = g["close"].astype(float)
    v = g["vol"].astype(float)
    last = g.iloc[-1]
    val = db.loc[code] if code in db.index else None
    mv = None if val is None else float(val["total_mv"] / 10000)
    ret20_pre = (float(c.iloc[-2]) / float(c.iloc[-22]) - 1) * 100
    ret20 = (float(c.iloc[-1]) / float(c.iloc[-21]) - 1) * 100
    low20 = float(c.iloc[-21:].min())
    high20 = float(c.iloc[-21:].max())
    rows.append(
        {
            "code": code,
            "name": basic.loc[code, "name"],
            "industry": basic.loc[code, "industry"],
            "close": float(last["close"]),
            "pct": float(last["pct_chg"]),
            "market_cap_yi": mv,
            "pe_ttm": None if val is None or pd.isna(val["pe_ttm"]) else float(val["pe_ttm"]),
            "turnover": None if val is None else float(val["turnover_rate"]),
            "volume_ratio": None if val is None or pd.isna(val["volume_ratio"]) else float(val["volume_ratio"]),
            "ret5": (float(c.iloc[-1]) / float(c.iloc[-6]) - 1) * 100,
            "ret10": (float(c.iloc[-1]) / float(c.iloc[-11]) - 1) * 100,
            "ret20_pre": ret20_pre,
            "ret20": ret20,
            "amount_yi": float(last["amount"] / 100000),
            "prev3_max_amount_yi": float(g.iloc[-4:-1]["amount"].astype(float).max() / 100000),
            "vol5_ratio": float(v.iloc[-1] / v.iloc[-6:-1].mean()),
            "low20": low20,
            "high20": high20,
            "position20": (float(last["close"]) - low20) / (high20 - low20) if high20 > low20 else 0,
            "b4_price": float(last["close"]) < 10,
            "b4_mcap": mv is not None and mv < 100,
            "b4_liquidity": float(g.iloc[-4:-1]["amount"].astype(float).max() / 100000) >= 5,
            "b4_pre_gain": ret20_pre <= 20,
            "core_low_gain": ret20 < 20,
        }
    )

frame = pd.DataFrame(rows)
frame["score"] = (
    frame["pct"].clip(-5, 8) * 0.8
    + frame["volume_ratio"].fillna(0) * 2
    + frame["b4_price"].astype(int)
    + frame["b4_mcap"].astype(int)
    + frame["b4_liquidity"].astype(int) * 2
    + frame["b4_pre_gain"].astype(int)
    - frame["ret20"].clip(lower=0) * 0.08
)
frame = frame[
    (frame["pct"] > -2)
    & (frame["pct"] < 8)
    & (frame["volume_ratio"] >= 1.1)
    & (frame["ret20"] < 20)
].sort_values("score", ascending=False)
OUT.write_text(frame.to_json(orient="records", force_ascii=False, indent=2), encoding="utf-8")
print(frame.head(40).to_json(orient="records", force_ascii=False, indent=2))

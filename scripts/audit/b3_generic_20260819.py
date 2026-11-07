import json
import os
from pathlib import Path

import pandas as pd
import tushare as ts


SECRET_FILE = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11"
    r"\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\.market_data_mcp_secrets.json"
)
END_DATE = os.environ.get("WJ_TRADE_DATE", "20260817")
OUT = Path(os.environ.get("WJ_OUTPUT", "b3_generic_20260819_output.json"))
INDUSTRIES = {
    item.strip()
    for item in os.environ.get(
        "WJ_INDUSTRIES", "半导体,元器件,通信设备,专用机械,矿物制品"
    ).split(",")
    if item.strip()
}

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
    exchange="SSE", start_date="20260601", end_date=END_DATE,
    is_open="1", fields="cal_date",
)
dates = sorted(cal["cal_date"].tolist())[-31:]
frames = [
    pro.daily(
        trade_date=date,
        fields="ts_code,trade_date,open,high,low,close,pct_chg,vol,amount",
    )
    for date in dates
]
daily = pd.concat(frames, ignore_index=True)
daily = daily[daily["ts_code"].isin(basic.index)].copy()

rows = []
for code, group in daily.groupby("ts_code"):
    group = group.sort_values("trade_date").reset_index(drop=True)
    if len(group) < 22 or group.iloc[-1]["trade_date"] != END_DATE:
        continue
    close = group["close"].astype(float)
    vol = group["vol"].astype(float)
    last = group.iloc[-1]
    value = db.loc[code] if code in db.index else None
    market_cap = None if value is None else float(value["total_mv"] / 10000)
    ret20_pre = (float(close.iloc[-2]) / float(close.iloc[-22]) - 1) * 100
    ret20 = (float(close.iloc[-1]) / float(close.iloc[-21]) - 1) * 100
    low20 = float(close.iloc[-21:].min())
    high20 = float(close.iloc[-21:].max())
    prev3_amount = float(group.iloc[-4:-1]["amount"].astype(float).max() / 100000)
    rows.append(
        {
            "code": code,
            "name": basic.loc[code, "name"],
            "industry": basic.loc[code, "industry"],
            "close": float(last["close"]),
            "pct": float(last["pct_chg"]),
            "market_cap_yi": market_cap,
            "pe_ttm": None if value is None or pd.isna(value["pe_ttm"]) else float(value["pe_ttm"]),
            "turnover": None if value is None else float(value["turnover_rate"]),
            "volume_ratio": None if value is None or pd.isna(value["volume_ratio"]) else float(value["volume_ratio"]),
            "ret5": (float(close.iloc[-1]) / float(close.iloc[-6]) - 1) * 100,
            "ret10": (float(close.iloc[-1]) / float(close.iloc[-11]) - 1) * 100,
            "ret20_pre": ret20_pre,
            "ret20": ret20,
            "amount_yi": float(last["amount"] / 100000),
            "prev3_max_amount_yi": prev3_amount,
            "vol5_ratio": float(vol.iloc[-1] / vol.iloc[-6:-1].mean()),
            "position20": (float(last["close"]) - low20) / (high20 - low20) if high20 > low20 else 0.0,
            "b4_price": float(last["close"]) < 10,
            "b4_mcap": market_cap is not None and market_cap < 100,
            "b4_liquidity": prev3_amount >= 5,
            "b4_pre_gain": ret20_pre <= 20,
            "b5_close_condition": float(last["pct_chg"]) <= 2,
        }
    )

frame = pd.DataFrame(rows)
frame["b4_score"] = (
    frame["b4_price"].astype(int)
    + frame["b4_mcap"].astype(int)
    + frame["b4_liquidity"].astype(int)
    + frame["b4_pre_gain"].astype(int)
)
frame["rank_score"] = (
    frame["b4_score"] * 5
    + frame["volume_ratio"].fillna(0).clip(0, 3) * 1.5
    - frame["ret20"].clip(lower=0) * 0.08
    - frame["position20"] * 2
)
frame = frame.sort_values(["b4_score", "rank_score"], ascending=False)
OUT.write_text(frame.to_json(orient="records", force_ascii=False, indent=2), encoding="utf-8")
print(frame.head(50).to_json(orient="records", force_ascii=False, indent=2))

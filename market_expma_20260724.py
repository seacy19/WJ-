import json
import os
from pathlib import Path

import pandas as pd
import tushare as ts


SECRET_FILE = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11"
    r"\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\.market_data_mcp_secrets.json"
)
secrets = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
token = secrets.get("TUSHARE_TOKEN") or secrets.get("TUSHARE_PRO_TOKEN")
pro = ts.pro_api(token)
end_date = os.environ.get("WJ_END_DATE", "20260727")

df = pro.stk_mins(
    ts_code="000001.SH",
    freq="15min",
    start_date="2026-07-01 09:30:00",
    end_date=f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]} 15:00:00",
)
if df.empty:
    raise RuntimeError("No 15-minute index data returned")

time_col = "trade_time" if "trade_time" in df.columns else "trade_date"
df = df.sort_values(time_col).reset_index(drop=True)
df["close"] = df["close"].astype(float)
df["ema12"] = df["close"].ewm(span=12, adjust=False).mean()
df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
df["state"] = (df["ema12"] > df["ema50"]).astype(int)
df["cross"] = df["state"].diff()

hourly = df.copy()
hourly["group"] = range(len(hourly))
hourly["group"] = hourly["group"] // 4
hourly = hourly.groupby("group", as_index=False).agg(
    trade_time=(time_col, "last"),
    close=("close", "last"),
)
hourly["ema12"] = hourly["close"].ewm(span=12, adjust=False).mean()
hourly["ema50"] = hourly["close"].ewm(span=50, adjust=False).mean()
hourly["state"] = (hourly["ema12"] > hourly["ema50"]).astype(int)
hourly["cross"] = hourly["state"].diff()


def summarize(frame):
    last = frame.iloc[-1]
    recent_cross = frame[frame["cross"].abs() == 1].tail(5)
    return {
        "last_time": str(last[frame.columns[1] if frame.columns[0] == "group" else time_col])
        if "group" in frame.columns
        else str(last[time_col]),
        "close": float(last["close"]),
        "ema12": float(last["ema12"]),
        "ema50": float(last["ema50"]),
        "state": "golden" if int(last["state"]) == 1 else "dead",
        "gap_pct": float((last["ema12"] / last["ema50"] - 1) * 100),
        "recent_crosses": [
            {
                "time": str(r["trade_time"] if "trade_time" in r else r[time_col]),
                "type": "golden" if r["cross"] == 1 else "dead",
            }
            for _, r in recent_cross.iterrows()
        ],
    }


print(json.dumps({
    "15min": summarize(df),
    "60min": summarize(hourly),
}, ensure_ascii=False, indent=2))

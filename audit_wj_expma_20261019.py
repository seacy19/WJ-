"""Index EXPMA(12, 50) status for the WJ premarket decision."""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".tushare_runtime")
import pandas as pd
import requests
import tushare as ts

secret = Path(r"C:\Users\seacy\.codex\visualizations\2026\07\11\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\.market_data_mcp_secrets.json")
s = json.loads(secret.read_text(encoding="utf-8"))
pro = ts.pro_api(s.get("TUSHARE_TOKEN") or s.get("TUSHARE_PRO_TOKEN"))
session = requests.Session()
session.trust_env = False
response = session.get("https://push2his.eastmoney.com/api/qt/stock/kline/get", params={
    "secid":"1.000001", "klt":"15", "fqt":"0", "beg":"20260901", "end":"20261016", "lmt":"1000",
    "fields1":"f1,f2,f3,f4,f5,f6", "fields2":"f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
}, timeout=15).json()
minute = pd.DataFrame([{"trade_time": line.split(",")[0], "close": float(line.split(",")[2])} for line in response["data"]["klines"]])
minute = minute.sort_values("trade_time").reset_index(drop=True)
minute["date"] = minute.trade_time.str.slice(0, 10)
minute["bar"] = minute.groupby("date").cumcount()
hour = minute.groupby(["date", minute.bar // 4], as_index=False).agg(trade_time=("trade_time", "last"), close=("close", "last"))
daily = pro.index_daily(ts_code="000001.SH", start_date="20260101", end_date="20261016", fields="ts_code,trade_date,close")
daily = daily.sort_values("trade_date").reset_index(drop=True)

def state(df, time_col):
    frame = df.copy()
    frame["ema12"] = frame.close.ewm(span=12, adjust=False).mean()
    frame["ema50"] = frame.close.ewm(span=50, adjust=False).mean()
    frame["gold"] = frame.ema12 > frame.ema50
    cross = frame[frame.gold.ne(frame.gold.shift())].tail(5)
    last = frame.iloc[-1]
    return {"count":len(frame), "last":str(last[time_col]), "close":round(float(last.close),2),
            "ema12":round(float(last.ema12),2),"ema50":round(float(last.ema50),2),
            "state":"金叉" if last.gold else "死叉",
            "recent_crosses":[{"time":str(row[time_col]),"state":"金叉" if row.gold else "死叉"} for _,row in cross.iterrows()]}

out={"15min":state(minute,"trade_time"),"60min":state(hour,"trade_time"),"daily":state(daily,"trade_date")}
print(json.dumps(out,ensure_ascii=False,indent=2))

import json
from pathlib import Path

import pandas as pd
import tushare as ts


SECRET_FILE = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11"
    r"\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\.market_data_mcp_secrets.json"
)
import os

DATE = os.environ.get("WJ_TRADE_DATE", "20260811")
INDUSTRIES = ["机床制造", "生物制药", "医药商业", "化学制药", "中成药", "医疗保健", "乳制品", "煤炭开采", "石油开采", "黄金", "半导体", "元器件", "化工原料", "通信设备"]
if os.environ.get("WJ_INDUSTRIES"):
    INDUSTRIES = [
        industry.strip()
        for industry in os.environ["WJ_INDUSTRIES"].split(",")
        if industry.strip()
    ]
secrets = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
pro = ts.pro_api(secrets.get("TUSHARE_TOKEN") or secrets.get("TUSHARE_PRO_TOKEN"))
basic = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name,industry,market").set_index("ts_code")
db = pro.daily_basic(trade_date=DATE, fields="ts_code,total_mv,pe_ttm,pb,turnover_rate,volume_ratio").set_index("ts_code")
cal = pro.trade_cal(exchange="SSE", start_date="20260701", end_date=DATE, is_open="1", fields="cal_date")
dates = sorted(cal["cal_date"].tolist())[-11:]
frames = [pro.daily(trade_date=d, fields="ts_code,trade_date,close,pct_chg,amount,vol") for d in dates]
all_daily = pd.concat(frames, ignore_index=True)
piv = all_daily.pivot_table(index="ts_code", columns="trade_date", values="close", aggfunc="last")
last = all_daily[all_daily["trade_date"] == DATE].set_index("ts_code")
rows = []
for code, row in last.iterrows():
    if code not in basic.index or basic.loc[code, "industry"] not in INDUSTRIES:
        continue
    name = basic.loc[code, "name"]
    if "ST" in str(name):
        continue
    val = db.loc[code] if code in db.index else None
    rows.append({
        "code": code,
        "name": name,
        "industry": basic.loc[code, "industry"],
        "close": float(row["close"]),
        "pct": float(row["pct_chg"]),
        "ret5": (float(row["close"]) / float(piv.loc[code, dates[-6]]) - 1) * 100 if code in piv.index else None,
        "ret10": (float(row["close"]) / float(piv.loc[code, dates[-11]]) - 1) * 100 if code in piv.index else None,
        "market_cap_yi": None if val is None else float(val["total_mv"] / 10000),
        "pe_ttm": None if val is None or pd.isna(val["pe_ttm"]) else float(val["pe_ttm"]),
        "turnover": None if val is None else float(val["turnover_rate"]),
        "volume_ratio": None if val is None or pd.isna(val["volume_ratio"]) else float(val["volume_ratio"]),
        "amount_bn": float(row["amount"] / 100000),
    })

out = {}
frame = pd.DataFrame(rows)
out["_stats"] = {
    industry: {
        "count": int(len(group)),
        "advance": int((group["pct"] > 0).sum()),
        "advance_ratio": float((group["pct"] > 0).mean()),
        "mean_pct": float(group["pct"].mean()),
        "median_pct": float(group["pct"].median()),
        "median_ret5": float(group["ret5"].median()),
        "amount_bn": float(group["amount_bn"].sum()),
    }
    for industry, group in frame.groupby("industry")
}
for industry in INDUSTRIES:
    out[industry] = frame[frame["industry"] == industry].sort_values("pct", ascending=False).head(20).to_dict(orient="records")
Path(os.environ.get("WJ_OUTPUT", "theme_members_20260812_output.json")).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=2))

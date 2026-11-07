import json
from pathlib import Path

import tushare as ts


SECRET_FILE = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11"
    r"\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\.market_data_mcp_secrets.json"
)
secrets = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
pro = ts.pro_api(secrets.get("TUSHARE_TOKEN") or secrets.get("TUSHARE_PRO_TOKEN"))

calendar = pro.trade_cal(
    exchange="SSE",
    start_date="20260810",
    end_date="20260818",
    fields="cal_date,is_open,pretrade_date",
).sort_values("cal_date")

rows = []
for date in calendar.loc[calendar["is_open"] == 1, "cal_date"]:
    daily = pro.daily(trade_date=date, fields="ts_code,trade_date,close,pct_chg,amount")
    rows.append(
        {
            "date": date,
            "daily_rows": len(daily),
            "amount_yi": float(daily["amount"].sum() / 100000) if not daily.empty else 0.0,
        }
    )

print(json.dumps({"calendar": calendar.to_dict(orient="records"), "availability": rows}, ensure_ascii=False, indent=2))

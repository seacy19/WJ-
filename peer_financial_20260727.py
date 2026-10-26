import json
from pathlib import Path

import tushare as ts


SECRET_FILE = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11"
    r"\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\.market_data_mcp_secrets.json"
)
CODES = [
    "002156.SZ", "600584.SH", "002185.SZ",
    "603893.SH", "688002.SH", "603129.SH", "603228.SH", "002028.SZ",
]
secrets = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
token = secrets.get("TUSHARE_TOKEN") or secrets.get("TUSHARE_PRO_TOKEN")
pro = ts.pro_api(token)

out = []
for code in CODES:
    income = pro.income(
        ts_code=code,
        start_date="20250101",
        end_date="20260630",
        fields="ts_code,ann_date,end_date,report_type,revenue,n_income_attr_p",
    )
    indicator = pro.fina_indicator(
        ts_code=code,
        start_date="20250101",
        end_date="20260630",
        fields=(
            "ts_code,ann_date,end_date,roe,grossprofit_margin,"
            "netprofit_margin,tr_yoy,netprofit_yoy,ocf_to_or"
        ),
    )
    out.append({
        "code": code,
        "income": income.sort_values(["end_date", "ann_date"]).to_dict("records"),
        "indicator": indicator.sort_values(["end_date", "ann_date"]).to_dict("records"),
    })

print(json.dumps(out, ensure_ascii=False, indent=2))

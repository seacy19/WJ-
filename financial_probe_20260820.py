import json
import os
from pathlib import Path

import tushare as ts


SECRET_FILE = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11"
    r"\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\.market_data_mcp_secrets.json"
)
CODES = [
    "600985.SH",  # 淮北矿业
    "601225.SH",  # 陕西煤业
    "601088.SH",  # 中国神华
    "600997.SH",  # 开滦股份
    "600740.SH",  # 山西焦化
    "601009.SH",  # 南京银行
    "600036.SH",  # 招商银行
]
if os.environ.get("WJ_CODES"):
    CODES = [code.strip() for code in os.environ["WJ_CODES"].split(",") if code.strip()]
END_DATE = os.environ.get("WJ_END_DATE", "20260819")

secrets = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
pro = ts.pro_api(secrets.get("TUSHARE_TOKEN") or secrets.get("TUSHARE_PRO_TOKEN"))

out = []
for code in CODES:
    income = pro.income(
        ts_code=code,
        start_date="20250101",
        end_date=END_DATE,
        fields="ts_code,ann_date,end_date,report_type,revenue,n_income_attr_p",
    )
    indicator = pro.fina_indicator(
        ts_code=code,
        start_date="20250101",
        end_date=END_DATE,
        fields=(
            "ts_code,ann_date,end_date,roe,grossprofit_margin,"
            "netprofit_margin,tr_yoy,netprofit_yoy,ocf_to_or"
        ),
    )
    out.append(
        {
            "code": code,
            "income": income.sort_values(["end_date", "ann_date"], ascending=False)
            .head(6)
            .to_dict("records"),
            "indicator": indicator.sort_values(["end_date", "ann_date"], ascending=False)
            .head(6)
            .to_dict("records"),
        }
    )

payload = json.dumps(out, ensure_ascii=False, indent=2)
if os.environ.get("WJ_OUTPUT"):
    Path(os.environ["WJ_OUTPUT"]).write_text(payload, encoding="utf-8")
print(payload)

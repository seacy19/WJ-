"""Compare fundamental leaders across four plausible profit-growth chains."""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".tushare_runtime")
import tushare as ts

secret = Path(r"C:\Users\seacy\.codex\visualizations\2026\07\11\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp\.market_data_mcp_secrets.json")
s = json.loads(secret.read_text(encoding="utf-8"))
pro = ts.pro_api(s.get("TUSHARE_TOKEN") or s.get("TUSHARE_PRO_TOKEN"))
groups = {
    "AI光通信": ["300308.SZ", "300502.SZ", "300394.SZ"],
    "铜资源": ["603993.SH", "601899.SH", "600362.SH"],
    "PCB": ["002463.SZ", "300476.SZ", "600183.SH"],
    "低空经济": ["002085.SZ", "000099.SZ", "603085.SH", "603197.SH"],
}
meta = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name,industry").set_index("ts_code")
rows = []
for group, codes in groups.items():
    for code in codes:
        fin = pro.fina_indicator(ts_code=code, start_date="20250101", end_date="20261016", fields="ts_code,ann_date,end_date,roe,grossprofit_margin,netprofit_yoy,tr_yoy,ocf_to_or")
        income = pro.income(ts_code=code, start_date="20250101", end_date="20261016", fields="ts_code,ann_date,end_date,report_type,revenue,n_income_attr_p")
        cash = pro.cashflow(ts_code=code, start_date="20250101", end_date="20261016", fields="ts_code,ann_date,end_date,report_type,n_cashflow_act")
        prices = pro.daily(ts_code=code, start_date="20240101", end_date="20261016", fields="ts_code,trade_date,open,high,low,close,vol")
        def latest(df, period):
            if df.empty: return None
            d = df[(df.end_date == period) & (df.ann_date <= "20261016")].copy()
            if "report_type" in d.columns:
                d = d[d.report_type.astype(str) == "1"]
            return None if d.empty else d.sort_values("ann_date").iloc[-1]
        f = latest(fin, "20260630")
        inc = latest(income, "20260630")
        inc_prior = latest(income, "20250630")
        cf = latest(cash, "20260630")
        prices = prices.sort_values("trade_date").reset_index(drop=True)
        if prices.empty: continue
        close = float(prices.close.iloc[-1])
        prior120 = prices.iloc[-121:-1]
        last20 = prices.iloc[-20:]
        def val(r, col):
            if r is None: return None
            v = r.get(col)
            return round(float(v), 2) if v is not None and str(v) != "nan" else None
        net = val(inc, "n_income_attr_p")
        cfv = val(cf, "n_cashflow_act")
        rows.append({
            "group": group, "code": code, "name": meta.loc[code, "name"] if code in meta.index else None,
            "close": round(close, 2), "ret20": round(100*(close / float(prices.close.iloc[-21]) - 1), 2) if len(prices)>=21 else None,
            "ma20": round(float(last20.close.mean()), 2),
            "prior120_high": round(float(prior120.high.max()), 2) if not prior120.empty else None,
            "two_year_high": round(float(prices.high.max()), 2),
            "vol_mult_5": round(float(prices.vol.iloc[-1]) / float(prices.vol.iloc[-6:-1].mean()), 2),
            "roe_h1": val(f, "roe"), "gross_margin_h1": val(f, "grossprofit_margin"),
            "revenue_yoy_h1": val(f, "tr_yoy"), "profit_yoy_h1": val(f, "netprofit_yoy"),
            "revenue_h1": val(inc, "revenue"), "profit_h1": net,
            "profit_h1_prior": val(inc_prior, "n_income_attr_p"),
            "ocf_h1": cfv,
            "ocf_to_profit": round(cfv/net,2) if cfv is not None and net is not None and net != 0 else None,
        })
Path("audit_wj_c_20261019_output.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
print(len(rows))

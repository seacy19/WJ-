import json
from pathlib import Path

import pandas as pd
import tushare as ts


DATE = "20260716"
START = "20260501"
SECRET_FILE = Path(
    r"C:\Users\seacy\.codex\visualizations\2026\07\11"
    r"\019f51ce-cedd-79c2-a614-e0177210b81a\market_data_mcp"
    r"\.market_data_mcp_secrets.json"
)


def token():
    data = json.loads(SECRET_FILE.read_text(encoding="utf-8"))
    return data.get("TUSHARE_TOKEN") or data.get("TUSHARE_PRO_TOKEN")


def nums(df, columns):
    for column in columns:
        if column in df:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def is_limit_up(row):
    name = str(row.get("name", ""))
    code = str(row["ts_code"])
    pct = float(row["pct_chg"])
    if "ST" in name.upper():
        return pct >= 4.8
    if code.startswith(("300", "301", "688")):
        return pct >= 19.5
    if code.endswith(".BJ"):
        return pct >= 29.5
    return pct >= 9.5


def main():
    pro = ts.pro_api(token())
    daily_fields = "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
    basic_fields = "ts_code,trade_date,turnover_rate,turnover_rate_f,volume_ratio,pe_ttm,pb,total_mv,circ_mv"
    stock_fields = "ts_code,symbol,name,area,industry,market,list_date"

    daily = nums(
        pro.daily(trade_date=DATE, fields=daily_fields),
        ["open", "high", "low", "close", "pre_close", "pct_chg", "vol", "amount"],
    )
    basic = nums(
        pro.daily_basic(trade_date=DATE, fields=basic_fields),
        ["turnover_rate", "turnover_rate_f", "volume_ratio", "pe_ttm", "pb", "total_mv", "circ_mv"],
    )
    stocks = pro.stock_basic(exchange="", list_status="L", fields=stock_fields)
    data = daily.merge(basic, on=["ts_code", "trade_date"], how="left").merge(stocks, on="ts_code", how="left")
    data["amount_yi"] = data["amount"] / 100000
    data["circ_mv_yi"] = data["circ_mv"] / 10000
    data["limit_up"] = data.apply(is_limit_up, axis=1)

    clean = data[
        ~data["name"].fillna("").str.contains("ST|退", case=False, regex=True)
    ].copy()
    limits = clean[clean["limit_up"]].sort_values("amount", ascending=False)
    liquid = clean[clean["amount_yi"] >= 5].copy()
    strong = liquid[(liquid["pct_chg"] >= 3) & ~liquid["limit_up"]].sort_values(
        ["pct_chg", "amount"], ascending=False
    )

    prior_names = [
        "普洛药业", "沪电股份", "古井贡酒", "巨人网络", "通富微电",
        "生益科技", "凯莱英", "昭衍新药", "华大九天", "峰岹科技",
    ]
    prior = data[data["name"].isin(prior_names)].sort_values("name")

    history_frames = []
    for day in pd.date_range("2026-05-01", "2026-07-16", freq="B"):
        ds = day.strftime("%Y%m%d")
        frame = pro.daily(trade_date=ds, fields=daily_fields)
        if not frame.empty:
            history_frames.append(frame)
    history = nums(
        pd.concat(history_frames, ignore_index=True),
        ["open", "high", "low", "close", "pre_close", "pct_chg", "vol", "amount"],
    )
    history = history.sort_values(["ts_code", "trade_date"])
    history["ma5"] = history.groupby("ts_code")["close"].transform(lambda s: s.rolling(5).mean())
    history["ma10"] = history.groupby("ts_code")["close"].transform(lambda s: s.rolling(10).mean())
    history["ma20"] = history.groupby("ts_code")["close"].transform(lambda s: s.rolling(20).mean())
    history["close_5ago"] = history.groupby("ts_code")["close"].shift(5)
    history["close_10ago"] = history.groupby("ts_code")["close"].shift(10)
    history["close_20ago"] = history.groupby("ts_code")["close"].shift(20)
    history["ret5"] = (history["close"] / history["close_5ago"] - 1) * 100
    history["ret10"] = (history["close"] / history["close_10ago"] - 1) * 100
    history["ret20"] = (history["close"] / history["close_20ago"] - 1) * 100
    history["high20"] = history.groupby("ts_code")["high"].transform(lambda s: s.rolling(20).max())
    history["low20"] = history.groupby("ts_code")["low"].transform(lambda s: s.rolling(20).min())
    metrics = history[history["trade_date"] == DATE][
        ["ts_code", "ma5", "ma10", "ma20", "ret5", "ret10", "ret20", "high20", "low20"]
    ]

    candidates = pd.concat([limits.head(50), strong.head(80)], ignore_index=True)
    candidates = candidates.drop_duplicates("ts_code").merge(metrics, on="ts_code", how="left")
    candidates["score"] = (
        candidates["pct_chg"].clip(-10, 20)
        + candidates["volume_ratio"].fillna(1).clip(0, 5) * 2
        + (candidates["close"] >= candidates["ma5"]).fillna(False) * 2
        + (candidates["close"] >= candidates["ma20"]).fillna(False) * 2
        - candidates["ret20"].fillna(0).clip(lower=0) * 0.08
    )
    candidates = candidates.sort_values(["score", "amount"], ascending=False)

    cols = [
        "ts_code", "name", "industry", "market", "open", "high", "low", "close",
        "pct_chg", "amount_yi", "turnover_rate", "volume_ratio", "pe_ttm", "pb",
        "circ_mv_yi", "ma5", "ma10", "ma20", "ret5", "ret10", "ret20", "high20", "low20",
    ]
    focus_names = [
        "普洛药业", "古井贡酒", "巨人网络", "昭衍新药", "片仔癀", "同仁堂",
        "鹭燕医药", "博瑞医药", "光线传媒", "上海电影", "儒意电影",
        "沪电股份", "生益科技", "景旺电子", "逸豪新材", "美格智能",
        "通富微电", "华大九天", "峰岹科技", "安迪苏", "云赛智联",
    ]
    focus = data[data["name"].isin(focus_names)].merge(metrics, on="ts_code", how="left")
    indices = []
    for code in ["000001.SH", "399001.SZ", "399006.SZ", "000688.SH"]:
        idx = pro.index_daily(ts_code=code, start_date=DATE, end_date=DATE,
                              fields="ts_code,trade_date,close,pct_chg,amount")
        if not idx.empty:
            indices.extend(idx.to_dict("records"))

    out = {
        "breadth": {
            "up": int((daily["pct_chg"] > 0).sum()),
            "down": int((daily["pct_chg"] < 0).sum()),
            "flat": int((daily["pct_chg"] == 0).sum()),
            "amount_yi": round(float(daily["amount"].sum() / 100000)),
            "limit_up": int(clean["limit_up"].sum()),
            "up5": int((clean["pct_chg"] >= 5).sum()),
            "down5": int((clean["pct_chg"] <= -5).sum()),
        },
        "limit_industries": limits.groupby("industry").size().sort_values(ascending=False).head(20).to_dict(),
        "indices": indices,
        "prior": prior[
            ["ts_code", "name", "industry", "open", "high", "low", "close", "pct_chg",
             "amount_yi", "turnover_rate", "volume_ratio", "pe_ttm", "pb"]
        ].to_dict("records"),
        "focus": focus[cols].sort_values("name").to_dict("records"),
        "limits": limits[cols[:15]].head(35).to_dict("records"),
        "candidates": candidates[cols].head(25).to_dict("records"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=lambda x: None if pd.isna(x) else x))


if __name__ == "__main__":
    main()

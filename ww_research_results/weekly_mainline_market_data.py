"""Build a point-in-time-bounded weekly A-share market snapshot from TuShare.

The TuShare token is read only from TUSHARE_TOKEN in the local process
environment. It is never written to the output file or printed.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests


API_URL = "https://api.tushare.pro"
INDEX_CODES = {
    "000001.SH": "上证综指",
    "000300.SH": "沪深300",
    "000905.SH": "中证500",
    "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",
}


def call_tushare(token: str, api_name: str, params: dict[str, str], fields: str) -> list[dict[str, Any]]:
    response = requests.post(
        API_URL,
        json={
            "api_name": api_name,
            "token": token,
            "params": params,
            "fields": fields,
            "limit": 6000,
        },
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        # Deliberately omit request secrets and full request bodies from errors.
        raise RuntimeError(
            f"TuShare {api_name} failed: code={payload.get('code')}, msg={payload.get('msg')}"
        )
    data = payload.get("data") or {}
    columns = data.get("fields") or []
    return [dict(zip(columns, row)) for row in (data.get("items") or [])]


def resolve_dates(token: str, week_start: date, week_end: date) -> tuple[date, list[date]]:
    calendar_start = (week_start - timedelta(days=14)).strftime("%Y%m%d")
    rows = call_tushare(
        token,
        "trade_cal",
        {
            "exchange": "SSE",
            "start_date": calendar_start,
            "end_date": week_end.strftime("%Y%m%d"),
        },
        "exchange,cal_date,is_open",
    )
    open_dates = sorted(
        date.fromisoformat(row["cal_date"][:4] + "-" + row["cal_date"][4:6] + "-" + row["cal_date"][6:8])
        for row in rows
        if str(row.get("is_open")) == "1"
    )
    week_dates = [day for day in open_dates if week_start <= day <= week_end]
    previous_dates = [day for day in open_dates if day < week_start]
    if not week_dates:
        raise ValueError("The selected week contains no SSE trading days.")
    if not previous_dates:
        raise ValueError("Could not find a previous SSE trading day for the baseline.")
    return previous_dates[-1], week_dates


def fetch_daily(token: str, day: date) -> list[dict[str, Any]]:
    return call_tushare(
        token,
        "daily",
        {"trade_date": day.strftime("%Y%m%d")},
        "ts_code,trade_date,close,pct_chg,amount",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week-start", required=True, help="Monday, YYYY-MM-DD")
    parser.add_argument("--week-end", required=True, help="Sunday or last calendar day, YYYY-MM-DD")
    parser.add_argument("--output", help="Output JSON path; defaults to ww_research_results/market_data_<ISO-week>.json")
    parser.add_argument("--force", action="store_true", help="Replace an existing output snapshot")
    args = parser.parse_args()

    week_start = date.fromisoformat(args.week_start)
    week_end = date.fromisoformat(args.week_end)
    if week_start.weekday() != 0:
        raise ValueError("--week-start must be a Monday.")
    if week_end < week_start or week_end > week_start + timedelta(days=6):
        raise ValueError("--week-end must fall in the same Monday-to-Sunday week.")
    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        raise RuntimeError("Set TUSHARE_TOKEN in the local process environment; do not put it in a file or command argument.")

    baseline_date, week_dates = resolve_dates(token, week_start, week_end)
    observation_dates = [baseline_date, *week_dates]
    rows_by_date: dict[str, list[dict[str, Any]]] = {}
    for day in observation_dates:
        rows_by_date[day.isoformat()] = fetch_daily(token, day)

    maps = {
        day: {row["ts_code"]: row for row in rows}
        for day, rows in rows_by_date.items()
    }
    complete_codes = set.intersection(*(set(rows) for rows in maps.values()))
    weekly_returns: list[float] = []
    for code in complete_codes:
        growth = 1.0
        valid = True
        for day in week_dates:
            raw_return = maps[day.isoformat()][code].get("pct_chg")
            if raw_return is None:
                valid = False
                break
            growth *= 1.0 + float(raw_return) / 100.0
        if valid:
            weekly_returns.append((growth - 1.0) * 100.0)
    if not weekly_returns:
        raise RuntimeError("No stocks have a complete baseline and weekly return series.")

    index_results: dict[str, dict[str, Any]] = {}
    for code, name in INDEX_CODES.items():
        history = call_tushare(
            token,
            "index_daily",
            {
                "ts_code": code,
                "start_date": baseline_date.strftime("%Y%m%d"),
                "end_date": week_dates[-1].strftime("%Y%m%d"),
            },
            "ts_code,trade_date,close,pct_chg",
        )
        by_day = {row["trade_date"]: row for row in history}
        start_key = baseline_date.strftime("%Y%m%d")
        end_key = week_dates[-1].strftime("%Y%m%d")
        if start_key not in by_day or end_key not in by_day:
            index_results[code] = {"name": name, "status": "missing_boundary_close"}
            continue
        start_close = float(by_day[start_key]["close"])
        end_close = float(by_day[end_key]["close"])
        index_results[code] = {
            "name": name,
            "start_close": start_close,
            "end_close": end_close,
            "weekly_return_pct": round((end_close / start_close - 1.0) * 100.0, 6),
        }

    week_number = week_start.isocalendar()
    week_id = f"{week_number.year}-W{week_number.week:02d}"
    snapshot = {
        "schema_version": 1,
        "week_id": week_id,
        "week_start": week_start.isoformat(),
        "week_end_calendar_date": week_end.isoformat(),
        "trading_dates": [day.isoformat() for day in week_dates],
        "baseline_trade_date": baseline_date.isoformat(),
        "information_cutoff": f"{week_dates[-1].isoformat()} 15:00:00+08:00",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "TuShare Pro",
        "secret_saved": False,
        "request_row_counts": {day: len(rows) for day, rows in rows_by_date.items()},
        "market_breadth": {
            "sample_rule": "A-share codes with a bar on the previous open day and every trading day in the selected week; compound pct_chg; exclude incomplete observations",
            "complete_stock_count": len(weekly_returns),
            "median_weekly_return_pct": round(statistics.median(weekly_returns), 6),
            "positive_share_pct": round(100.0 * sum(value > 0 for value in weekly_returns) / len(weekly_returns), 6),
            "negative_share_pct": round(100.0 * sum(value < 0 for value in weekly_returns) / len(weekly_returns), 6),
        },
        "indices": index_results,
        "limitations": [
            "Stock returns are price returns based on daily pct_chg, not dividend-reinvested total returns.",
            "Suspended stocks or codes missing any observation are excluded from the breadth sample.",
            "This snapshot does not infer themes or industry rankings; historical taxonomy must be version-checked separately.",
        ],
    }

    output = Path(args.output) if args.output else Path(__file__).with_name(f"market_data_{week_id}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not args.force:
        raise FileExistsError(f"Refusing to overwrite existing snapshot: {output}. Use --force only after reviewing the prior version.")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent, delete=False, newline="\n") as handle:
        json.dump(snapshot, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(output)
    print(json.dumps({"week_id": week_id, "output": str(output.resolve()), "stock_count": len(weekly_returns), "market_breadth": snapshot["market_breadth"], "indices": index_results}, ensure_ascii=False))


if __name__ == "__main__":
    main()

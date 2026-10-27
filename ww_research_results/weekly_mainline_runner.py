"""Weekly helper: create the prior completed week's market snapshot and research queue."""

from __future__ import annotations

import json
import csv
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "ww_research_results"
SNAPSHOT_SCRIPT = RESULTS / "weekly_mainline_market_data.py"
QUEUE_DIR = RESULTS / "weekly_mainline_pending"


def main() -> int:
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    week_start = this_monday - timedelta(days=7)
    week_end = week_start + timedelta(days=6)
    snapshot_path = RESULTS / f"market_data_{week_start.isocalendar().year}-W{week_start.isocalendar().week:02d}.json"

    command = [
        sys.executable,
        str(SNAPSHOT_SCRIPT),
        "--week-start",
        week_start.isoformat(),
        "--week-end",
        week_end.isoformat(),
    ]
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode != 0 or not snapshot_path.exists():
        return result.returncode or 1

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if not snapshot.get("trading_dates"):
        print(f"{snapshot['week_id']} 没有A股交易日（可能为整周休市）；不创建研究待办。")
        return 0
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    trading_dates = snapshot.get("trading_dates", [])
    if not trading_dates:
        return 1
    week_id = snapshot["week_id"]
    pending_path = QUEUE_DIR / f"{week_id}.md"
    pending_path.write_text(
        "\n".join(
            [
                f"# {week_id} 周度主线研究待办",
                "",
                f"- 交易日：{trading_dates[0]} 至 {trading_dates[-1]}（共{len(trading_dates)}日）",
                f"- 信息截止：{snapshot['information_cutoff']}",
                f"- 行情快照：../{snapshot_path.name}",
                f"- 全市场完整样本：{snapshot['market_breadth']['complete_stock_count']}只；中位收益{snapshot['market_breadth']['median_weekly_return_pct']:.3f}%；上涨占比{snapshot['market_breadth']['positive_share_pct']:.2f}%",
                "- 待人工研究：按截止时点搜集政策、产业与公司公告；核对需求、利润落点、竞争壁垒及主题成员的历史有效性。",
                "- 明确区分候选方向与确认主线；记录已计价预期、反证和下一周观察点。",
                "- 不使用截止时间之后发布的信息解释当周行情。",
                "- 当前自动化只生成行情快照和研究待办；主线搜索、来源核验及报告撰写仍须人工复核。",
                "",
            ]
        ),
        encoding="utf-8",
    )

    backlog_path = RESULTS / "weekly_mainline_10y_backlog.csv"
    with backlog_path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    updated = False
    for row in rows:
        if row.get("week_id") == week_id:
            row["status"] = "行情快照与研究待办已自动生成，等待人工主线复盘"
            updated = True
            break
    if not updated:
        rows.append(
            {
                "week_id": week_id,
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "status": "行情快照与研究待办已自动生成，等待人工主线复盘",
                "mainline": "",
                "evidence_links": "",
                "after_week_validation": (
                    f"TuShare快照：{snapshot['market_breadth']['complete_stock_count']}只完整样本，"
                    f"中位收益{snapshot['market_breadth']['median_weekly_return_pct']:.3f}%，"
                    f"上涨占比{snapshot['market_breadth']['positive_share_pct']:.2f}%。"
                ),
            }
        )
    with backlog_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

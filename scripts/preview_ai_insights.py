"""
週次レビューのAI分析（良かったこと／意識するといいこと）を、
アーカイブファイルを一切書き換えずにターミナルへプレビュー表示する確認用スクリプト。

過去の週を含めてAIの出力トーン・精度を確認したいときに使う。
比較用に、旧・閾値ベース生成の結果もあわせて表示する。

使い方:
  python scripts/preview_ai_insights.py --week 12
  python scripts/preview_ai_insights.py --start 2026-05-01 --end 2026-05-07
  python scripts/preview_ai_insights.py --all
  python scripts/preview_ai_insights.py --week 12 --show-context   # AIに送った生データも表示
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_weekly_review as gwr  # noqa: E402


def _week_range_from_archive(week_num: int) -> tuple[date, date]:
    path = gwr.ARCHIVE_DIR / f"weekly_review_week{week_num}.md"
    if not path.exists():
        raise SystemExit(f"アーカイブが見つかりません: {path}")
    text = path.read_text(encoding="utf-8")
    m = re.search(r"## (\d{4}-\d{2}-\d{2}) → (\d{4}-\d{2}-\d{2})", text)
    if not m:
        raise SystemExit(f"日付範囲を読み取れませんでした: {path}")
    return date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))


def _all_weeks() -> list[tuple[int, date, date]]:
    weeks = []
    for f in sorted(gwr.ARCHIVE_DIR.glob("weekly_review_week*.md")):
        m = re.search(r"weekly_review_week(\d+)\.md", f.name)
        if not m:
            continue
        week_num = int(m.group(1))
        start, end = _week_range_from_archive(week_num)
        weeks.append((week_num, start, end))
    return sorted(weeks, key=lambda w: w[0])


def preview_week(week_num: int, start: date, end: date, show_context: bool) -> None:
    w_df = gwr.load_weight(start, end)
    bp_df = gwr.load_bp(start, end)
    bp_morning = bp_df[bp_df["time"] == "morning"]
    bp_night = bp_df[bp_df["time"] == "night"]
    meals = gwr.load_meals(start, end)
    meals_text = gwr.load_meals_text(start, end)
    exercise = gwr.load_exercise(start, end)
    record_days = (end - start).days + 1

    prev_avg = gwr.load_prev_week_avg(start)
    w_diff = (w_df["weight"].mean() - prev_avg) if (not w_df.empty and prev_avg is not None) else None

    print(f"\n{'=' * 60}")
    print(f"Week {week_num}: {start} → {end}")
    print("=" * 60)

    if show_context:
        print("\n--- AIに送る生データ ---")
        print(gwr._build_ai_context(start, end, w_df, bp_morning, bp_night, meals, meals_text, exercise, w_diff))

    try:
        ai_result = gwr.generate_ai_insights(
            start, end, w_df, bp_morning, bp_night, meals, meals_text, exercise, w_diff
        )
    except Exception as e:
        print(f"\n[AI分析エラー] {e}")
        ai_result = None

    if ai_result is None:
        print("\n[AI分析] 失敗またはAPIキー未設定のため結果なし（ANTHROPIC_API_KEYを確認してください）")
    else:
        analysis_sec, good_sec, mindful_sec, strategy_sec = ai_result
        print("\n--- AI生成: 分析（総括） ---")
        print(analysis_sec)
        print("\n--- AI生成: 良かったこと ---")
        print(good_sec)
        print("\n--- AI生成: 意識するといいこと ---")
        print(mindful_sec)
        print("\n--- AI生成: 来週の作戦 ---")
        print(strategy_sec)

    old_analysis = gwr.build_analysis(w_df, bp_morning, bp_night, meals, exercise, w_diff)
    old_good = gwr.build_good_points(w_df, bp_morning, meals, exercise, w_diff)
    old_mindful = gwr.build_mindful_points(w_df, bp_morning, meals, exercise, record_days, w_diff)
    old_strategy = gwr.build_next_strategy(w_df, bp_morning, meals, exercise, w_diff)
    print("\n--- （参考）旧・閾値ベース生成: 分析（総括） ---")
    print(old_analysis)
    print("\n--- （参考）旧・閾値ベース生成: 良かったこと ---")
    print(old_good)
    print("\n--- （参考）旧・閾値ベース生成: 意識するといいこと ---")
    print(old_mindful)
    print("\n--- （参考）旧・閾値ベース生成: 来週の作戦 ---")
    print(old_strategy)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--week", type=int, help="アーカイブ済みの週番号を指定（例: 12）")
    parser.add_argument("--start", type=str, help="開始日 YYYY-MM-DD（--endとセットで使用）")
    parser.add_argument("--end", type=str, help="終了日 YYYY-MM-DD（--startとセットで使用）")
    parser.add_argument("--all", action="store_true", help="アーカイブ済みの全週をまとめてプレビュー")
    parser.add_argument("--show-context", action="store_true", help="AIに渡す生データも表示する")
    args = parser.parse_args()

    if args.all:
        for week_num, start, end in _all_weeks():
            preview_week(week_num, start, end, args.show_context)
        return

    if args.week is not None:
        start, end = _week_range_from_archive(args.week)
        preview_week(args.week, start, end, args.show_context)
        return

    if args.start and args.end:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end)
        preview_week(0, start, end, args.show_context)
        return

    parser.error("--week か --all か、--start/--end のいずれかを指定してください")


if __name__ == "__main__":
    main()

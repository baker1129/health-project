"""任意期間のカスタムレポートを生成するスクリプト。

週次レビュー（logs/reviews/weekly_review.md・archive/weekly/）とは完全に別の
出力先（logs/reviews/custom/）に保存し、水曜日起点の週次サイクルには一切
影響しない。データ読み込みはgenerate_weekly_review.pyの読み取り専用関数を
再利用するが、週次専用の判定（前週比・最低目標など）は行わず、同じ日数の
直前期間との比較に一般化している。

使い方: python scripts/generate_custom_review.py --start 2026-05-01 --end 2026-05-31
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from goals import GOALS
from generate_weekly_review import load_weight, load_bp, load_meals, load_exercise, bp_judge

ROOT       = Path(__file__).resolve().parents[1]
CUSTOM_DIR = ROOT / "logs" / "reviews" / "custom"


def build_custom_review(start: date, end: date) -> str:
    period_days = (end - start).days + 1

    w_df  = load_weight(start, end)
    bp_df = load_bp(start, end)
    bp_morning = bp_df[bp_df["time"] == "morning"]
    bp_night   = bp_df[bp_df["time"] == "night"]
    meals    = load_meals(start, end)
    exercise = load_exercise(start, end)

    # 体重
    weight_lines = []
    if w_df.empty:
        weight_lines.append("- データなし")
    else:
        w_avg = w_df["weight"].mean()

        prev_start = start - timedelta(days=period_days)
        prev_end   = start - timedelta(days=1)
        prev_df    = load_weight(prev_start, prev_end)
        if not prev_df.empty:
            diff = w_avg - prev_df["weight"].mean()
            weight_lines.append(f"- 期間平均: **{w_avg:.1f} kg**（前の同期間比 {diff:+.1f} kg）")
        else:
            weight_lines.append(f"- 期間平均: **{w_avg:.1f} kg**（前の同期間データなし）")

        weight_lines.append(f"- 記録日数: {len(w_df)}日 / {period_days}日中")

        if not w_df["bodyfat"].isna().all():
            bf = w_df["bodyfat"].dropna()
            weight_lines.append(f"- 体脂肪率: {bf.min():.1f}〜{bf.max():.1f}%（平均 {bf.mean():.1f}%）")

        # 目標達成は期間平均で判定する（週次レビューと同じ考え方）
        for target_kg, label in GOALS:
            if w_avg <= target_kg:
                weight_lines.append(f"- ✅ {label}（{target_kg} kg）: 達成済み（期間平均）")
            else:
                weight_lines.append(f"- {label}（{target_kg} kg）まで: あと **{w_avg - target_kg:.1f} kg**（期間平均）")
                break

    # 血圧
    def summarize(df, label: str) -> str:
        if df.empty:
            return f"- {label}平均: データなし"
        avg_sys = df["systolic"].mean()
        avg_dia = df["diastolic"].mean()
        return f"- {label}平均: **{avg_sys:.1f} / {avg_dia:.1f} mmHg**（{bp_judge(avg_sys, avg_dia)}）"

    bp_lines = [summarize(bp_morning, "朝"), summarize(bp_night, "夜")]

    # 食事
    meals_lines = [
        f"- 外食: {meals['eating_out']}回",
        f"- 夜食: {meals['night_snack_days']}日",
        f"- 間食: {meals['snack_days']}日",
        f"- 朝食なし: {meals['no_breakfast_days']}日",
    ]

    # 運動
    exercise_lines = [f"- {e}" for e in exercise] if exercise else ["- 記録なし"]

    weight_md   = "\n".join(weight_lines)
    bp_md       = "\n".join(bp_lines)
    meals_md    = "\n".join(meals_lines)
    exercise_md = "\n".join(exercise_lines)

    return f"""# Custom Review

## {start} → {end}（{period_days}日間）

### 体重
{weight_md}

---

### 血圧
{bp_md}

---

### 食事
{meals_md}

---

### 運動
{exercise_md}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="任意期間のカスタムレポートを生成する")
    parser.add_argument("--start", required=True, help="開始日 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="終了日 YYYY-MM-DD")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end   = date.fromisoformat(args.end)
    if start > end:
        raise SystemExit(f"開始日({start})が終了日({end})より後になっています。")

    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    review = build_custom_review(start, end)
    out_path = CUSTOM_DIR / f"review_{start}_to_{end}.md"
    out_path.write_text(review, encoding="utf-8")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()

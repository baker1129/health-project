"""
過去のアーカイブ済み週次レビュー（logs/reviews/archive/weekly/*.md）の
「分析（総括）」「良かったこと」「意識するといいこと」「来週の作戦」セクションを、
AI生成（generate_ai_insights）で置き換える一回限りのバッチスクリプト。

体重・血圧・食事・運動など、他のセクションはそのまま変更しない。
旧フォーマットの「### ダメだったこと」ヘッダーも新ヘッダー「### 意識するといいこと」に統一する。

使い方:
  python scripts/regenerate_archive_insights.py            # 全アーカイブ対象
  python scripts/regenerate_archive_insights.py --week 12   # 特定の週だけ
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

# 「### 分析（総括）」からファイル末尾までを丸ごと置き換える
# （分析（総括）・良かったこと・意識するといいこと・来週の作戦 の4セクション分。
#  「### 最低目標」セクションは廃止済みのため、来週の作戦がファイル末尾になる）。
# 旧ヘッダー（### ダメだったこと）・新ヘッダー（### 意識するといいこと）どちらの
# アーカイブファイルにもマッチする。
SECTION_RE = re.compile(
    r"### 分析（総括）\n.*\Z",
    re.DOTALL,
)


def _week_info(path: Path) -> tuple[int, date, date]:
    m = re.search(r"weekly_review_week(\d+)\.md", path.name)
    if not m:
        raise ValueError(f"週番号を抽出できません: {path.name}")
    week_num = int(m.group(1))
    text = path.read_text(encoding="utf-8")
    dm = re.search(r"## (\d{4}-\d{2}-\d{2}) → (\d{4}-\d{2}-\d{2})", text)
    if not dm:
        raise ValueError(f"日付範囲を抽出できません: {path.name}")
    return week_num, date.fromisoformat(dm.group(1)), date.fromisoformat(dm.group(2))


def regenerate_one(path: Path) -> str:
    week_num, start, end = _week_info(path)
    text = path.read_text(encoding="utf-8")

    w_df = gwr.load_weight(start, end)
    bp_df = gwr.load_bp(start, end)
    bp_morning = bp_df[bp_df["time"] == "morning"]
    bp_night = bp_df[bp_df["time"] == "night"]
    meals = gwr.load_meals(start, end)
    meals_text = gwr.load_meals_text(start, end)
    exercise = gwr.load_exercise(start, end)
    prev_avg = gwr.load_prev_week_avg(start)
    w_diff = (w_df["weight"].mean() - prev_avg) if (not w_df.empty and prev_avg is not None) else None

    try:
        ai_result = gwr.generate_ai_insights(
            start, end, w_df, bp_morning, bp_night, meals, meals_text, exercise, w_diff
        )
    except Exception as e:
        return f"[SKIP] Week {week_num} ({path.name}): AI呼び出しエラー: {e}"

    if ai_result is None:
        return f"[SKIP] Week {week_num} ({path.name}): AI生成に失敗（APIキー未設定など）"

    analysis_sec, good_sec, mindful_sec, strategy_sec = ai_result

    if not SECTION_RE.search(text):
        return f"[SKIP] Week {week_num} ({path.name}): 置き換え対象のセクションが見つかりませんでした"

    new_block = (
        f"### 分析（総括）\n{analysis_sec}\n\n---\n\n"
        f"### 良かったこと\n{good_sec}\n\n"
        f"### 意識するといいこと\n{mindful_sec}\n\n"
        f"---\n\n### 来週の作戦\n{strategy_sec}\n"
    )
    new_text = SECTION_RE.sub(lambda m: new_block, text, count=1)
    path.write_text(new_text, encoding="utf-8")
    return f"[OK] Week {week_num} ({path.name}): 更新しました"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--week", type=int, help="特定の週番号のみ対象にする")
    args = parser.parse_args()

    if args.week is not None:
        targets = [gwr.ARCHIVE_DIR / f"weekly_review_week{args.week}.md"]
    else:
        targets = sorted(
            gwr.ARCHIVE_DIR.glob("weekly_review_week*.md"),
            key=lambda p: int(re.search(r"\d+", p.stem).group()),
        )

    results = []
    for path in targets:
        if not path.exists():
            results.append(f"[SKIP] {path.name}: ファイルなし")
            continue
        result = regenerate_one(path)
        print(result)
        results.append(result)

    ok = sum(1 for r in results if r.startswith("[OK]"))
    print(f"\n完了: {ok}/{len(results)} 件を更新しました")


if __name__ == "__main__":
    main()

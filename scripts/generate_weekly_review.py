"""
水曜日の夜血圧入力をトリガーに週次レビューを生成・アーカイブするスクリプト。
- archive/weekly/weekly_review_weekN.md にデータ分析付きで保存
- logs/reviews/weekly_review.md を次週テンプレートに差し替え
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

from goals import GOALS

ROOT         = Path(__file__).resolve().parents[1]
WEIGHT_CSV   = ROOT / "logs" / "daily" / "weight.csv"
BP_CSV       = ROOT / "logs" / "daily" / "blood_pressure.csv"
MEALS_MD     = ROOT / "logs" / "lifestyle" / "meals.md"
EXERCISE_MD  = ROOT / "logs" / "lifestyle" / "exercise.md"
REVIEWS_DIR  = ROOT / "logs" / "reviews"
ARCHIVE_DIR  = REVIEWS_DIR / "archive" / "weekly"
CURRENT_FILE = REVIEWS_DIR / "weekly_review.md"

JST = timezone(timedelta(hours=9))
FORCE = "--force" in sys.argv


# ---------------------------------------------------------------------------
# 実行条件チェック
# ---------------------------------------------------------------------------

def should_run() -> bool:
    if FORCE:
        return True
    now = datetime.now(JST)
    today = now.date()

    # 直近の水曜日（深夜越え対応：今日が水曜なら今日、それ以外は遡る）
    days_since_wed = (today.weekday() - 2) % 7
    last_wednesday = today - timedelta(days=days_since_wed)

    wed_str = last_wednesday.isoformat()
    df = pd.read_csv(BP_CSV)
    has_night = not df[(df["date"] == wed_str) & (df["time"] == "night")].empty
    if not has_night:
        print(f"直近の水曜日（{wed_str}）の夜血圧がまだ入力されていません。スキップします。")
        return False

    # 今週分のレビューがすでに生成済みならスキップ（無駄なコミット防止）
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    for f in sorted(ARCHIVE_DIR.glob("weekly_review_week*.md")):
        content = f.read_text(encoding="utf-8")
        dm = re.search(r"## (\d{4}-\d{2}-\d{2}) → (\d{4}-\d{2}-\d{2})", content)
        if dm and date.fromisoformat(dm.group(2)) == last_wednesday:
            print(f"直近の水曜日（{wed_str}）のレビューはすでに生成済みです。スキップします。")
            return False

    return True


# ---------------------------------------------------------------------------
# 週番号・日付範囲の決定
# ---------------------------------------------------------------------------

def get_week_info() -> tuple[int, date, date, bool]:
    """(week_num, start, end, is_update) を返す。
    is_update=True のとき既存アーカイブの上書き更新（テンプレートは差し替えない）。
    """
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(JST).date()

    # 週終了日は「直近の水曜日」（今日が水曜なら今日、それ以外は遡る）
    days_since_wed = (today.weekday() - 2) % 7
    week_end = today - timedelta(days=days_since_wed)

    existing = sorted(ARCHIVE_DIR.glob("weekly_review_week*.md"))
    latest_num   = 0
    latest_start: date | None = None
    latest_end:   date | None = None

    for f in existing:
        m = re.match(r"weekly_review_week(\d+)\.md", f.name)
        if not m:
            continue
        n = int(m.group(1))
        content = f.read_text(encoding="utf-8")
        dm = re.search(r"## (\d{4}-\d{2}-\d{2}) → (\d{4}-\d{2}-\d{2})", content)
        if dm and n > latest_num:
            latest_num   = n
            latest_start = date.fromisoformat(dm.group(1))
            latest_end   = date.fromisoformat(dm.group(2))

    if latest_end is None:
        # アーカイブなし → 初回生成（プロジェクト開始日から）
        project_start = date(2026, 4, 29)
        return 1, project_start, week_end, False

    if latest_end == week_end:
        # 同週の上書き更新（当週データが追加されたケース）
        return latest_num, latest_start, week_end, True

    # 新しい週の生成
    return latest_num + 1, latest_end + timedelta(days=1), week_end, False


# ---------------------------------------------------------------------------
# データ読み込み
# ---------------------------------------------------------------------------

def load_weight(start: date, end: date) -> pd.DataFrame:
    df = pd.read_csv(WEIGHT_CSV)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
    df["bodyfat"] = pd.to_numeric(df.get("bodyfat", pd.NA), errors="coerce")
    return df[(df["date"] >= start) & (df["date"] <= end)].sort_values("date")


def load_bp(start: date, end: date) -> pd.DataFrame:
    df = pd.read_csv(BP_CSV)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    for col in ["systolic1", "diastolic1", "pulse1", "systolic2", "diastolic2", "pulse2"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["systolic"]  = (df["systolic1"]  + df["systolic2"])  / 2
    df["diastolic"] = (df["diastolic1"] + df["diastolic2"]) / 2
    df["pulse"]     = (df["pulse1"]     + df["pulse2"])     / 2
    df = df[(df["date"] >= start) & (df["date"] <= end)]
    return df.sort_values(["date", "time"])


def load_meals(start: date, end: date) -> dict:
    if not MEALS_MD.exists():
        return {"eating_out": 0, "night_snack_days": 0, "snack_days": 0, "no_breakfast_days": 0}
    text = MEALS_MD.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    sections = re.split(r"\n(?=## \d{4}-\d{2}-\d{2})", text)
    eating_out, night_snack_days, snack_days, no_breakfast = 0, 0, 0, 0
    for section in sections:
        dm = re.match(r"## (\d{4}-\d{2}-\d{2})", section)
        if not dm:
            continue
        d = date.fromisoformat(dm.group(1))
        if not (start <= d <= end):
            continue
        eo = re.search(r"^外食: (\d+)回", section, re.MULTILINE)
        ns = re.search(r"^夜食: (あり|なし)", section, re.MULTILINE)
        sn = re.search(r"^間食: (あり|なし)", section, re.MULTILINE)
        bf = re.search(r"### 朝\n- なし", section)
        if eo:
            eating_out += int(eo.group(1))
        if ns and ns.group(1) == "あり":
            night_snack_days += 1
        if sn and sn.group(1) == "あり":
            snack_days += 1
        if bf:
            no_breakfast += 1
    return {
        "eating_out": eating_out,
        "night_snack_days": night_snack_days,
        "snack_days": snack_days,
        "no_breakfast_days": no_breakfast,
    }


def load_meals_text(start: date, end: date) -> str:
    """AI分析用に、期間内の食事日記を生データのまま連結して返す。"""
    if not MEALS_MD.exists():
        return ""
    text = MEALS_MD.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    sections = re.split(r"\n(?=## \d{4}-\d{2}-\d{2})", text)
    blocks = []
    for section in sections:
        dm = re.match(r"## (\d{4}-\d{2}-\d{2})", section)
        if not dm:
            continue
        d = date.fromisoformat(dm.group(1))
        if start <= d <= end:
            blocks.append(section.strip())
    return "\n\n".join(blocks)


def load_prev_week_avg(week_start: date) -> float | None:
    """直前7日間（前週）の体重平均。データがなければNone。"""
    prev_start = week_start - timedelta(days=7)
    prev_end   = week_start - timedelta(days=1)
    prev_df = load_weight(prev_start, prev_end)
    return prev_df["weight"].mean() if not prev_df.empty else None


def load_exercise(start: date, end: date) -> list[str]:
    if not EXERCISE_MD.exists():
        return []
    text = EXERCISE_MD.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    sections = re.split(r"\n(?=## \d{4}-\d{2}-\d{2})", text)
    entries = []
    for section in sections:
        dm = re.match(r"## (\d{4}-\d{2}-\d{2})", section)
        if not dm:
            continue
        d = date.fromisoformat(dm.group(1))
        if not (start <= d <= end):
            continue
        lines = [l.strip().lstrip("- ").strip() for l in section.split("\n") if l.strip().startswith("- ")]
        for line in lines:
            if line and line not in ("なし", "特になし"):
                entries.append(f"{d}: {line}")
    return entries


# ---------------------------------------------------------------------------
# 判定ヘルパー
# ---------------------------------------------------------------------------

def bp_judge(sys_val: float, dia_val: float) -> str:
    if sys_val >= 140 or dia_val >= 90:
        return "⚠️ 高め（受診検討）"
    if sys_val >= 130 or dia_val >= 85:
        return "注意（やや高め）"
    return "良好"


# ---------------------------------------------------------------------------
# 各セクション生成
# ---------------------------------------------------------------------------

def build_weight_section(w_df: pd.DataFrame, w_diff: float | None) -> str:
    if w_df.empty:
        return "- データなし"
    w_end = w_df.iloc[-1]["weight"]
    w_avg = w_df["weight"].mean()
    diff_text = f"（前週平均比 {w_diff:+.1f} kg）" if w_diff is not None else "（前週データなし）"
    lines = [
        f"- 週平均: **{w_avg:.1f} kg**{diff_text}",
        f"- 直近の記録: {w_end:.1f} kg（{len(w_df)}日記録）",
    ]
    if not w_df["bodyfat"].isna().all():
        bf_vals = w_df["bodyfat"].dropna()
        lines.append(f"- 体脂肪率: {bf_vals.min():.1f}〜{bf_vals.max():.1f}%（平均 {bf_vals.mean():.1f}%）")
    # 目標達成は週平均で判定（1日だけ一時的に基準を切った場合を達成扱いにしないため）
    for target_kg, label in GOALS:
        if w_avg <= target_kg:
            lines.append(f"- ✅ {label}（{target_kg} kg）: **達成済み**（週平均）")
        else:
            lines.append(f"- {label}（{target_kg} kg）まで: あと **{w_avg - target_kg:.1f} kg**（週平均）")
            break
    else:
        lines.append("- ✅ 全目標達成！最終目標（生活習慣確立）を継続中")
    return "\n".join(lines)


def build_bp_section(bp_morning: pd.DataFrame, bp_night: pd.DataFrame) -> str:
    lines = []

    def summarize(df: pd.DataFrame, label: str) -> str:
        if df.empty:
            return f"- {label}平均: データなし"
        avg_sys = df["systolic"].mean()
        avg_dia = df["diastolic"].mean()
        return f"- {label}平均: **{avg_sys:.1f} / {avg_dia:.1f} mmHg**（{bp_judge(avg_sys, avg_dia)}）"

    lines.append(summarize(bp_morning, "朝"))
    lines.append(summarize(bp_night, "夜"))

    if not bp_morning.empty and not bp_night.empty:
        diff = bp_morning["systolic"].mean() - bp_night["systolic"].mean()
        lines.append(f"- 朝夜差（収縮期）: {diff:+.1f} mmHg")

    # CPAP分析
    if not bp_morning.empty and "memo" in bp_morning.columns:
        on_df  = bp_morning[bp_morning["memo"].str.contains("cpap:on",  na=False)]
        off_df = bp_morning[bp_morning["memo"].str.contains("cpap:off", na=False)]
        if not off_df.empty:
            off_dates = ", ".join(str(d) for d in sorted(off_df["date"].unique()))
            off_sys = off_df["systolic"].mean()
            on_sys  = on_df["systolic"].mean() if not on_df.empty else None
            if on_sys:
                lines.append(f"- CPAP未着用日（{off_dates}）: 朝収縮期 {off_sys:.1f} mmHg（着用時比 {off_sys - on_sys:+.1f} mmHg）")
            else:
                lines.append(f"- CPAP未着用日（{off_dates}）: 朝収縮期 {off_sys:.1f} mmHg")

    # 脈拍異常（複数日継続時のみ記録）
    all_bp = pd.concat([bp_morning, bp_night])
    anomalies = all_bp[all_bp["pulse"] > 100]
    anomaly_days = anomalies["date"].nunique() if not anomalies.empty else 0
    if anomaly_days >= 2:
        for _, row in anomalies.iterrows():
            lines.append(f"- ⚠️ 脈拍異常: {row['date']} {row['time']} / {row['pulse']:.0f} bpm（頻脈）")

    return "\n".join(lines)


def build_meals_section(meals: dict, record_days: int) -> str:
    lines = [
        f"- 外食: **{meals['eating_out']}回**",
        f"- 夜食: **{meals['night_snack_days']}日**",
        f"- 間食: **{meals['snack_days']}日**",
    ]
    if record_days > 0:
        lines.append(f"- 朝食なし: {record_days}日中{meals['no_breakfast_days']}日")
    return "\n".join(lines)


def build_exercise_section(entries: list[str]) -> str:
    if not entries:
        return "- 記録なし（または特になし）"
    return "\n".join(f"- {e}" for e in entries)


def build_analysis(
    w_df: pd.DataFrame,
    bp_morning: pd.DataFrame,
    bp_night: pd.DataFrame,
    meals: dict,
    exercise: list[str],
    w_diff: float | None,
) -> str:
    lines = []

    # 体重（週平均を前週平均と比較。日々の増減ではなく週単位のトレンドで判断する）
    if not w_df.empty:
        avg = w_df["weight"].mean()
        if w_diff is None:
            lines.append(f"週平均 {avg:.1f} kg（前週データがないためトレンド比較は次週以降）。")
        elif w_diff < -1:
            lines.append(f"体重は前週平均より {abs(w_diff):.1f} kg 減少（週平均 {avg:.1f} kg）。食事コントロールが機能している。")
        elif w_diff < 0:
            lines.append(f"体重はわずかに減少（前週比 {w_diff:+.1f} kg、週平均 {avg:.1f} kg）。方向は正しい。")
        elif w_diff <= 0.5:
            lines.append(f"体重はほぼ横ばい（前週比 {w_diff:+.1f} kg、週平均 {avg:.1f} kg）。停滞期の可能性。運動量を増やすタイミング。")
        else:
            lines.append(f"体重が前週比 {w_diff:+.1f} kg 増加（週平均 {avg:.1f} kg）。食事・運動を見直したい。")
        if avg <= GOALS[0][0]:
            lines.append(f"✅ {GOALS[0][1]}（{GOALS[0][0]} kg）を達成。次は{GOALS[1][1]}（{GOALS[1][0]} kg）に向けて継続。")

    # 血圧
    if not bp_morning.empty:
        avg_sys = bp_morning["systolic"].mean()
        avg_dia = bp_morning["diastolic"].mean()
        judge   = bp_judge(avg_sys, avg_dia)
        if avg_sys >= 140:
            lines.append(f"朝血圧の平均が {avg_sys:.0f}/{avg_dia:.0f} mmHg と高め（{judge}）。継続する場合は主治医に相談を。")
        elif avg_sys >= 130:
            lines.append(f"朝血圧の平均 {avg_sys:.0f}/{avg_dia:.0f} mmHg はやや高め。塩分・睡眠・CPAP着用を継続確認。")
        else:
            lines.append(f"朝血圧の平均 {avg_sys:.0f}/{avg_dia:.0f} mmHg は良好な範囲。")

    # CPAP
    if not bp_morning.empty and "memo" in bp_morning.columns:
        on_df  = bp_morning[bp_morning["memo"].str.contains("cpap:on",  na=False)]
        off_df = bp_morning[bp_morning["memo"].str.contains("cpap:off", na=False)]
        if not off_df.empty and not on_df.empty:
            diff_cpap = off_df["systolic"].mean() - on_df["systolic"].mean()
            if diff_cpap > 0:
                lines.append(f"CPAP未着用時の朝収縮期は着用時より平均 {diff_cpap:+.1f} mmHg 高い。着用継続が最優先。")
            else:
                lines.append(f"CPAP未着用時の朝収縮期は着用時と比べて大きな差はなかった（{diff_cpap:+.1f} mmHg）。")

    # 脈拍異常（複数日継続時のみ分析コメントを追加）
    all_bp = pd.concat([bp_morning, bp_night]) if not (bp_morning.empty and bp_night.empty) else pd.DataFrame()
    if not all_bp.empty:
        anomalies = all_bp[all_bp["pulse"] > 100]
        anomaly_days = anomalies["date"].nunique() if not anomalies.empty else 0
        if anomaly_days >= 2:
            for _, row in anomalies.iterrows():
                lines.append(f"{row['date']} {row['time']} の脈拍 {row['pulse']:.0f} bpm は頻脈。飲酒・ストレス等との関連を確認。")

    # 食事
    if meals["night_snack_days"] >= 1:
        lines.append(f"夜食が {meals['night_snack_days']} 日あった。就寝前の空腹感への対策を検討。")
    if meals["snack_days"] >= 3:
        lines.append(f"間食が {meals['snack_days']} 日と多め。")
    if meals["night_snack_days"] == 0 and meals["snack_days"] == 0:
        lines.append("夜食・間食なし。良好な食習慣が維持できている。")

    if meals["no_breakfast_days"] >= 4:
        lines.append("朝食欠食が多い。昼の過食や夜の間食につながりやすいため、簡単なものでも何か口にする習慣を。")

    # 運動
    ex_days = len(exercise)
    if ex_days == 0:
        lines.append("運動の記録なし。来週は短時間でも歩く機会を作りたい。")
    elif ex_days >= 3:
        lines.append(f"運動 {ex_days} 日実施。継続できている。")
    else:
        lines.append(f"運動 {ex_days} 日実施。目標の3日以上に向けてもう一歩。")

    return "\n".join(f"- {l}" for l in lines) if lines else "- （データ不足）"


# ---------------------------------------------------------------------------
# 良かったこと・意識するといいこと・来週の作戦
# ---------------------------------------------------------------------------

def _walk_goal_days(w_avg: float) -> int:
    """現在のフェーズに応じた週間歩行目標日数（第1目標達成後は5日）。週平均で判定。"""
    return 5 if w_avg <= GOALS[0][0] else 3


def build_good_points(
    w_df: pd.DataFrame,
    bp_morning: pd.DataFrame,
    meals: dict,
    exercise: list[str],
    w_diff: float | None,
) -> str:
    points = []
    w_avg = w_df["weight"].mean() if not w_df.empty else None

    if w_avg is not None:
        for target_kg, label in GOALS:
            if w_avg <= target_kg:
                points.append(f"✅ {label}（{target_kg} kg）達成！（週平均）")

    if len(w_df) >= 5:
        points.append(f"体重を {len(w_df)} 日記録（目標5日以上達成）")

    if w_diff is not None:
        if w_diff < -1.0:
            points.append(f"週平均が前週より {abs(w_diff):.1f} kg 減少")
        elif w_diff < 0:
            points.append("週平均が前週よりわずかに減少（方向は正しい）")

    if not bp_morning.empty:
        avg_sys = bp_morning["systolic"].mean()
        avg_dia = bp_morning["diastolic"].mean()
        if avg_sys < 130 and avg_dia < 85:
            points.append(f"朝血圧 {avg_sys:.0f}/{avg_dia:.0f} mmHg と良好")

    if not bp_morning.empty and "memo" in bp_morning.columns:
        off_count = bp_morning["memo"].str.contains("cpap:off", na=False).sum()
        on_count  = bp_morning["memo"].str.contains("cpap:on",  na=False).sum()
        if off_count == 0 and on_count > 0:
            points.append(f"CPAP {on_count} 日着用（完全着用）")

    if meals["night_snack_days"] == 0 and meals["snack_days"] == 0:
        points.append("夜食・間食なし")

    ex_days   = len(exercise)
    goal_days = _walk_goal_days(w_avg) if w_avg is not None else 3
    if ex_days >= goal_days:
        points.append(f"運動 {ex_days} 日実施（目標 {goal_days} 日以上達成）")
    elif ex_days >= 1:
        points.append(f"運動 {ex_days} 日実施")

    return "\n".join(f"- {p}" for p in points) if points else "- （特記なし）"


def build_mindful_points(
    w_df: pd.DataFrame,
    bp_morning: pd.DataFrame,
    meals: dict,
    exercise: list[str],
    record_days: int,
    w_diff: float | None,
) -> str:
    """「ダメだったこと」ではなく、次に意識するとより良くなりそうな点を挙げる。
    失敗の指摘ではなく気づきの提示を目的とする。"""
    points = []
    w_avg = w_df["weight"].mean() if not w_df.empty else None

    if len(w_df) < 5:
        points.append(f"体重記録は {len(w_df)} 日。毎日記録できると変化がより見えやすくなりそう")

    if w_diff is not None and w_diff > 0.5:
        points.append(f"週平均が前週より {w_diff:+.1f} kg 増加。食事量やタイミングを意識するとまた減少に転じやすい")

    if not bp_morning.empty:
        avg_sys = bp_morning["systolic"].mean()
        avg_dia = bp_morning["diastolic"].mean()
        if avg_sys >= 140 or avg_dia >= 90:
            points.append(f"朝血圧が {avg_sys:.0f}/{avg_dia:.0f} mmHg と高め。塩分や睡眠を意識しつつ、続くようなら受診も検討を")
        elif avg_sys >= 130 or avg_dia >= 85:
            points.append(f"朝血圧が {avg_sys:.0f}/{avg_dia:.0f} mmHg とやや高め。引き続き塩分・睡眠の質を意識すると良さそう")

    if not bp_morning.empty and "memo" in bp_morning.columns:
        off_count = bp_morning["memo"].str.contains("cpap:off", na=False).sum()
        if off_count >= 1:
            points.append(f"CPAP未着用が {off_count} 日。装着を意識すると睡眠の質が上がりやすい")

    if meals["night_snack_days"] >= 1:
        points.append(f"夜食が {meals['night_snack_days']} 日。就寝前の時間の使い方を意識するとさらに良くなりそう")

    if meals["snack_days"] >= 1:
        points.append(f"間食が {meals['snack_days']} 日。悪いことではないので、内容やタイミングを意識するとさらに良くなりそう")

    if meals["no_breakfast_days"] >= 3:
        points.append(f"朝食なしが {meals['no_breakfast_days']} 日と多め。簡単なものでも口にする習慣を意識すると良さそう")

    ex_days   = len(exercise)
    goal_days = _walk_goal_days(w_avg) if w_avg is not None else 3
    if ex_days == 0:
        points.append("運動なしの週。10分だけでも歩く習慣を意識すると良さそう")
    elif ex_days < goal_days:
        points.append(f"運動は {ex_days} 日（目標 {goal_days} 日）。もう少し日数を増やせるとさらに良くなりそう")

    return "\n".join(f"- {p}" for p in points) if points else "- （特記なし）"


def build_next_strategy(
    w_df: pd.DataFrame,
    bp_morning: pd.DataFrame,
    meals: dict,
    exercise: list[str],
    w_diff: float | None,
) -> str:
    strategies = []
    w_avg = w_df["weight"].mean() if not w_df.empty else None

    if w_avg is not None:
        for target_kg, label in GOALS:
            if w_avg > target_kg:
                remaining = w_avg - target_kg
                if remaining <= 1.0:
                    strategies.append(f"**{label}まであと {remaining:.1f} kg（週平均）** — このペースで達成を")
                break

        if w_diff is not None:
            if w_diff > 0.5:
                strategies.append("食事量・夜食のタイミングを意識する")
            elif abs(w_diff) <= 0.2 and len(exercise) < 3:
                strategies.append("停滞気味のため運動量を増やす（10分でもOK）")

    ex_days   = len(exercise)
    goal_days = _walk_goal_days(w_avg) if w_avg is not None else 3
    if ex_days == 0:
        strategies.append(f"10分ウォーキング × {goal_days} 日以上を最低目標に")
    elif ex_days < goal_days:
        strategies.append(f"運動をあと {goal_days - ex_days} 日増やして週 {goal_days} 日達成を目指す")
    else:
        strategies.append(f"運動習慣を維持（週 {ex_days} 日 → 継続）")

    if meals["no_breakfast_days"] >= 3:
        strategies.append("プロテイン・ナッツなど簡単なもので朝食を習慣化する")

    if meals["night_snack_days"] >= 1:
        strategies.append("就寝2時間前以降は食べない")

    if not bp_morning.empty:
        avg_sys = bp_morning["systolic"].mean()
        if avg_sys >= 130:
            strategies.append("塩分を控え、CPAP着用と睡眠を継続確認")

    return "\n".join(f"- {s}" for s in strategies) if strategies else "- 現状維持を継続"


# ---------------------------------------------------------------------------
# AIによる「良かったこと」「意識するといいこと」生成
# ---------------------------------------------------------------------------

AI_SYSTEM_PROMPT = """あなたは個人の健康管理（体重・血圧の改善）をサポートする管理栄養士兼トレーナーです。
ユーザーの1週間分の記録（体重・血圧・食事・運動の実データ）を分析し、
「分析（総括）」「良かったこと」「意識するといいこと」「来週の作戦」の4つを作成してください。

方針:
- 体重は7日平均で判断する。日々の増減や記録が抜けた日を咎めない。
- 間食を含め「〜をした/しなかった」という行動自体を良い・悪いと評価しない。間食は悪いことではなく、内容やタイミングを意識する対象として中立に扱う。
- 外食の「回数」自体を多い・少ないと評価しない。外食は通勤等により発生する行動であり、回数の増減はユーザーの意思でコントロールしにくい。外食に触れる場合は、回数ではなく「その日食べた内容（メニュー）」を根拠にした助言に限定する。
- 「ダメだったこと」「失敗」のような否定的な断定はしない。改善点は必ず「こうするとさらに良くなる」という前向きな提案の形で書く。
- 実際に記録された食事内容（食品名）や運動内容（距離・時間）、体重目標の進捗を根拠に、具体的な栄養素・食品・運動の助言をする。記録にない一般論は書かない。
- 血圧は朝の値を優先して評価する。
- 食事記録がなければ食事についての助言はせず、体重・血圧・運動など他のデータから言えることに絞る。

各項目の書き方と役割分担:
- summary（分析＝総括）: 箇条書きにせず、2〜4文のつながった文章にする。体重・血圧の全体的な傾向を軸に、good_points・mindful_pointsの内容と矛盾しない、週全体を俯瞰した総括にする。詳細な個別助言はgood_points/mindful_points側に譲り、summaryは「今週はどんな週だったか」の要約に徹する。
- good_points: この1週間で良かったこと・続けられていたことの振り返り。簡潔な1文の箇条書きを3〜5個程度。
- mindful_points: この1週間の記録から見えた、次に意識するとさらに良くなりそうなことの振り返り。簡潔な1文の箇条書きを3〜5個程度。
- next_strategy（来週の作戦）: 来週すぐ実行できる具体的な行動プラン。箇条書きで3〜4個程度。【体重目標の進捗】【運動目安】に記載の残りkgや目標日数など具体的な数値を踏まえつつ、今週実際にできていた食事・運動パターン（good_points/mindful_pointsで触れた内容）を土台にした、来週向けの前向きなアクションにする。mindful_pointsが「今週の振り返り」であるのに対し、next_strategyは「来週やる具体的なアクション」という役割の違いを意識し、内容が単純に重複しないようにする。"""

AI_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "この1週間の総括。箇条書きではなく2〜4文の文章。good_points/mindful_pointsと整合する内容にする",
        },
        "good_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "この1週間で良かったこと・続けられていたことの箇条書き",
        },
        "mindful_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "次に意識するとさらに良くなりそうなことの箇条書き（否定的な断定は禁止）",
        },
        "next_strategy": {
            "type": "array",
            "items": {"type": "string"},
            "description": "来週すぐ実行できる具体的な行動プランの箇条書き（体重目標の進捗・運動目安を踏まえる）",
        },
    },
    "required": ["summary", "good_points", "mindful_points", "next_strategy"],
    "additionalProperties": False,
}


def _build_ai_context(
    start: date,
    end: date,
    w_df: pd.DataFrame,
    bp_morning: pd.DataFrame,
    bp_night: pd.DataFrame,
    meals: dict,
    meals_text: str,
    exercise: list[str],
    w_diff: float | None,
) -> str:
    w_avg = w_df["weight"].mean() if not w_df.empty else None
    weight_lines = (
        "\n".join(f"- {r.date}: {r.weight}kg" for r in w_df.itertuples())
        if not w_df.empty else "記録なし"
    )

    def bp_lines(df: pd.DataFrame) -> str:
        if df.empty:
            return "記録なし"
        return "\n".join(
            f"- {r.date}: {r.systolic:.0f}/{r.diastolic:.0f} mmHg（脈拍 {r.pulse:.0f}）"
            for r in df.itertuples()
        )

    exercise_text = "\n".join(f"- {e}" for e in exercise) if exercise else "記録なし"

    if w_avg is None:
        goal_text = "データなし"
    else:
        goal_text = "最終目標を達成済み"
        for target_kg, label in GOALS:
            if w_avg > target_kg:
                goal_text = f"次の目標「{label}」（{target_kg}kg）まであと {w_avg - target_kg:.1f}kg（週平均）"
                break

    goal_days = _walk_goal_days(w_avg) if w_avg is not None else 3

    return f"""期間: {start} 〜 {end}

【体重】(7日平均: {f"{w_avg:.1f}kg" if w_avg is not None else "データなし"} / 前週比: {f"{w_diff:+.1f}kg" if w_diff is not None else "比較不可"})
{weight_lines}

【体重目標の進捗】{goal_text}

【朝血圧】
{bp_lines(bp_morning)}

【夜血圧】
{bp_lines(bp_night)}

【食事記録（生データ）】
{meals_text or "記録なし"}

【食事の集計】外食 {meals['eating_out']}回 / 夜食あり {meals['night_snack_days']}日 / 間食あり {meals['snack_days']}日 / 朝食なし {meals['no_breakfast_days']}日

【運動記録】
{exercise_text}

【運動目安】週 {goal_days} 日以上のウォーキングが目安（今週の実施: {len(exercise)} 日）"""


def generate_ai_insights(
    start: date,
    end: date,
    w_df: pd.DataFrame,
    bp_morning: pd.DataFrame,
    bp_night: pd.DataFrame,
    meals: dict,
    meals_text: str,
    exercise: list[str],
    w_diff: float | None,
) -> tuple[str, str, str, str] | None:
    """食事・運動の実データをAIに分析させ、(分析総括, 良かったこと, 意識するといいこと, 来週の作戦) を返す。
    分析総括は文章、良かったこと・意識するといいこと・来週の作戦はMarkdown箇条書き。
    APIキー未設定やAPIエラーなど、失敗時はNoneを返す（呼び出し側は閾値ベースの生成にフォールバックする）。"""
    try:
        import anthropic
    except ImportError:
        return None

    context = _build_ai_context(start, end, w_df, bp_morning, bp_night, meals, meals_text, exercise, w_diff)

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2048,
        system=AI_SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": AI_OUTPUT_SCHEMA},
        },
        messages=[{"role": "user", "content": context}],
    )

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        return None
    data = json.loads(text)
    summary        = (data.get("summary") or "").strip()
    good_points    = data.get("good_points") or []
    mindful_points = data.get("mindful_points") or []
    next_strategy  = data.get("next_strategy") or []
    analysis_sec = summary if summary else "- （特記なし）"
    good_sec     = "\n".join(f"- {p}" for p in good_points) if good_points else "- （特記なし）"
    mindful_sec  = "\n".join(f"- {p}" for p in mindful_points) if mindful_points else "- （特記なし）"
    strategy_sec = "\n".join(f"- {p}" for p in next_strategy) if next_strategy else "- 現状維持を継続"
    return analysis_sec, good_sec, mindful_sec, strategy_sec


# ---------------------------------------------------------------------------
# レビュー本文生成
# ---------------------------------------------------------------------------

def build_review(week_num: int, start: date, end: date) -> str:
    w_df      = load_weight(start, end)
    bp_df     = load_bp(start, end)
    bp_morning = bp_df[bp_df["time"] == "morning"]
    bp_night   = bp_df[bp_df["time"] == "night"]
    meals     = load_meals(start, end)
    meals_text = load_meals_text(start, end)
    exercise  = load_exercise(start, end)
    record_days = (end - start).days + 1

    prev_avg = load_prev_week_avg(start)
    w_diff   = (w_df["weight"].mean() - prev_avg) if (not w_df.empty and prev_avg is not None) else None

    weight_sec   = build_weight_section(w_df, w_diff)
    bp_sec       = build_bp_section(bp_morning, bp_night)
    meals_sec    = build_meals_section(meals, record_days)
    exercise_sec = build_exercise_section(exercise)

    try:
        ai_result = generate_ai_insights(
            start, end, w_df, bp_morning, bp_night, meals, meals_text, exercise, w_diff
        )
    except Exception as e:
        print(f"AI分析に失敗したため閾値ベースの生成にフォールバックします: {e}")
        ai_result = None

    if ai_result is not None:
        analysis_sec, good_sec, mindful_sec, strategy_sec = ai_result
    else:
        analysis_sec = build_analysis(w_df, bp_morning, bp_night, meals, exercise, w_diff)
        good_sec     = build_good_points(w_df, bp_morning, meals, exercise, w_diff)
        mindful_sec  = build_mindful_points(w_df, bp_morning, meals, exercise, record_days, w_diff)
        strategy_sec = build_next_strategy(w_df, bp_morning, meals, exercise, w_diff)

    return f"""# Weekly Review

---

## {start} → {end}（Week {week_num}）

### 体重
{weight_sec}

---

### 血圧
{bp_sec}

---

### 食事
{meals_sec}

---

### 運動
{exercise_sec}

---

### 分析（総括）
{analysis_sec}

---

### 良かったこと
{good_sec}

### 意識するといいこと
{mindful_sec}

---

### 来週の作戦
{strategy_sec}
"""


# ---------------------------------------------------------------------------
# 次週テンプレート生成
# ---------------------------------------------------------------------------

def build_next_template(next_week_num: int, next_start: date, next_end: date) -> str:
    return f"""# Weekly Review

---

## {next_start} → {next_end}（Week {next_week_num}）

### 体重
（水曜日に自動生成されます）

---

### 血圧
（水曜日に自動生成されます）

---

### 食事
（水曜日に自動生成されます）

---

### 運動
（水曜日に自動生成されます）

---

### 分析（総括）
-

---

### 良かったこと
-

### 意識するといいこと
-

---

### 来週の作戦
-
"""


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main() -> None:
    if not should_run():
        sys.exit(0)

    week_num, start, end, is_update = get_week_info()

    if start > end:
        print(f"スキップ: start({start}) > end({end})。データ範囲が不正です。")
        sys.exit(0)

    action = "更新" if is_update else "新規生成"
    print(f"Week {week_num} のレビューを{action}中: {start} → {end}")

    # レビュー生成・アーカイブ保存
    review = build_review(week_num, start, end)
    archive_path = ARCHIVE_DIR / f"weekly_review_week{week_num}.md"
    archive_path.write_text(review, encoding="utf-8")
    print(f"アーカイブ保存（{action}）: {archive_path}")

    # 新しい週の場合のみ次週テンプレートを差し替え
    if not is_update:
        next_week_num = week_num + 1
        next_start    = end + timedelta(days=1)
        next_end      = end + timedelta(days=7)
        template      = build_next_template(next_week_num, next_start, next_end)
        CURRENT_FILE.write_text(template, encoding="utf-8")
        print(f"次週テンプレート作成: {CURRENT_FILE}（Week {next_week_num}: {next_start} → {next_end}）")
    else:
        print(f"上書き更新のため weekly_review.md テンプレートは変更しません。")


if __name__ == "__main__":
    main()

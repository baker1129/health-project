"""
水曜日の夜血圧入力をトリガーに週次レビューを生成・アーカイブするスクリプト。
- archive/weekly/weekly_review_weekN.md にデータ分析付きで保存
- logs/reviews/weekly_review.md を次週テンプレートに差し替え
"""

import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

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
    if now.weekday() != 2:  # 2 = Wednesday
        print(f"本日は水曜日ではありません（{now.strftime('%A')}）。スキップします。")
        return False
    today_str = now.date().isoformat()
    df = pd.read_csv(BP_CSV)
    has_night = not df[(df["date"] == today_str) & (df["time"] == "night")].empty
    if not has_night:
        print(f"本日（{today_str}）の夜血圧がまだ入力されていません。スキップします。")
        return False
    return True


# ---------------------------------------------------------------------------
# 週番号・日付範囲の決定
# ---------------------------------------------------------------------------

def get_week_info() -> tuple[int, date, date]:
    """(week_num, start, end) を返す。アーカイブの内容から次の週番号を決定する。"""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    existing = sorted(ARCHIVE_DIR.glob("weekly_review_week*.md"))
    nums = []
    last_end: date | None = None

    for f in existing:
        m = re.match(r"weekly_review_week(\d+)\.md", f.name)
        if not m:
            continue
        n = int(m.group(1))
        nums.append(n)
        content = f.read_text(encoding="utf-8")
        dm = re.search(r"## (\d{4}-\d{2}-\d{2}) → (\d{4}-\d{2}-\d{2})", content)
        if dm and (last_end is None or int(dm.group(2).replace("-", "")) > int(last_end.isoformat().replace("-", ""))):
            last_end = date.fromisoformat(dm.group(2))

    week_num = (max(nums) + 1) if nums else 1
    end = datetime.now(JST).date()
    start = (last_end + timedelta(days=1)) if last_end else (end - timedelta(days=6))
    return week_num, start, end


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
        return {"eating_out": 0, "snack": 0, "no_breakfast_days": 0}
    text = MEALS_MD.read_text(encoding="utf-8")
    sections = re.split(r"\n(?=## \d{4}-\d{2}-\d{2})", text)
    eating_out, snack, no_breakfast = 0, 0, 0
    for section in sections:
        dm = re.match(r"## (\d{4}-\d{2}-\d{2})", section)
        if not dm:
            continue
        d = date.fromisoformat(dm.group(1))
        if not (start <= d <= end):
            continue
        eo = re.search(r"^外食: (\d+)回", section, re.MULTILINE)
        sn = re.search(r"^夜食・間食: (\d+)回", section, re.MULTILINE)
        bf = re.search(r"### 朝\n- なし", section)
        if eo:
            eating_out += int(eo.group(1))
        if sn:
            snack += int(sn.group(1))
        if bf:
            no_breakfast += 1
    return {"eating_out": eating_out, "snack": snack, "no_breakfast_days": no_breakfast}


def load_exercise(start: date, end: date) -> list[str]:
    if not EXERCISE_MD.exists():
        return []
    text = EXERCISE_MD.read_text(encoding="utf-8")
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

def build_weight_section(w_df: pd.DataFrame, target: float = 88.9) -> str:
    if w_df.empty:
        return "- データなし"
    w_start = w_df.iloc[0]["weight"]
    w_end   = w_df.iloc[-1]["weight"]
    w_avg   = w_df["weight"].mean()
    w_diff  = w_end - w_start
    lines = [
        f"- 開始: {w_start:.1f} kg　→　最新: {w_end:.1f} kg　（**{w_diff:+.1f} kg**）",
        f"- 週平均: **{w_avg:.1f} kg**",
    ]
    if not w_df["bodyfat"].isna().all():
        bf_vals = w_df["bodyfat"].dropna()
        lines.append(f"- 体脂肪率: {bf_vals.min():.1f}〜{bf_vals.max():.1f}%（平均 {bf_vals.mean():.1f}%）")
    lines.append(f"- 第1目標（{target} kg）まで: あと **{w_end - target:.1f} kg**")
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

    # 脈拍異常
    all_bp = pd.concat([bp_morning, bp_night])
    anomalies = all_bp[all_bp["pulse"] > 100]
    for _, row in anomalies.iterrows():
        lines.append(f"- ⚠️ 脈拍異常: {row['date']} {row['time']} / {row['pulse']:.0f} bpm（頻脈）")

    return "\n".join(lines)


def build_meals_section(meals: dict, record_days: int) -> str:
    lines = [
        f"- 外食: **{meals['eating_out']}回**",
        f"- 夜食・間食: **{meals['snack']}回**",
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
) -> str:
    lines = []

    # 体重
    if not w_df.empty and len(w_df) > 1:
        diff = w_df.iloc[-1]["weight"] - w_df.iloc[0]["weight"]
        avg  = w_df["weight"].mean()
        if diff < -1:
            lines.append(f"体重は週で {abs(diff):.1f} kg 減少（週平均 {avg:.1f} kg）。食事コントロールが機能している。")
        elif diff < 0:
            lines.append(f"体重はわずかに減少（{diff:+.1f} kg、週平均 {avg:.1f} kg）。方向は正しい。")
        elif diff <= 0.5:
            lines.append(f"体重はほぼ横ばい（{diff:+.1f} kg、週平均 {avg:.1f} kg）。停滞期の可能性。運動量を増やすタイミング。")
        else:
            lines.append(f"体重が {diff:+.1f} kg 増加（週平均 {avg:.1f} kg）。食事・運動を見直したい。")

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
            lines.append(f"CPAP未着用時の朝収縮期は着用時より平均 {diff_cpap:+.1f} mmHg 高い。着用継続が最優先。")

    # 脈拍異常
    all_bp = pd.concat([bp_morning, bp_night]) if not (bp_morning.empty and bp_night.empty) else pd.DataFrame()
    if not all_bp.empty:
        anomalies = all_bp[all_bp["pulse"] > 100]
        if not anomalies.empty:
            for _, row in anomalies.iterrows():
                lines.append(f"{row['date']} {row['time']} の脈拍 {row['pulse']:.0f} bpm は頻脈。飲酒・ストレス等との関連を確認。")

    # 食事
    if meals["snack"] >= 3:
        lines.append(f"夜食・間食が {meals['snack']} 回と多め。就寝前の空腹感への対策を検討。")
    elif meals["snack"] == 0:
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
# レビュー本文生成
# ---------------------------------------------------------------------------

def build_review(week_num: int, start: date, end: date) -> str:
    w_df      = load_weight(start, end)
    bp_df     = load_bp(start, end)
    bp_morning = bp_df[bp_df["time"] == "morning"]
    bp_night   = bp_df[bp_df["time"] == "night"]
    meals     = load_meals(start, end)
    exercise  = load_exercise(start, end)
    record_days = (end - start).days + 1

    weight_sec   = build_weight_section(w_df)
    bp_sec       = build_bp_section(bp_morning, bp_night)
    meals_sec    = build_meals_section(meals, record_days)
    exercise_sec = build_exercise_section(exercise)
    analysis_sec = build_analysis(w_df, bp_morning, bp_night, meals, exercise)

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
-

### ダメだったこと
-

---

### 来週の作戦
-

---

### 最低目標
- 体重記録：5日以上
- 歩行：10分 × 3日以上
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

### ダメだったこと
-

---

### 来週の作戦
-

---

### 最低目標
- 体重記録：5日以上
- 歩行：10分 × 3日以上
"""


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main() -> None:
    if not should_run():
        sys.exit(0)

    week_num, start, end = get_week_info()
    print(f"Week {week_num} のレビューを生成中: {start} → {end}")

    # レビュー生成・アーカイブ保存
    review = build_review(week_num, start, end)
    archive_path = ARCHIVE_DIR / f"weekly_review_week{week_num}.md"
    archive_path.write_text(review, encoding="utf-8")
    print(f"アーカイブ保存: {archive_path}")

    # 次週テンプレート生成
    next_week_num  = week_num + 1
    next_start     = end + timedelta(days=1)
    next_end       = end + timedelta(days=7)
    template       = build_next_template(next_week_num, next_start, next_end)
    CURRENT_FILE.write_text(template, encoding="utf-8")
    print(f"次週テンプレート作成: {CURRENT_FILE}（Week {next_week_num}: {next_start} → {next_end}）")


if __name__ == "__main__":
    main()

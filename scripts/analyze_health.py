from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

WEIGHT_CSV = ROOT / "logs" / "daily" / "weight.csv"
BP_CSV = ROOT / "logs" / "daily" / "blood_pressure.csv"

REPORT_DIR = ROOT / "reports"
ANALYSIS_MD = REPORT_DIR / "health_analysis.md"


# ---------------------------------------------------------------------------
# データ読み込み
# ---------------------------------------------------------------------------

def load_weight() -> pd.DataFrame:
    df = pd.read_csv(WEIGHT_CSV)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
    if "bodyfat" in df.columns:
        df["bodyfat"] = pd.to_numeric(df["bodyfat"], errors="coerce")
    else:
        df["bodyfat"] = pd.NA
    df = df.dropna(subset=["date", "weight"])
    df = df.sort_values("date")
    return df[["date", "weight", "bodyfat"]]


def load_blood_pressure_raw() -> pd.DataFrame:
    """朝夜の生データをそのまま返す（time列を保持）"""
    df = pd.read_csv(BP_CSV)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ["systolic", "diastolic", "pulse"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = pd.NA
    df = df.dropna(subset=["date", "systolic", "diastolic"])
    df = df.sort_values(["date", "time"])
    return df


def load_blood_pressure_daily() -> pd.DataFrame:
    """日次平均（既存の動作を維持）"""
    df = load_blood_pressure_raw()
    daily = (
        df.groupby("date", as_index=False)
        .agg(
            systolic=("systolic", "mean"),
            diastolic=("diastolic", "mean"),
            pulse=("pulse", "mean"),
        )
        .sort_values("date")
    )
    return daily


def merge_health_data() -> pd.DataFrame:
    weight = load_weight()
    bp = load_blood_pressure_daily()
    df = pd.merge(weight, bp, on="date", how="inner")
    return df.sort_values("date")


# ---------------------------------------------------------------------------
# 血圧リスク判定（日次平均ベース）
# ---------------------------------------------------------------------------

def detect_bp_risk(df: pd.DataFrame) -> dict[str, str]:
    if df.empty:
        return {
            "latest_bp": "データ不足",
            "bp_status": "血圧判定: データ不足",
            "console": "血圧判定: データ不足",
        }

    latest = df.iloc[-1]
    sys = latest["systolic"]
    dia = latest["diastolic"]
    latest_bp = f"{sys:.1f}/{dia:.1f} mmHg"

    if sys >= 140 or dia >= 90:
        bp_status = "⚠️ 血圧高め: 継続する場合は主治医に相談"
    elif sys >= 130 or dia >= 85:
        bp_status = "注意: やや高めです"
    else:
        bp_status = "良好: 現時点では高値ではありません"

    console = "\n".join([
        f"最新日平均血圧: {latest_bp}",
        bp_status,
    ])

    return {
        "latest_bp": latest_bp,
        "bp_status": bp_status,
        "console": console,
    }


# ---------------------------------------------------------------------------
# 【新機能】朝夜別血圧分析
# ---------------------------------------------------------------------------

def analyze_bp_by_time() -> dict[str, str]:
    """朝（morning）と夜（night）に分けて血圧を分析する"""
    df = load_blood_pressure_raw()

    if df.empty:
        return {
            "morning_summary": "データなし",
            "night_summary": "データなし",
            "morning_night_diff": "データなし",
            "console": "朝夜別血圧: データなし",
        }

    df_morning = df[df["time"] == "morning"].copy()
    df_night = df[df["time"] == "night"].copy()

    def summarize(subset: pd.DataFrame, label: str) -> tuple[str, str, float, float]:
        if subset.empty:
            return f"{label}: データなし", f"{label}: データなし", float("nan"), float("nan")
        avg_sys = subset["systolic"].mean()
        avg_dia = subset["diastolic"].mean()
        latest_sys = subset.iloc[-1]["systolic"]
        latest_dia = subset.iloc[-1]["diastolic"]

        if avg_sys >= 140 or avg_dia >= 90:
            status = "⚠️ 高め（受診検討）"
        elif avg_sys >= 130 or avg_dia >= 85:
            status = "注意（やや高め）"
        else:
            status = "良好"

        md = (
            f"平均 {avg_sys:.1f}/{avg_dia:.1f} mmHg　"
            f"直近 {latest_sys:.0f}/{latest_dia:.0f} mmHg　{status}"
        )
        console = (
            f"{label}: 平均 {avg_sys:.1f}/{avg_dia:.1f} mmHg "
            f"/ 直近 {latest_sys:.0f}/{latest_dia:.0f} mmHg [{status}]"
        )
        return md, console, avg_sys, avg_dia

    morning_md, morning_console, m_sys, m_dia = summarize(df_morning, "朝")
    night_md, night_console, n_sys, n_dia = summarize(df_night, "夜")

    # 朝夜差（早朝高血圧の目安：朝が夜より 10mmHg 以上高い場合に注意）
    if not (pd.isna(m_sys) or pd.isna(n_sys)):
        diff_sys = m_sys - n_sys
        diff_dia = m_dia - n_dia
        if diff_sys >= 10:
            diff_status = f"⚠️ 早朝高血圧の可能性（朝が夜より収縮期 {diff_sys:+.1f} mmHg 高い）"
        elif diff_sys <= -10:
            diff_status = f"夜間高血圧の可能性（夜が朝より収縮期 {abs(diff_sys):.1f} mmHg 高い）"
        else:
            diff_status = f"朝夜差は正常範囲内（収縮期差 {diff_sys:+.1f} mmHg）"
        diff_md = f"収縮期差（朝－夜）: {diff_sys:+.1f} mmHg　{diff_status}"
        diff_console = diff_status
    else:
        diff_md = "朝夜差: 計算不可（データ不足）"
        diff_console = "朝夜差: 計算不可"

    console = "\n".join([
        "【朝夜別血圧】",
        morning_console,
        night_console,
        diff_console,
    ])

    return {
        "morning_summary": morning_md,
        "night_summary": night_md,
        "morning_night_diff": diff_md,
        "console": console,
    }


# ---------------------------------------------------------------------------
# 【新機能】脈拍異常検出
# ---------------------------------------------------------------------------

def detect_pulse_anomaly() -> dict[str, str]:
    """脈拍の異常値（頻脈・徐脈）を検出する"""
    df = load_blood_pressure_raw()

    if df.empty or df["pulse"].isna().all():
        return {
            "pulse_status": "データなし",
            "anomaly_dates": "なし",
            "console": "脈拍チェック: データなし",
        }

    df_pulse = df.dropna(subset=["pulse"]).copy()

    # 頻脈：100 超 / 徐脈：50 未満
    tachycardia = df_pulse[df_pulse["pulse"] > 100]
    bradycardia = df_pulse[df_pulse["pulse"] < 50]

    anomalies = []
    anomaly_lines = []

    for _, row in tachycardia.iterrows():
        date_str = row["date"].strftime("%Y-%m-%d")
        time_str = row.get("time", "")
        anomalies.append(
            f"{date_str} {time_str}: 脈拍 {row['pulse']:.0f} bpm ⚠️ 頻脈（100超）"
        )
        anomaly_lines.append(
            f"{date_str} {time_str} / {row['pulse']:.0f} bpm / ⚠️ 頻脈"
        )

    for _, row in bradycardia.iterrows():
        date_str = row["date"].strftime("%Y-%m-%d")
        time_str = row.get("time", "")
        anomalies.append(
            f"{date_str} {time_str}: 脈拍 {row['pulse']:.0f} bpm ⚠️ 徐脈（50未満）"
        )
        anomaly_lines.append(
            f"{date_str} {time_str} / {row['pulse']:.0f} bpm / ⚠️ 徐脈"
        )

    latest_pulse = df_pulse.iloc[-1]["pulse"]

    if latest_pulse > 100:
        pulse_status = f"⚠️ 直近の脈拍 {latest_pulse:.0f} bpm: 頻脈の可能性。主治医に相談を"
    elif latest_pulse < 50:
        pulse_status = f"⚠️ 直近の脈拍 {latest_pulse:.0f} bpm: 徐脈の可能性。主治医に相談を"
    else:
        pulse_status = f"良好: 直近の脈拍 {latest_pulse:.0f} bpm（正常範囲）"

    if anomalies:
        anomaly_dates_md = "<br>".join(anomaly_lines)
        console_anomaly = "\n".join(anomalies)
    else:
        anomaly_dates_md = "記録期間中の異常値なし"
        console_anomaly = "記録期間中の異常値なし"

    console = "\n".join([
        "【脈拍チェック】",
        pulse_status,
        console_anomaly,
    ])

    return {
        "pulse_status": pulse_status,
        "anomaly_dates": anomaly_dates_md,
        "console": console,
    }


# ---------------------------------------------------------------------------
# 体重×血圧 相関
# ---------------------------------------------------------------------------

def calc_correlation(df: pd.DataFrame) -> dict[str, str]:
    if len(df) < 5:
        text = "データ不足（最低5日以上必要）"
        return {
            "correlation": text,
            "console": f"体重×血圧 相関: {text}",
        }

    corr_sys = df["weight"].corr(df["systolic"])
    corr_dia = df["weight"].corr(df["diastolic"])

    if corr_sys > 0.5 or corr_dia > 0.5:
        status = "⚠️ 体重増加と血圧上昇が連動している可能性があります"
    elif corr_sys < -0.3 or corr_dia < -0.3:
        status = "👍 体重減少と血圧改善が連動している可能性があります"
    else:
        status = "明確な相関はまだ見えません"

    markdown_text = (
        f"収縮期: {corr_sys:.2f}<br>"
        f"拡張期: {corr_dia:.2f}<br>"
        f"{status}"
    )

    console = "\n".join([
        f"体重×収縮期血圧 相関: {corr_sys:.2f}",
        f"体重×拡張期血圧 相関: {corr_dia:.2f}",
        status,
    ])

    return {
        "correlation": markdown_text,
        "console": console,
    }


# ---------------------------------------------------------------------------
# 体重増→血圧上昇パターン検出
# ---------------------------------------------------------------------------

def detect_weight_bp_pattern(df: pd.DataFrame) -> dict[str, str]:
    if len(df) < 7:
        text = "判定不可（最低7日以上必要）"
        return {
            "pattern": text,
            "console": f"体重増→血圧上昇検出: {text}",
        }

    recent = df.tail(7)
    weight_diff = recent["weight"].iloc[-1] - recent["weight"].iloc[0]
    sys_diff = recent["systolic"].iloc[-1] - recent["systolic"].iloc[0]
    dia_diff = recent["diastolic"].iloc[-1] - recent["diastolic"].iloc[0]

    changes = (
        f"体重: {weight_diff:+.2f} kg<br>"
        f"収縮期血圧: {sys_diff:+.1f} mmHg<br>"
        f"拡張期血圧: {dia_diff:+.1f} mmHg"
    )

    if weight_diff > 0.5 and (sys_diff > 5 or dia_diff > 3):
        status = "⚠️ アラート: 体重増加に伴い血圧も上昇しています"
        advice = "対策候補: 塩分、外食、夜食、飲酒、睡眠不足を確認"
        pattern = f"{changes}<br>{status}<br>{advice}"
        console_extra = [status, advice]
    elif weight_diff < -0.5 and (sys_diff < -5 or dia_diff < -3):
        status = "👍 良好: 体重減少に伴い血圧も改善傾向です"
        pattern = f"{changes}<br>{status}"
        console_extra = [status]
    else:
        status = "明確な連動はありません"
        pattern = f"{changes}<br>{status}"
        console_extra = [status]

    console = "\n".join([
        "直近7日変化:",
        f"- 体重: {weight_diff:+.2f} kg",
        f"- 収縮期血圧: {sys_diff:+.1f} mmHg",
        f"- 拡張期血圧: {dia_diff:+.1f} mmHg",
        *console_extra,
    ])

    return {
        "pattern": pattern,
        "console": console,
    }


# ---------------------------------------------------------------------------
# Markdownレポート書き出し
# ---------------------------------------------------------------------------

def write_markdown_report(
    bp_result: dict[str, str],
    bp_time_result: dict[str, str],
    pulse_result: dict[str, str],
    correlation_result: dict[str, str],
    pattern_result: dict[str, str],
) -> None:
    REPORT_DIR.mkdir(exist_ok=True)

    content = f"""### 最新サマリー

| 項目 | 結果 |
|---|---|
| 最新日平均血圧 | {bp_result["latest_bp"]} |
| 判定 | {bp_result["bp_status"]} |
| 朝の血圧 | {bp_time_result["morning_summary"]} |
| 夜の血圧 | {bp_time_result["night_summary"]} |
| 朝夜差 | {bp_time_result["morning_night_diff"]} |
| 脈拍状態 | {pulse_result["pulse_status"]} |
| 脈拍異常記録 | {pulse_result["anomaly_dates"]} |
| 体重×血圧 相関 | {correlation_result["correlation"]} |
| 体重増→血圧上昇検出 | {pattern_result["pattern"]} |
"""

    ANALYSIS_MD.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main() -> None:
    df = merge_health_data()

    if df.empty:
        print("分析できるデータがありません。")
        print("weight.csv と blood_pressure.csv に同じ日付のデータが必要です。")
        REPORT_DIR.mkdir(exist_ok=True)
        ANALYSIS_MD.write_text(
            "### 最新サマリー\n\n分析できるデータがありません。\n",
            encoding="utf-8",
        )
        return

    bp_result = detect_bp_risk(df)
    bp_time_result = analyze_bp_by_time()       # 新機能：朝夜別
    pulse_result = detect_pulse_anomaly()        # 新機能：脈拍異常
    correlation_result = calc_correlation(df)
    pattern_result = detect_weight_bp_pattern(df)

    write_markdown_report(
        bp_result=bp_result,
        bp_time_result=bp_time_result,
        pulse_result=pulse_result,
        correlation_result=correlation_result,
        pattern_result=pattern_result,
    )

    print("=== Health Analysis ===")
    print()
    print(bp_result["console"])
    print()
    print(bp_time_result["console"])
    print()
    print(pulse_result["console"])
    print()
    print(correlation_result["console"])
    print()
    print(pattern_result["console"])
    print()
    print(f"Markdown report saved: {ANALYSIS_MD}")


if __name__ == "__main__":
    main()

import sys
from datetime import timezone, timedelta, datetime as dt
from pathlib import Path

import pandas as pd

JST = timezone(timedelta(hours=9))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parents[1]

WEIGHT_CSV = ROOT / "logs" / "daily" / "weight.csv"
BP_CSV     = ROOT / "logs" / "daily" / "blood_pressure.csv"
MEALS_MD   = ROOT / "logs" / "lifestyle" / "meals.md"

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
    return df[["date", "weight", "bodyfat"]].sort_values("date")


def load_blood_pressure_raw(require_bp: bool = True) -> pd.DataFrame:
    """2回計測形式・1回計測形式の両方に対応。平均値をsystolic/diastolic/pulseに格納する。

    require_bp=False にすると、血圧未計測（CPAPのみ記録など）の行も残す。
    """
    df = pd.read_csv(BP_CSV)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    if "systolic1" in df.columns:
        # 新形式：2回計測 → 平均を計算
        for col in ["systolic1", "diastolic1", "pulse1", "systolic2", "diastolic2", "pulse2"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["systolic"]  = (df["systolic1"]  + df["systolic2"])  / 2
        df["diastolic"] = (df["diastolic1"] + df["diastolic2"]) / 2
        df["pulse"]     = (df["pulse1"]     + df["pulse2"])     / 2
    else:
        # 旧形式：1回計測（互換性維持）
        for col in ["systolic", "diastolic", "pulse"]:
            df[col] = pd.to_numeric(df.get(col, pd.NA), errors="coerce")

    df = df.dropna(subset=["date"])
    if require_bp:
        df = df.dropna(subset=["systolic", "diastolic"])
    return df.sort_values(["date", "time"])


def load_blood_pressure_daily() -> pd.DataFrame:
    """日次平均（朝夜の平均）"""
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
    return pd.merge(weight, bp, on="date", how="inner").sort_values("date")


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
    return {"latest_bp": latest_bp, "bp_status": bp_status, "console": console}


# ---------------------------------------------------------------------------
# 朝夜別血圧分析
# ---------------------------------------------------------------------------

def analyze_bp_by_time() -> dict[str, str]:
    df = load_blood_pressure_raw()

    if df.empty:
        return {
            "morning_summary": "データなし",
            "night_summary": "データなし",
            "morning_night_diff": "データなし",
            "console": "朝夜別血圧: データなし",
        }

    def summarize(subset: pd.DataFrame, label: str):
        if subset.empty:
            return f"{label}: データなし", f"{label}: データなし", float("nan"), float("nan")
        avg_sys = subset["systolic"].mean()
        avg_dia = subset["diastolic"].mean()
        latest = subset.iloc[-1]
        l_sys, l_dia = latest["systolic"], latest["diastolic"]

        if avg_sys >= 140 or avg_dia >= 90:
            status = "⚠️ 高め（受診検討）"
        elif avg_sys >= 130 or avg_dia >= 85:
            status = "注意（やや高め）"
        else:
            status = "良好"

        md = f"平均 {avg_sys:.1f}/{avg_dia:.1f} mmHg　直近 {l_sys:.1f}/{l_dia:.1f} mmHg　{status}"
        console = f"{label}: 平均 {avg_sys:.1f}/{avg_dia:.1f} / 直近 {l_sys:.1f}/{l_dia:.1f} [{status}]"
        return md, console, avg_sys, avg_dia

    df_m = df[df["time"] == "morning"]
    df_n = df[df["time"] == "night"]
    morning_md, morning_con, m_sys, m_dia = summarize(df_m, "朝")
    night_md,   night_con,   n_sys, n_dia = summarize(df_n, "夜")

    if not (pd.isna(m_sys) or pd.isna(n_sys)):
        diff_sys = m_sys - n_sys
        if diff_sys >= 10:
            diff_status = f"⚠️ 早朝高血圧の可能性（朝が夜より収縮期 {diff_sys:+.1f} mmHg 高い）"
        elif diff_sys <= -10:
            diff_status = f"夜間高血圧の可能性（夜が朝より収縮期 {abs(diff_sys):.1f} mmHg 高い）"
        else:
            diff_status = f"朝夜差は正常範囲内（収縮期差 {diff_sys:+.1f} mmHg）"
        diff_md = f"収縮期差（朝－夜）: {diff_sys:+.1f} mmHg　{diff_status}"
    else:
        diff_status = "朝夜差: 計算不可（データ不足）"
        diff_md = diff_status

    console = "\n".join(["【朝夜別血圧】", morning_con, night_con, diff_status])
    return {
        "morning_summary": morning_md,
        "night_summary": night_md,
        "morning_night_diff": diff_md,
        "console": console,
    }


# ---------------------------------------------------------------------------
# 脈拍異常検出
# ---------------------------------------------------------------------------

def detect_pulse_anomaly() -> dict[str, str]:
    df = load_blood_pressure_raw()

    if df.empty or df["pulse"].isna().all():
        return {"pulse_status": "データなし", "anomaly_dates": "なし", "console": "脈拍チェック: データなし"}

    df_p = df.dropna(subset=["pulse"])

    latest_pulse = df_p.iloc[-1]["pulse"]

    # 異常記録表示: 14日以内かつ当月のみ（どちらか一方でも外れたら非表示）
    today_jst = dt.now(JST).date()
    cutoff = pd.Timestamp(today_jst - timedelta(days=14))
    df_window = df_p[(df_p["date"] >= cutoff) & (df_p["date"].dt.month == today_jst.month)]
    tachycardia = df_window[df_window["pulse"] > 100]
    bradycardia = df_window[df_window["pulse"] < 50]

    anomaly_lines = []
    for _, row in pd.concat([tachycardia, bradycardia]).sort_values("date").iterrows():
        kind = "⚠️ 頻脈" if row["pulse"] > 100 else "⚠️ 徐脈"
        anomaly_lines.append(
            f"{row['date'].strftime('%Y-%m-%d')} {row['time']} / {row['pulse']:.1f} bpm / {kind}"
        )
    if latest_pulse > 100:
        pulse_status = f"⚠️ 直近の脈拍 {latest_pulse:.1f} bpm: 頻脈の可能性。主治医に相談を"
    elif latest_pulse < 50:
        pulse_status = f"⚠️ 直近の脈拍 {latest_pulse:.1f} bpm: 徐脈の可能性。主治医に相談を"
    else:
        pulse_status = f"良好: 直近の脈拍 {latest_pulse:.1f} bpm（正常範囲）"

    anomaly_dates_md = "<br>".join(anomaly_lines) if anomaly_lines else "記録期間中の異常値なし"
    console = "\n".join(["【脈拍チェック】", pulse_status] + (anomaly_lines or ["異常値なし"]))

    return {"pulse_status": pulse_status, "anomaly_dates": anomaly_dates_md, "console": console}


# ---------------------------------------------------------------------------
# CPAP着用有無×朝血圧分析
# ---------------------------------------------------------------------------

def analyze_cpap() -> dict[str, str]:
    # 血圧未計測でもCPAP着用有無は記録されるため、血圧の有無で行を落とさない
    df = load_blood_pressure_raw(require_bp=False)
    df_m = df[df["time"] == "morning"].copy()

    _no_data = {
        "usage": "記録なし",
        "on_sys": "—",
        "off_sys": "—",
        "diff": "—",
        "note": "",
        "console": "CPAP分析: 記録なし",
    }

    if df_m.empty or "memo" not in df_m.columns:
        return _no_data

    def _parse_cpap(val: str):
        v = str(val).strip().lower()
        if "cpap:on" in v:
            return True
        if "cpap:off" in v:
            return False
        return None

    df_m["cpap_on"] = df_m["memo"].fillna("").map(_parse_cpap)
    df_rec = df_m.dropna(subset=["cpap_on"])

    if df_rec.empty:
        return _no_data

    total     = len(df_rec)
    on_count  = int(df_rec["cpap_on"].sum())
    usage_pct = on_count / total * 100
    usage_text = f"{on_count}/{total}日 ({usage_pct:.0f}%)"

    df_on  = df_rec[df_rec["cpap_on"] == True]
    df_off = df_rec[df_rec["cpap_on"] == False]

    on_sys  = df_on["systolic"].mean()  if not df_on.empty  else float("nan")
    off_sys = df_off["systolic"].mean() if not df_off.empty else float("nan")

    on_sys_text  = f"{on_sys:.1f} mmHg"  if not pd.isna(on_sys)  else "データなし"
    off_sys_text = f"{off_sys:.1f} mmHg" if not pd.isna(off_sys) else "データなし"

    if not (pd.isna(on_sys) or pd.isna(off_sys)):
        diff = off_sys - on_sys
        if diff >= 10:
            diff_text = f"⚠️ 未着用時は収縮期が平均 {diff:+.1f} mmHg 高い"
        elif diff > 0:
            diff_text = f"未着用時がやや高い傾向 ({diff:+.1f} mmHg)"
        else:
            diff_text = f"現時点では差は不明瞭 ({diff:+.1f} mmHg)"
    else:
        diff_text = "比較不可（着用/未着用どちらかのデータなし）"

    note = f"記録{total}日分" + ("・記憶ベース含む" if total < 14 else "")

    console = "\n".join([
        "【CPAP分析】",
        f"着用率: {usage_text}",
        f"着用時 朝収縮期平均: {on_sys_text}",
        f"未着用時 朝収縮期平均: {off_sys_text}",
        diff_text,
        f"({note})",
    ])

    return {
        "usage": usage_text,
        "on_sys": on_sys_text,
        "off_sys": off_sys_text,
        "diff": diff_text,
        "note": note,
        "console": console,
    }


# ---------------------------------------------------------------------------
# 体重×血圧 相関
# ---------------------------------------------------------------------------

def calc_correlation(df: pd.DataFrame) -> dict[str, str]:
    if len(df) < 5:
        text = "データ不足（最低5日以上必要）"
        return {"correlation": text, "console": f"体重×血圧 相関: {text}"}

    corr_sys = df["weight"].corr(df["systolic"])
    corr_dia = df["weight"].corr(df["diastolic"])

    if corr_sys > 0.5 or corr_dia > 0.5:
        status = "⚠️ 体重増加と血圧上昇が連動している可能性があります"
    elif corr_sys < -0.3 or corr_dia < -0.3:
        status = "👍 体重減少と血圧改善が連動している可能性があります"
    else:
        status = "明確な相関はまだ見えません"

    markdown_text = f"収縮期: {corr_sys:.2f}<br>拡張期: {corr_dia:.2f}<br>{status}"
    console = "\n".join([
        f"体重×収縮期血圧 相関: {corr_sys:.2f}",
        f"体重×拡張期血圧 相関: {corr_dia:.2f}",
        status,
    ])
    return {"correlation": markdown_text, "console": console}


# ---------------------------------------------------------------------------
# 体重増→血圧上昇パターン検出
# ---------------------------------------------------------------------------

def detect_weight_bp_pattern(df: pd.DataFrame) -> dict[str, str]:
    if len(df) < 7:
        text = "判定不可（最低7日以上必要）"
        return {"pattern": text, "console": f"体重増→血圧上昇検出: {text}"}

    recent = df.tail(7)
    weight_diff = recent["weight"].iloc[-1] - recent["weight"].iloc[0]
    sys_diff    = recent["systolic"].iloc[-1] - recent["systolic"].iloc[0]
    dia_diff    = recent["diastolic"].iloc[-1] - recent["diastolic"].iloc[0]

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
    return {"pattern": pattern, "console": console}


# ---------------------------------------------------------------------------
# 食事（外食・夜食間食）週次集計
# ---------------------------------------------------------------------------

def analyze_meals() -> dict[str, str]:
    import re
    from datetime import datetime, timedelta

    if not MEALS_MD.exists():
        return {"weekly_summary": "データなし", "console": "食事分析: データなし"}

    text = MEALS_MD.read_text(encoding="utf-8")
    sections = re.split(r'\n(?=## \d{4}-\d{2}-\d{2})', text)

    records = []
    for section in sections:
        date_m = re.match(r'## (\d{4}-\d{2}-\d{2})', section)
        if not date_m:
            continue
        date = datetime.strptime(date_m.group(1), "%Y-%m-%d").date()
        eo_m = re.search(r'^外食: (\d+)回',       section, re.MULTILINE)
        ns_m = re.search(r'^夜食: (あり|なし)',    section, re.MULTILINE)
        sn_m = re.search(r'^間食: (あり|なし)',    section, re.MULTILINE)
        records.append({
            "date":         date,
            "eating_out":   int(eo_m.group(1)) if eo_m else None,
            "night_snack":  (ns_m.group(1) == "あり") if ns_m else None,
            "snack":        (sn_m.group(1) == "あり") if sn_m else None,
        })

    if not records:
        return {"weekly_summary": "記録なし", "console": "食事分析: 記録なし"}

    latest_date = max(r["date"] for r in records)
    week_start  = latest_date - __import__("datetime").timedelta(days=6)
    week = [r for r in records if r["date"] >= week_start]

    eo_total   = sum(r["eating_out"] for r in week if r["eating_out"] is not None)
    ns_days    = sum(1 for r in week if r["night_snack"])
    sn_days    = sum(1 for r in week if r["snack"])
    eo_days    = sum(1 for r in week if r["eating_out"] is not None)
    rec_days   = sum(1 for r in week if r["night_snack"] is not None or r["snack"] is not None)
    days_total = max(eo_days, rec_days)

    summary_md = f"外食 {eo_total}回 / 夜食 {ns_days}日・間食 {sn_days}日（直近7日・記録{days_total}日分）"
    console    = f"外食: {eo_total}回、夜食: {ns_days}日、間食: {sn_days}日（直近7日・記録{days_total}日分）"
    return {"weekly_summary": summary_md, "console": console}


# ---------------------------------------------------------------------------
# Markdownレポート書き出し
# ---------------------------------------------------------------------------

def write_markdown_report(
    bp_result: dict[str, str],
    bp_time_result: dict[str, str],
    pulse_result: dict[str, str],
    cpap_result: dict[str, str],
    correlation_result: dict[str, str],
    pattern_result: dict[str, str],
    meals_result: dict[str, str],
) -> None:
    REPORT_DIR.mkdir(exist_ok=True)

    cpap_note = f"（{cpap_result['note']}）" if cpap_result["note"] else ""
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
| CPAP着用率 | {cpap_result["usage"]} {cpap_note} |
| CPAP着用時 朝収縮期平均 | {cpap_result["on_sys"]} |
| CPAP未着用時 朝収縮期平均 | {cpap_result["off_sys"]} |
| CPAP有無の影響 | {cpap_result["diff"]} |
| 体重×血圧 相関 | {correlation_result["correlation"]} |
| 体重増→血圧上昇検出 | {pattern_result["pattern"]} |
| 外食・夜食間食（直近7日） | {meals_result["weekly_summary"]} |
"""
    ANALYSIS_MD.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main() -> None:
    df = merge_health_data()

    if df.empty:
        print("分析できるデータがありません。")
        REPORT_DIR.mkdir(exist_ok=True)
        ANALYSIS_MD.write_text("### 最新サマリー\n\n分析できるデータがありません。\n", encoding="utf-8")
        return

    bp_result          = detect_bp_risk(df)
    bp_time_result     = analyze_bp_by_time()
    pulse_result       = detect_pulse_anomaly()
    cpap_result        = analyze_cpap()
    correlation_result = calc_correlation(df)
    pattern_result     = detect_weight_bp_pattern(df)
    meals_result       = analyze_meals()

    write_markdown_report(
        bp_result=bp_result,
        bp_time_result=bp_time_result,
        pulse_result=pulse_result,
        cpap_result=cpap_result,
        correlation_result=correlation_result,
        pattern_result=pattern_result,
        meals_result=meals_result,
    )

    print("=== Health Analysis ===\n")
    print(bp_result["console"])
    print()
    print(bp_time_result["console"])
    print()
    print(pulse_result["console"])
    print()
    print(cpap_result["console"])
    print()
    print(correlation_result["console"])
    print()
    print(pattern_result["console"])
    print()
    print(meals_result["console"])
    print()
    print(f"Markdown report saved: {ANALYSIS_MD}")


if __name__ == "__main__":
    main()

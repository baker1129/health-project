from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

WEIGHT_CSV = ROOT / "logs" / "daily" / "weight.csv"
BP_CSV = ROOT / "logs" / "daily" / "blood_pressure.csv"

REPORT_DIR = ROOT / "reports"
ANALYSIS_MD = REPORT_DIR / "health_analysis.md"


def load_weight() -> pd.DataFrame:
    df = pd.read_csv(WEIGHT_CSV)

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce")

    df = df.dropna(subset=["date", "weight"])
    df = df.sort_values("date")

    return df[["date", "weight"]]


def load_blood_pressure_daily() -> pd.DataFrame:
    df = pd.read_csv(BP_CSV)

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["systolic"] = pd.to_numeric(df["systolic"], errors="coerce")
    df["diastolic"] = pd.to_numeric(df["diastolic"], errors="coerce")

    if "pulse" in df.columns:
        df["pulse"] = pd.to_numeric(df["pulse"], errors="coerce")
    else:
        df["pulse"] = pd.NA

    df = df.dropna(subset=["date", "systolic", "diastolic"])

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
    df = df.sort_values("date")

    return df


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

    console = "\n".join(
        [
            f"最新日平均血圧: {latest_bp}",
            bp_status,
        ]
    )

    return {
        "latest_bp": latest_bp,
        "bp_status": bp_status,
        "console": console,
    }


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

    console = "\n".join(
        [
            f"体重×収縮期血圧 相関: {corr_sys:.2f}",
            f"体重×拡張期血圧 相関: {corr_dia:.2f}",
            status,
        ]
    )

    return {
        "correlation": markdown_text,
        "console": console,
    }


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

    console = "\n".join(
        [
            "直近7日変化:",
            f"- 体重: {weight_diff:+.2f} kg",
            f"- 収縮期血圧: {sys_diff:+.1f} mmHg",
            f"- 拡張期血圧: {dia_diff:+.1f} mmHg",
            *console_extra,
        ]
    )

    return {
        "pattern": pattern,
        "console": console,
    }


def write_markdown_report(
    bp_result: dict[str, str],
    correlation_result: dict[str, str],
    pattern_result: dict[str, str],
) -> None:
    REPORT_DIR.mkdir(exist_ok=True)

    content = f"""### 最新サマリー

| 項目 | 結果 |
|---|---|
| 最新日平均血圧 | {bp_result["latest_bp"]} |
| 判定 | {bp_result["bp_status"]} |
| 体重×血圧 相関 | {correlation_result["correlation"]} |
| 体重増→血圧上昇検出 | {pattern_result["pattern"]} |
"""

    ANALYSIS_MD.write_text(content, encoding="utf-8")


def main() -> None:
    df = merge_health_data()

    if df.empty:
        print("分析できるデータがありません。")
        print("weight.csv と blood_pressure.csv に同じ日付のデータが必要です。")

        REPORT_DIR.mkdir(exist_ok=True)
        ANALYSIS_MD.write_text(
            """### 最新サマリー

分析できるデータがありません。

`weight.csv` と `blood_pressure.csv` に同じ日付のデータが必要です。
""",
            encoding="utf-8",
        )
        return

    bp_result = detect_bp_risk(df)
    correlation_result = calc_correlation(df)
    pattern_result = detect_weight_bp_pattern(df)

    write_markdown_report(
        bp_result=bp_result,
        correlation_result=correlation_result,
        pattern_result=pattern_result,
    )

    print("=== Health Analysis ===")
    print()

    print(bp_result["console"])
    print()

    print(correlation_result["console"])
    print()

    print(pattern_result["console"])
    print()

    print(f"Markdown report saved: {ANALYSIS_MD}")


if __name__ == "__main__":
    main()
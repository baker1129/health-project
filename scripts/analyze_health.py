from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

WEIGHT_CSV = ROOT / "logs" / "daily" / "weight.csv"
BP_CSV = ROOT / "logs" / "daily" / "blood_pressure.csv"


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
    df["pulse"] = pd.to_numeric(df["pulse"], errors="coerce")

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


def calc_correlation(df: pd.DataFrame) -> str:
    if len(df) < 5:
        return "体重×血圧 相関: データ不足（最低5日以上必要）"

    corr_sys = df["weight"].corr(df["systolic"])
    corr_dia = df["weight"].corr(df["diastolic"])

    message = [
        f"体重×収縮期血圧 相関: {corr_sys:.2f}",
        f"体重×拡張期血圧 相関: {corr_dia:.2f}",
    ]

    if corr_sys > 0.5 or corr_dia > 0.5:
        message.append("⚠️ 体重増加と血圧上昇が連動している可能性があります")
    elif corr_sys < -0.3 or corr_dia < -0.3:
        message.append("👍 体重減少と血圧改善が連動している可能性があります")
    else:
        message.append("明確な相関はまだ見えません")

    return "\n".join(message)


def detect_weight_bp_pattern(df: pd.DataFrame) -> str:
    if len(df) < 7:
        return "体重増→血圧上昇検出: 判定不可（最低7日以上必要）"

    recent = df.tail(7)

    weight_diff = recent["weight"].iloc[-1] - recent["weight"].iloc[0]
    sys_diff = recent["systolic"].iloc[-1] - recent["systolic"].iloc[0]
    dia_diff = recent["diastolic"].iloc[-1] - recent["diastolic"].iloc[0]

    message = [
        "直近7日変化:",
        f"- 体重: {weight_diff:+.2f} kg",
        f"- 収縮期血圧: {sys_diff:+.1f} mmHg",
        f"- 拡張期血圧: {dia_diff:+.1f} mmHg",
    ]

    if weight_diff > 0.5 and (sys_diff > 5 or dia_diff > 3):
        message.append("⚠️ アラート: 体重増加に伴い血圧も上昇しています")
        message.append("対策候補: 塩分、外食、夜食、飲酒、睡眠不足を確認")
    elif weight_diff < -0.5 and (sys_diff < -5 or dia_diff < -3):
        message.append("👍 良好: 体重減少に伴い血圧も改善傾向です")
    else:
        message.append("明確な連動はありません")

    return "\n".join(message)


def detect_bp_risk(df: pd.DataFrame) -> str:
    if df.empty:
        return "血圧判定: データ不足"

    latest = df.iloc[-1]

    sys = latest["systolic"]
    dia = latest["diastolic"]

    message = [
        f"最新日平均血圧: {sys:.1f}/{dia:.1f} mmHg",
    ]

    if sys >= 140 or dia >= 90:
        message.append("⚠️ 血圧高め: 継続する場合は主治医に相談")
    elif sys >= 130 or dia >= 85:
        message.append("注意: やや高めです")
    else:
        message.append("良好: 現時点では高値ではありません")

    return "\n".join(message)


def main() -> None:
    df = merge_health_data()

    if df.empty:
        print("分析できるデータがありません。")
        print("weight.csv と blood_pressure.csv に同じ日付のデータが必要です。")
        return

    print("=== Health Analysis ===")
    print()

    print(detect_bp_risk(df))
    print()

    print(calc_correlation(df))
    print()

    print(detect_weight_bp_pattern(df))


if __name__ == "__main__":
    main()
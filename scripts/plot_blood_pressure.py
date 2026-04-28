from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "logs" / "blood_pressure.csv"
REPORT_DIR = ROOT / "reports"
OUTPUT = REPORT_DIR / "blood_pressure.png"


def load_data():
    df = pd.read_csv(FILE)

    df["date"] = pd.to_datetime(df["date"])
    df["systolic"] = pd.to_numeric(df["systolic"], errors="coerce")
    df["diastolic"] = pd.to_numeric(df["diastolic"], errors="coerce")

    df = df.dropna(subset=["date", "systolic", "diastolic"])

    return df


def daily_average(df):
    daily = df.groupby("date").agg({
        "systolic": "mean",
        "diastolic": "mean"
    }).reset_index()

    daily["sys_7d"] = daily["systolic"].rolling(7, min_periods=1).mean()
    daily["dia_7d"] = daily["diastolic"].rolling(7, min_periods=1).mean()

    return daily


def evaluate(df):
    if len(df) < 7:
        return "データ不足"

    sys = df["sys_7d"].iloc[-1]
    dia = df["dia_7d"].iloc[-1]

    if sys >= 140 or dia >= 90:
        return "血圧高め ⚠️ 要改善"
    elif sys >= 130 or dia >= 85:
        return "やや高め 注意"
    else:
        return "良好 👍"


def detect_trend(df):
    if len(df) < 7:
        return "判定不可"

    latest = df["sys_7d"].iloc[-1]
    past = df["sys_7d"].iloc[-7]

    diff = latest - past

    if diff > 5:
        return f"上昇傾向（+{diff:.1f}）⚠️"
    elif diff < -5:
        return f"下降傾向（{diff:.1f}）👍"
    else:
        return "横ばい"


def plot(df):
    plt.figure(figsize=(10, 5))

    plt.plot(df["date"], df["systolic"], label="Systolic", marker="o")
    plt.plot(df["date"], df["sys_7d"], label="Sys 7d avg")

    plt.axhline(140, linestyle="--", label="High (140)")
    plt.axhline(130, linestyle="--", label="Warning (130)")

    plt.title("Blood Pressure Trend")
    plt.xlabel("Date")
    plt.ylabel("mmHg")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()

    plt.savefig(OUTPUT)


def main():
    REPORT_DIR.mkdir(exist_ok=True)

    df = load_data()
    daily = daily_average(df)

    status = evaluate(daily)
    trend = detect_trend(daily)

    print(status)
    print(trend)

    plot(daily)


if __name__ == "__main__":
    main()
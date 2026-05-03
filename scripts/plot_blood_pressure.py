from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


ROOT = Path(__file__).resolve().parents[1]
BP_CSV = ROOT / "logs" / "daily" / "blood_pressure.csv"
REPORT_DIR = ROOT / "reports"
OUTPUT = REPORT_DIR / "blood_pressure.png"


def load_data() -> pd.DataFrame:
    df = pd.read_csv(BP_CSV)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    if "systolic1" in df.columns:
        for col in ["systolic1", "diastolic1", "pulse1", "systolic2", "diastolic2", "pulse2"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["systolic"]  = (df["systolic1"]  + df["systolic2"])  / 2
        df["diastolic"] = (df["diastolic1"] + df["diastolic2"]) / 2
        df["pulse"]     = (df["pulse1"]     + df["pulse2"])     / 2
    else:
        for col in ["systolic", "diastolic", "pulse"]:
            df[col] = pd.to_numeric(df.get(col, pd.NA), errors="coerce")

    df = df.dropna(subset=["date", "systolic", "diastolic"])
    return df.sort_values("date")


def daily_average(df: pd.DataFrame) -> pd.DataFrame:
    daily = (
        df.groupby("date", as_index=False)
        .agg(
            systolic=("systolic", "mean"),
            diastolic=("diastolic", "mean"),
        )
        .sort_values("date")
    )

    daily["sys_7d"] = daily["systolic"].rolling(window=7, min_periods=1).mean()
    daily["dia_7d"] = daily["diastolic"].rolling(window=7, min_periods=1).mean()

    return daily


def main() -> None:
    REPORT_DIR.mkdir(exist_ok=True)

    raw = load_data()
    df = daily_average(raw)

    if df.empty:
        raise ValueError("No valid blood pressure data found in logs/daily/blood_pressure.csv")

    plt.figure(figsize=(10, 5))

    plt.plot(df["date"], df["systolic"], marker="o", label="Systolic")
    plt.plot(df["date"], df["diastolic"], marker="o", label="Diastolic")
    plt.plot(df["date"], df["sys_7d"], marker="o", label="Systolic 7-day avg")
    plt.plot(df["date"], df["dia_7d"], marker="o", label="Diastolic 7-day avg")

    # 目安ライン
    plt.axhline(140, linestyle="--", label="Systolic high: 140")
    plt.axhline(90, linestyle="--", label="Diastolic high: 90")
    plt.axhline(130, linestyle=":", label="Systolic caution: 130")
    plt.axhline(85, linestyle=":", label="Diastolic caution: 85")

    # X軸を実データ範囲に合わせる
    start = df["date"].min() - pd.Timedelta(days=1)
    end = df["date"].max() + pd.Timedelta(days=1)
    plt.xlim(start, end)

    # 日付表示を見やすくする
    ax = plt.gca()
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    plt.xticks(rotation=45)

    plt.title("Blood Pressure Trend")
    plt.xlabel("Date")
    plt.ylabel("mmHg")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    plt.savefig(OUTPUT)
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    main()
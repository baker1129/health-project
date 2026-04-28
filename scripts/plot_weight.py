from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
WEIGHT_CSV = ROOT / "logs" / "weight.csv"
REPORT_DIR = ROOT / "reports"
OUTPUT = REPORT_DIR / "weight.png"


def main() -> None:
    REPORT_DIR.mkdir(exist_ok=True)

    df = pd.read_csv(WEIGHT_CSV)

    df["date"] = pd.to_datetime(df["date"])
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
    df["bodyfat"] = pd.to_numeric(df["bodyfat"], errors="coerce")

    df = df.dropna(subset=["date", "weight"])
    df = df.sort_values("date")

    if df.empty:
        raise ValueError("No valid weight data found in logs/weight.csv")

    df["weight_7d_avg"] = df["weight"].rolling(window=7, min_periods=1).mean()

    plt.figure(figsize=(10, 5))

    plt.plot(df["date"], df["weight"], marker="o", label="Weight")
    plt.plot(df["date"], df["weight_7d_avg"], marker="o", label="7-day average")

    plt.title("Weight Trend")
    plt.xlabel("Date")
    plt.ylabel("Weight kg")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    plt.savefig(OUTPUT)
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    main()
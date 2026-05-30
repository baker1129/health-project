from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.ticker as ticker
import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
WEIGHT_CSV = ROOT / "logs" / "daily" / "weight.csv"
REPORT_DIR = ROOT / "reports"
OUTPUT = REPORT_DIR / "weight.png"


def _date_label(x, _pos):
    d = mdates.num2date(x)
    return f"{d.month}/{d.day}"


def main() -> None:
    REPORT_DIR.mkdir(exist_ok=True)

    df = pd.read_csv(WEIGHT_CSV)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce")

    if "bodyfat" in df.columns:
        df["bodyfat"] = pd.to_numeric(df["bodyfat"], errors="coerce")

    df = df.dropna(subset=["date", "weight"]).sort_values("date")

    if df.empty:
        raise ValueError("No valid weight data found in logs/daily/weight.csv")

    df["weight_7d_avg"] = df["weight"].rolling(window=7, min_periods=1).mean()
    has_bodyfat = "bodyfat" in df.columns and df["bodyfat"].notna().any()

    fig, ax1 = plt.subplots(figsize=(10, 4.5))

    ax1.plot(
        df["date"], df["weight"],
        color="#5b9bd5", linewidth=1.2, alpha=0.5,
        marker="o", markersize=3.5, label="体重",
    )
    ax1.plot(
        df["date"], df["weight_7d_avg"],
        color="#1d4e8f", linewidth=2.5, label="7日平均",
    )
    ax1.axhline(82.9, color="#34c759", linewidth=1, linestyle="--", alpha=0.7, label="第2目標 82.9kg")

    ax1.set_ylabel("体重 (kg)", fontsize=11)
    ax1.set_title("体重推移", fontsize=13, fontweight="bold")
    ax1.grid(True, axis="y", linestyle=":", alpha=0.4)
    ax1.legend(loc="upper right", fontsize=10, framealpha=0.8)

    if has_bodyfat:
        df_bf = df.dropna(subset=["bodyfat"])
        ax2 = ax1.twinx()
        ax2.plot(
            df_bf["date"], df_bf["bodyfat"],
            color="#ff9500", linewidth=1.2, alpha=0.45,
            marker="s", markersize=2.5, linestyle="--", label="体脂肪率",
        )
        ax2.set_ylabel("体脂肪率 (%)", fontsize=11, color="#ff9500")
        ax2.tick_params(axis="y", labelcolor="#ff9500")
        ax2.legend(loc="lower right", fontsize=10, framealpha=0.8)

    start = df["date"].min() - pd.Timedelta(days=1)
    end   = df["date"].max() + pd.Timedelta(days=1)
    ax1.set_xlim(start, end)
    ax1.xaxis.set_major_locator(mdates.DayLocator(interval=7))
    ax1.xaxis.set_major_formatter(ticker.FuncFormatter(_date_label))
    ax1.xaxis.set_minor_locator(mdates.DayLocator())
    ax1.tick_params(axis="x", which="minor", length=3)
    plt.xticks(fontsize=10)

    plt.tight_layout()
    plt.savefig(OUTPUT, dpi=150)
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    main()

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.ticker as ticker
import matplotlib.pyplot as plt
import pandas as pd
import japanize_matplotlib  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
BP_CSV = ROOT / "logs" / "daily" / "blood_pressure.csv"
REPORT_DIR = ROOT / "reports"
OUTPUT = REPORT_DIR / "blood_pressure.png"


def _date_label(x, _pos):
    d = mdates.num2date(x)
    return f"{d.month}/{d.day}"


def load_data() -> pd.DataFrame:
    df = pd.read_csv(BP_CSV)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    for col in ["systolic1", "diastolic1", "pulse1", "systolic2", "diastolic2", "pulse2"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["systolic"]  = (df["systolic1"]  + df["systolic2"])  / 2
    df["diastolic"] = (df["diastolic1"] + df["diastolic2"]) / 2

    return df.dropna(subset=["date", "systolic", "diastolic"]).sort_values("date")


def daily_avg(df: pd.DataFrame, time_filter: str) -> pd.DataFrame:
    sub = df[df["time"] == time_filter].copy()
    daily = (
        sub.groupby("date", as_index=False)
        .agg(systolic=("systolic", "mean"), diastolic=("diastolic", "mean"))
        .sort_values("date")
    )
    daily["sys_7d"] = daily["systolic"].rolling(window=7, min_periods=1).mean()
    daily["dia_7d"] = daily["diastolic"].rolling(window=7, min_periods=1).mean()
    return daily


def _plot_panel(ax, df: pd.DataFrame, title: str) -> None:
    if df.empty:
        return

    # 危険域の背景色（収縮期を基準にした簡易帯）
    ax.axhspan(140, 200, alpha=0.07, color="red")
    ax.axhspan(130, 140, alpha=0.07, color="orange")

    # 収縮期
    ax.plot(df["date"], df["systolic"],  color="#ff5252", linewidth=1.2, alpha=0.45,
            marker="o", markersize=3.5, label="収縮期")
    ax.plot(df["date"], df["sys_7d"],    color="#b71c1c", linewidth=2.5, label="収縮期 7日平均")

    # 拡張期
    ax.plot(df["date"], df["diastolic"], color="#ff9800", linewidth=1.2, alpha=0.45,
            marker="o", markersize=3.5, label="拡張期")
    ax.plot(df["date"], df["dia_7d"],    color="#e65100", linewidth=2.5, label="拡張期 7日平均")

    # 参考ライン（凡例なし、右端アノテーションで代替）
    for val, color, label in [(140, "#b71c1c", "140"), (130, "#e65100", "130"),
                               (90,  "#b71c1c", "90"),  (85,  "#e65100", "85")]:
        ax.axhline(val, color=color, linewidth=0.8, linestyle=":", alpha=0.6)
        ax.annotate(
            label,
            xy=(1.0, val), xycoords=("axes fraction", "data"),
            xytext=(4, 0), textcoords="offset points",
            fontsize=8, color=color, va="center",
        )

    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_ylabel("mmHg", fontsize=10)
    ax.set_ylim(55, 175)
    ax.grid(True, axis="y", linestyle=":", alpha=0.4)
    ax.legend(loc="upper right", fontsize=9, framealpha=0.8, ncol=2)


def _set_xaxis(ax, df: pd.DataFrame) -> None:
    start = df["date"].min() - pd.Timedelta(days=1)
    end   = df["date"].max() + pd.Timedelta(days=1)
    ax.set_xlim(start, end)
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=7))
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(_date_label))
    ax.xaxis.set_minor_locator(mdates.DayLocator())
    ax.tick_params(axis="x", which="minor", length=3)
    plt.setp(ax.get_xticklabels(), fontsize=9)


def main() -> None:
    REPORT_DIR.mkdir(exist_ok=True)

    raw     = load_data()
    morning = daily_avg(raw, "morning")
    night   = daily_avg(raw, "night")

    has_night = not night.empty

    fig, axes = plt.subplots(
        2 if has_night else 1, 1,
        figsize=(10, 8 if has_night else 4.5),
        sharex=False,
    )
    if not has_night:
        axes = [axes]

    _plot_panel(axes[0], morning, "血圧推移（朝）")
    _set_xaxis(axes[0], morning)

    if has_night:
        _plot_panel(axes[1], night, "血圧推移（夜）")
        all_dates = pd.concat([morning, night]).sort_values("date")
        _set_xaxis(axes[1], all_dates)

    plt.tight_layout(h_pad=2.5)
    plt.savefig(OUTPUT, dpi=150)
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    main()

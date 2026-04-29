from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

README = ROOT / "README.md"
ANALYSIS_MD = ROOT / "reports" / "health_analysis.md"

START = "<!-- HEALTH_ANALYSIS_START -->"
END = "<!-- HEALTH_ANALYSIS_END -->"


def main() -> None:
    readme = README.read_text(encoding="utf-8")
    analysis = ANALYSIS_MD.read_text(encoding="utf-8").strip()

    before, rest = readme.split(START, 1)
    _, after = rest.split(END, 1)

    updated = f"{before}{START}\n\n{analysis}\n\n{END}{after}"

    README.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
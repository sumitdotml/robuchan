"""Plot response times from data/response_times.log.

Format: one float per line (seconds elapsed since batch start).
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt

LOG_PATH = Path(__file__).parent / "response_times.log"
OUT_PATH = Path(__file__).parent / "response_times.png"


def parse_log(path: Path) -> list[float]:
    times = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    times.append(float(line))
                except ValueError:
                    pass
    return times


def main() -> None:
    times = parse_log(LOG_PATH)
    if not times:
        print(f"No data parsed from {LOG_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsed {len(times)} response times")

    _, ax = plt.subplots(figsize=(12, 4))
    ax.scatter(range(len(times)), times, s=4, color="#4C72B0", alpha=0.6, linewidths=0)
    ax.set_xlabel("Call index")
    ax.set_ylabel("Response time (s)")
    ax.set_title("API Response Time per Call")
    ax.set_xlim(0, len(times))

    plt.tight_layout()
    plt.savefig(OUT_PATH, dpi=150, bbox_inches="tight")
    print(f"Saved → {OUT_PATH}")


if __name__ == "__main__":
    main()

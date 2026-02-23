"""
Auto-discover all *_ragas files in this directory, parse their RAGAS scores,
write scores.csv, and save scores_chart.png as a grouped bar chart.

Run:  python plot_scores.py
"""

import csv
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SCRIPT_DIR = Path(__file__).parent
CSV_PATH   = SCRIPT_DIR / "scores.csv"
CHART_PATH = SCRIPT_DIR / "scores_chart.png"

METRICS = [
    "context_precision",
    "context_recall",
    "faithfulness",
    "answer_relevancy",
    "answer_correctness",
]

METRIC_LABELS = {
    "context_precision":  "Context\nPrecision",
    "context_recall":     "Context\nRecall",
    "faithfulness":       "Faithfulness",
    "answer_relevancy":   "Answer\nRelevancy",
    "answer_correctness": "Answer\nCorrectness",
}

# Maps filename stem → human-readable architecture label.
# Keys are matched as substrings of the filename (order matters – most specific first).
_NAME_MAP = [
    ("hybrid_multi_15", "Hybrid Multi-Agent (15/10)"),
    ("hybrid_multi_20", "Hybrid Multi-Agent (20/10)"),
    ("hybrid_multi_30", "Hybrid Multi-Agent (30/10)"),
    ("hybrid_30",       "Hybrid (30/10)"),
    ("multi_10",        "Multi Agent (10/7)"),
    ("multi_30",        "Multi Agent (30/10)"),
    ("single_30",       "Single Agent (30/10)"),
]

SHORT_NAMES = {
    "Single Agent (30/10)":        "Single\n30/10",
    "Multi Agent (10/7)":          "Multi\n10/7",
    "Multi Agent (30/10)":         "Multi\n30/10",
    "Hybrid (30/10)":              "Hybrid\n30/10",
    "Hybrid Multi-Agent (15/10)":  "HM 15/10",
    "Hybrid Multi-Agent (20/10)":  "HM 20/10",
    "Hybrid Multi-Agent (30/10)":  "HM 30/10",
}

COLORS = ["#4285F4", "#EA4335", "#FBBC04", "#34A853", "#AB47BC", "#FF6D00", "#00ACC1"]


# ──────────────────────────────────────────────────────────────────────────────
# 1. Discovery & parsing
# ──────────────────────────────────────────────────────────────────────────────

def _label_from_path(p: Path) -> str:
    stem = p.stem  # e.g. "chat_hybrid_multi_15_10_ragas"
    for key, label in _NAME_MAP:
        if key in stem:
            return label
    # Fallback: tidy up the stem
    return stem.replace("chat_", "").replace("_ragas", "").replace("_", " ").title()


def discover_and_parse(script_dir: Path) -> list[dict]:
    """
    Find every file whose name ends with '_ragas', parse its metric scores,
    and return a list of row dicts sorted by architecture label.
    """
    rows = []
    for path in sorted(script_dir.glob("*_ragas")):
        label  = _label_from_path(path)
        text   = path.read_text(encoding="utf-8")
        row    = {"architecture": label}
        for metric in METRICS:
            m = re.search(rf"{metric}:\s*([\d.]+)", text)
            row[metric] = float(m.group(1)) if m else 0.0
        rows.append(row)

    # Sort: single → multi → hybrid (deterministic order for chart)
    order = list(SHORT_NAMES.keys())
    rows.sort(key=lambda r: order.index(r["architecture"])
              if r["architecture"] in order else 999)
    return rows


# ──────────────────────────────────────────────────────────────────────────────
# 2. CSV writer
# ──────────────────────────────────────────────────────────────────────────────

def write_csv(rows: list[dict], path: Path) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["architecture"] + METRICS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV  saved → {path}")


# ──────────────────────────────────────────────────────────────────────────────
# 3. Chart
# ──────────────────────────────────────────────────────────────────────────────

def plot(rows: list[dict], path: Path) -> None:
    architectures = [r["architecture"] for r in rows]
    n_arch    = len(architectures)
    n_metrics = len(METRICS)
    x         = np.arange(n_metrics)
    bar_width = 0.11
    offsets   = (np.arange(n_arch) - (n_arch - 1) / 2)

    fig, ax = plt.subplots(figsize=(16, 7))

    for i, row in enumerate(rows):
        vals  = [row[m] for m in METRICS]
        label = SHORT_NAMES.get(row["architecture"], row["architecture"])
        bars  = ax.bar(
            x + offsets[i] * bar_width,
            vals,
            bar_width,
            label=label,
            color=COLORS[i % len(COLORS)],
            edgecolor="white",
            linewidth=0.5,
        )
        for bar, v in zip(bars, vals):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.006,
                f"{v:.3f}",
                ha="center", va="bottom",
                fontsize=6.5, fontweight="bold", rotation=90,
            )

    ax.set_ylabel("Score", fontsize=13, fontweight="bold")
    ax.set_title(
        "RAGAS Metrics Comparison – All RAG Architectures",
        fontsize=15, fontweight="bold", pad=15,
    )
    ax.set_xticks(x)
    ax.set_xticklabels([METRIC_LABELS[m] for m in METRICS], fontsize=11, fontweight="bold")
    ax.set_ylim(0, 1.18)

    ax.axhline(y=0.8, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
    ax.text(n_metrics - 0.45, 0.81, "0.80 threshold", fontsize=8, color="gray")

    ax.legend(
        loc="upper center", bbox_to_anchor=(0.5, -0.10),
        ncol=n_arch, fontsize=9,
        frameon=True, fancybox=True, shadow=True,
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.3, linestyle="--")

    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    print(f"Chart saved → {path}")
    plt.close(fig)


# ──────────────────────────────────────────────────────────────────────────────
# 4. Entrypoint
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    rows = discover_and_parse(SCRIPT_DIR)
    print(f"\nDiscovered {len(rows)} architectures:")
    for r in rows:
        print(f"  {r['architecture']}")

    write_csv(rows, CSV_PATH)
    plot(rows, CHART_PATH)
    print("\nDone.")

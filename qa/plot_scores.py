"""
Generate a grouped bar chart comparing RAGAS metrics across all RAG architectures.
Reads from scores.csv and saves the chart as scores_chart.png.
"""

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SCRIPT_DIR = Path(__file__).parent
CSV_PATH = SCRIPT_DIR / "scores.csv"
OUTPUT_PATH = SCRIPT_DIR / "scores_chart.png"

METRIC_LABELS = {
    "context_precision": "Context\nPrecision",
    "context_recall": "Context\nRecall",
    "faithfulness": "Faithfulness",
    "answer_relevancy": "Answer\nRelevancy",
    "answer_correctness": "Answer\nCorrectness",
}

SHORT_NAMES = {
    "Single Agent": "Single",
    "Multi Agent": "Multi",
    "Hybrid": "Hybrid",
    "Hybrid Multi-Agent (20/10)": "HM 20/10",
    "Hybrid Multi-Agent (30/10)": "HM 30/10",
}

COLORS = ["#4285F4", "#EA4335", "#FBBC04", "#34A853", "#AB47BC"]


def load_scores(path: Path):
    architectures = []
    metrics = list(METRIC_LABELS.keys())
    scores = {m: [] for m in metrics}

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            architectures.append(row["architecture"])
            for m in metrics:
                scores[m].append(float(row[m]))

    return architectures, metrics, scores


def plot(architectures, metrics, scores):
    n_arch = len(architectures)
    n_metrics = len(metrics)
    x = np.arange(n_metrics)
    bar_width = 0.15
    offsets = np.arange(n_arch) - (n_arch - 1) / 2

    fig, ax = plt.subplots(figsize=(14, 7))

    for i, arch in enumerate(architectures):
        vals = [scores[m][i] for m in metrics]
        label = SHORT_NAMES.get(arch, arch)
        bars = ax.bar(
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
                bar.get_height() + 0.008,
                f"{v:.3f}",
                ha="center",
                va="bottom",
                fontsize=7,
                fontweight="bold",
                rotation=90,
            )

    ax.set_ylabel("Score", fontsize=13, fontweight="bold")
    ax.set_title(
        "RAGAS Metrics Comparison Across RAG Architectures",
        fontsize=15,
        fontweight="bold",
        pad=15,
    )
    ax.set_xticks(x)
    ax.set_xticklabels(
        [METRIC_LABELS[m] for m in metrics], fontsize=11, fontweight="bold"
    )
    ax.set_ylim(0, 1.12)
    ax.axhline(y=0.8, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
    ax.text(n_metrics - 0.5, 0.805, "0.8 threshold", fontsize=8, color="gray")

    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.10),
        ncol=n_arch,
        fontsize=10,
        frameon=True,
        fancybox=True,
        shadow=True,
    )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.3, linestyle="--")

    fig.tight_layout()
    fig.savefig(OUTPUT_PATH, dpi=200, bbox_inches="tight")
    print(f"Chart saved to {OUTPUT_PATH}")
    plt.close(fig)


if __name__ == "__main__":
    architectures, metrics, scores = load_scores(CSV_PATH)
    plot(architectures, metrics, scores)

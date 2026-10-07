#!/usr/bin/env python3
"""Result figures for the technical report (vector PDF, English, repo house style).

Reads the JSON written by analyze_paper.py plus eval_inputs/<method>/stats_<tid>.json.
  fig2_families.pdf     family scores per condition, main and cross judge
  fig3_paired.pdf       per-topic Skill-Full minus NaiveRAG-Pool, both judges
  fig4_coverage.pdf     BSC versus arXiv coverage (Skill-Full runs)
Usage: make_figures.py <analysis.json> <das_eval dir> <out dir>
"""

from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

PALETTE = {"blue_main": "#0F4D92", "blue_secondary": "#3775BA", "teal": "#42949E",
           "red_2": "#E9A6A1", "red_strong": "#B64342", "neutral": "#CFCECE", "violet": "#9A4D8E"}
# Names as in the tables; each condition has its own marker so the figure reads in grayscale.
CONDS = [("Skill-Full", "Skill-Full", PALETTE["blue_main"], "o"),
         ("Skill-Abs", "Skill-Abs", PALETTE["teal"], "s"),
         ("NoSkill-Agent", "NoSkill-Agent", PALETTE["violet"], "v"),
         ("NaiveRAG-Pool", "NaiveRAG-Pool", PALETTE["red_2"], "^"),
         ("NaiveRAG-Own", "NaiveRAG-Own", PALETTE["red_strong"], "D")]
WIDTH = 5.5  # inches: the text width the figures are printed at, so font sizes print as set
FAMS = ["BSC", "TSQ", "HDQ", "MAR", "Total"]
BENCH_NAMES = {"DAS-Bench": "Main judge (Qwen3.5-397B-A17B)", "DAS-Bench-xjudge": "Cross judge (qwen3.8-flash)"}
SKILL_RUNS = ["skill_deepseek-v4.1-flash", "skill_deepseek-v4.1-flash_full_r2", "skill_deepseek-v4.1-flash_full_r3"]
POOL = "naiverag-deepseek-v4.1-flash_pool_r1"
CS = {f"{i:03d}" for i in range(1, 22)}


def style() -> None:
    plt.rcParams.update({
        "font.family": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"], "font.size": 8,
        "axes.titlesize": 8, "axes.labelsize": 8, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
        "legend.fontsize": 7.5, "axes.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
        "legend.frameon": False, "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "xtick.major.width": 0.8, "ytick.major.width": 0.8,
    })


def fig_families(res: dict, out: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH, 2.5), sharey=True)
    x = np.arange(len(FAMS))
    for ax, bench in zip(axes, BENCH_NAMES):
        cond = res["condition"][bench]
        present = [c for c in CONDS if c[0] in cond]
        width = 0.8 / len(present)
        for i, (key, label, color, mk) in enumerate(present):
            vals = [cond[key][f] for f in FAMS]
            err = [cond[key].get(f"{f}_sd_runs") or 0 for f in FAMS]
            # Points, not bars: the axis does not start at the scale minimum, so bar length would mislead.
            ax.errorbar(x + (i - (len(present) - 1) / 2) * width, vals, yerr=err if any(err) else None, fmt=mk, ms=4,
                        color=color, ecolor=color, elinewidth=1.0, capsize=2, label=label, zorder=3)
        ax.set_xticks(x, FAMS)
        ax.set_ylim(3.0, 5.1)
        ax.grid(axis="y", color=PALETTE["neutral"], lw=0.6, zorder=0)
        for k in range(len(FAMS) - 1):
            ax.axvline(k + 0.5, color=PALETTE["neutral"], lw=0.6, zorder=0)
        ax.set_title(BENCH_NAMES[bench])
        ax.axvspan(len(FAMS) - 1.5, len(FAMS) - 0.5, color=PALETTE["neutral"], alpha=0.25, zorder=0)
    axes[0].set_ylabel("Score (1–5)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=len(labels), bbox_to_anchor=(0.5, -0.02), handletextpad=0.2,
               columnspacing=0.9)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(out / "fig2_families.pdf", bbox_inches="tight")
    fig.savefig(out / "fig2_families.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_paired(res: dict, out: Path) -> None:
    ptf = res["per_topic_families"]
    fig, ax = plt.subplots(figsize=(WIDTH, 2.3))
    markers = {"DAS-Bench": ("o", PALETTE["blue_main"]), "DAS-Bench-xjudge": ("s", PALETTE["violet"])}
    tids = [f"{i:03d}" for i in range(1, 31)]
    for bench, (mk, color) in markers.items():
        xs, ys = [], []
        for j, t in enumerate(tids):
            skill = [ptf[bench][m][t]["Total"] for m in SKILL_RUNS if m in ptf[bench] and t in ptf[bench][m]]
            base = ptf[bench].get(POOL, {}).get(t)
            if skill and base:
                xs.append(j)
                ys.append(st.mean(skill) - base["Total"])
        ax.scatter(xs, ys, marker=mk, color=color, s=14, label=BENCH_NAMES[bench], zorder=3)
    ax.axhline(0, color="black", lw=1)
    ax.axvspan(20.5, 29.5, color=PALETTE["neutral"], alpha=0.25, zorder=0)
    lo = ax.get_ylim()[0]
    ax.text(25, lo + 0.03, "non-CS topics", ha="center", va="bottom", fontsize=7.5, color="#555555")
    ax.set_xticks(range(30), tids, rotation=90, fontsize=7)
    ax.set_xlim(-0.7, 29.7)
    ax.set_ylabel("Δ Total score")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=2)
    fig.tight_layout()
    fig.savefig(out / "fig3_paired.pdf", bbox_inches="tight")
    fig.savefig(out / "fig3_paired.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_coverage(res: dict, root: Path, out: Path) -> None:
    ptf = res["per_topic_families"]
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH, 2.4), sharey=True)
    rng = np.random.default_rng(0)  # vertical jitter: BSC takes steps of 0.25, so points stack without it
    for ax, bench in zip(axes, BENCH_NAMES):
        for m in SKILL_RUNS:
            for t, fam in ptf[bench].get(m, {}).items():
                f = root / "eval_inputs" / m / f"stats_{t}.json"
                if not f.exists():
                    continue
                cov = json.loads(f.read_text())["arxiv_coverage"]
                color = PALETTE["blue_main"] if t in CS else PALETTE["red_strong"]
                ax.scatter(cov, fam["BSC"] + rng.uniform(-0.06, 0.06), color=color, s=9, alpha=0.7,
                           marker="o" if t in CS else "^")
        ax.set_xlabel("arXiv coverage of references")
        ax.set_title(BENCH_NAMES[bench])
        ax.set_xlim(-0.03, 1.03)
    axes[0].set_ylabel("BSC (Skill-Full, all runs)")
    from matplotlib.lines import Line2D
    axes[1].legend(handles=[Line2D([], [], marker="o", ls="", color=PALETTE["blue_main"], label="CS topic"),
                            Line2D([], [], marker="^", ls="", color=PALETTE["red_strong"], label="non-CS topic")],
                   loc="upper left")
    fig.tight_layout()
    fig.savefig(out / "fig4_coverage.pdf", bbox_inches="tight")
    fig.savefig(out / "fig4_coverage.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    res = json.loads(Path(sys.argv[1]).read_text())
    root, out = Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    style()
    fig_families(res, out)
    fig_paired(res, out)
    fig_coverage(res, root, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
CONDS = [("Skill-Full", "Skill (full text)", PALETTE["blue_main"]),
         ("Skill-Abs", "Skill (abstracts only)", PALETTE["teal"]),
         ("NaiveRAG-Pool", "NaiveRAG-Pool", PALETTE["red_2"]),
         ("NaiveRAG-Own", "NaiveRAG-Own", PALETTE["red_strong"])]
FAMS = ["BSC", "TSQ", "HDQ", "MAR", "Total"]
BENCH_NAMES = {"DAS-Bench": "Main judge (Qwen3.5-397B-A17B)", "DAS-Bench-xjudge": "Cross judge (qwen3.8-flash)"}
SKILL_RUNS = ["skill_deepseek-v4.1-flash", "skill_deepseek-v4.1-flash_full_r2", "skill_deepseek-v4.1-flash_full_r3"]
POOL = "naiverag-deepseek-v4.1-flash_pool_r1"
CS = {f"{i:03d}" for i in range(1, 22)}


def style() -> None:
    plt.rcParams.update({
        "font.family": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"], "font.size": 11,
        "axes.linewidth": 1.2, "axes.spines.top": False, "axes.spines.right": False,
        "legend.frameon": False, "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "xtick.major.width": 1.2, "ytick.major.width": 1.2,
    })


def fig_families(res: dict, out: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6), sharey=True)
    width = 0.19
    x = np.arange(len(FAMS))
    for ax, bench in zip(axes, BENCH_NAMES):
        cond = res["condition"][bench]
        for i, (key, label, color) in enumerate(CONDS):
            if key not in cond:
                continue
            vals = [cond[key][f] for f in FAMS]
            err = [cond[key].get(f"{f}_sd_runs") or 0 for f in FAMS]
            # Points, not bars: the axis does not start at the scale minimum, so bar length would mislead.
            ax.errorbar(x + (i - 1.5) * width, vals, yerr=err if any(err) else None, fmt="o", ms=7,
                        color=color, ecolor=color, elinewidth=1.4, capsize=3, label=label, zorder=3)
        ax.set_xticks(x, FAMS)
        ax.set_ylim(3.0, 5.1)
        ax.grid(axis="y", color=PALETTE["neutral"], lw=0.6, zorder=0)
        for k in range(len(FAMS) - 1):
            ax.axvline(k + 0.5, color=PALETTE["neutral"], lw=0.6, zorder=0)
        ax.set_title(BENCH_NAMES[bench], fontsize=11)
        ax.axvspan(len(FAMS) - 1.5, len(FAMS) - 0.5, color=PALETTE["neutral"], alpha=0.25, zorder=0)
    axes[0].set_ylabel("Score (1–5)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.04))
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(out / "fig2_families.pdf", bbox_inches="tight")
    fig.savefig(out / "fig2_families.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_paired(res: dict, out: Path) -> None:
    ptf = res["per_topic_families"]
    fig, ax = plt.subplots(figsize=(11, 3.2))
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
        ax.scatter(xs, ys, marker=mk, color=color, s=28, label=BENCH_NAMES[bench], zorder=3)
    ax.axhline(0, color="black", lw=1)
    ax.axvspan(20.5, 29.5, color=PALETTE["neutral"], alpha=0.25, zorder=0)
    lo = ax.get_ylim()[0]
    ax.text(25, lo + 0.03, "non-CS topics", ha="center", va="bottom", fontsize=9, color="gray")
    ax.set_xticks(range(30), tids, rotation=90, fontsize=8)
    ax.set_xlim(-0.7, 29.7)
    ax.set_ylabel("Δ Total score")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=2, fontsize=9)
    fig.tight_layout()
    fig.savefig(out / "fig3_paired.pdf", bbox_inches="tight")
    fig.savefig(out / "fig3_paired.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_coverage(res: dict, root: Path, out: Path) -> None:
    ptf = res["per_topic_families"]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4), sharey=True)
    for ax, bench in zip(axes, BENCH_NAMES):
        for m in SKILL_RUNS:
            for t, fam in ptf[bench].get(m, {}).items():
                f = root / "eval_inputs" / m / f"stats_{t}.json"
                if not f.exists():
                    continue
                cov = json.loads(f.read_text())["arxiv_coverage"]
                color = PALETTE["blue_main"] if t in CS else PALETTE["red_strong"]
                ax.scatter(cov, fam["BSC"], color=color, s=18, alpha=0.7)
        ax.set_xlabel("arXiv coverage of references")
        ax.set_title(BENCH_NAMES[bench], fontsize=11)
        ax.set_xlim(-0.03, 1.03)
    axes[0].set_ylabel("BSC (Skill-Full, all runs)")
    from matplotlib.lines import Line2D
    axes[1].legend(handles=[Line2D([], [], marker="o", ls="", color=PALETTE["blue_main"], label="CS topic"),
                            Line2D([], [], marker="o", ls="", color=PALETTE["red_strong"], label="non-CS topic")],
                   loc="upper left", fontsize=9)
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

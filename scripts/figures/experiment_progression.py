#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "matplotlib>=3.7.0",
# ]
# ///
"""
Experiment progression figure for DeckSage presentation.

Shows Magic substitute nDCG across 62 experiments with key moments labeled.
Produces a clean, distill.pub-style SVG.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Data: (experiment_id, magic_sub_ndcg, label_or_None)
# Only experiments with measured Magic sub nDCG
data = [
    (1,  0.151, None),
    (2,  0.156, "v5 fused\n(+attr fusion)"),
    (4,  0.095, "LightGCN\n(inflated->real)"),
    (23, 0.156, None),  # v7 set edges
    (26, 0.156, "all-games\nbaseline"),
    (29, 0.088, "Commander\ndata (-22%)"),
    (31, 0.177, None),  # mp2v v2
    (37, 0.186, None),  # mp2v 40ep
    (38, 0.198, None),  # mp2v 80ep
    (39, 0.228, None),  # mp2v 160ep (leaked)
    # --- DEDUP CORRECTION ---
    (52, 0.069, "DEDUP\nCORRECTION"),
    (53, 0.094, "variance\nablation"),
    (54, 0.003, "HGT\n(near-random)"),
    (56, 0.107, "spectral\n(ProNE)"),
    # --- ANNOTATION SATURATION ---
    (58, 0.233, "fill holes\nround 1"),
    (59, 0.525, "SATURATED\n(true quality)"),
    # --- TEXT E5 ---
    (61, 0.501, "text_e5 holes\n(co-occur drops)"),
]

# Condensed nDCG for text_e5 (exp 0062)
text_e5_point = (62, 0.613, "text_e5\ncondensed")

fig, ax = plt.subplots(figsize=(12, 5))

# Style
ax.set_facecolor("#fafafa")
fig.patch.set_facecolor("#ffffff")

# Main line
xs = [d[0] for d in data]
ys = [d[1] for d in data]
ax.plot(xs, ys, color="#0071e3", linewidth=1.8, zorder=3, alpha=0.8)
ax.scatter(xs, ys, color="#0071e3", s=24, zorder=4)

# Text_e5 point (different color)
ax.scatter([text_e5_point[0]], [text_e5_point[1]], color="#34a853", s=60, zorder=5, marker="D")

# Dedup correction: vertical dashed line
ax.axvline(x=52, color="#d32f2f", linestyle="--", alpha=0.4, linewidth=1)
ax.axvspan(51.5, 52.5, alpha=0.06, color="#d32f2f")

# Saturation: vertical dashed line
ax.axvline(x=59, color="#34a853", linestyle="--", alpha=0.4, linewidth=1)

# Labels for key points
label_style = dict(fontsize=7.5, color="#444", ha="center", va="bottom",
                   fontfamily="sans-serif", linespacing=1.3)
for exp_id, ndcg, label in data:
    if label:
        offset_y = 0.02
        if "DEDUP" in label:
            offset_y = 0.04
            label_style_local = {**label_style, "color": "#d32f2f", "fontweight": "bold", "fontsize": 8}
        elif "SATURATED" in label:
            label_style_local = {**label_style, "color": "#34a853", "fontweight": "bold", "fontsize": 8}
        elif "HGT" in label or "LightGCN" in label:
            label_style_local = {**label_style, "color": "#888"}
            offset_y = -0.06
        elif "Commander" in label:
            label_style_local = {**label_style, "color": "#888"}
            offset_y = -0.05
        else:
            label_style_local = label_style
        ax.annotate(label, (exp_id, ndcg + offset_y), **label_style_local)

# Text_e5 label
ax.annotate(text_e5_point[2], (text_e5_point[0], text_e5_point[1] + 0.02),
            fontsize=8, color="#34a853", fontweight="bold", ha="center", va="bottom",
            fontfamily="sans-serif")

# Axes
ax.set_xlabel("Experiment", fontsize=11, fontfamily="sans-serif", color="#333")
ax.set_ylabel("Magic Substitute nDCG", fontsize=11, fontfamily="sans-serif", color="#333")
ax.set_xlim(-1, 65)
ax.set_ylim(-0.02, 0.72)

# Clean axes
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.spines["left"].set_color("#ccc")
ax.spines["bottom"].set_color("#ccc")
ax.tick_params(colors="#666", labelsize=9)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.2f}"))

# Phase annotations at bottom
phases = [
    (1, 10, "Baselines"),
    (20, 40, "Graph methods\n(GNN, MetaPath2Vec)"),
    (50, 56, "Dedup +\nVariance"),
    (57, 62, "Annotation\nsaturation"),
]
for x0, x1, label in phases:
    mid = (x0 + x1) / 2
    ax.annotate(label, (mid, -0.01), fontsize=7, color="#999", ha="center", va="top",
                fontfamily="sans-serif")

plt.tight_layout()

out = "docs/figures/experiment_progression.png"
import os
os.makedirs(os.path.dirname(out), exist_ok=True)
fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="#ffffff")
fig.savefig(out.replace(".png", ".svg"), bbox_inches="tight", facecolor="#ffffff")
print(f"Saved to {out} and {out.replace('.png', '.svg')}")

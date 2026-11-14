"""Scientific analog quality vs practical feasibility (Pareto view) from outputs/latest_query.json.

Run the query with ``--practicality`` first:
  uv run --frozen python 2_find_analogs.py --site apollo_11 --top-k 20 --practicality
  uv run --frozen python 3b_plot_pareto.py [--profile field|facility]

X = practical score (higher = easier/cheaper), Y = scientific analog distance (lower = better, axis inverted so
up = better). Pareto-optimal candidates are highlighted; hard-excluded sites are crossed out. Nothing is combined.
"""

from __future__ import annotations

import argparse
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from config import OUTPUT_DIR

QUERY_PATH = OUTPUT_DIR / "latest_query.json"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--profile", choices=["field", "facility"], default="field")
    args = p.parse_args()
    data = json.loads(QUERY_PATH.read_text(encoding="utf-8"))
    results = [r for r in data["results"] if "practicality" in r]
    if not results:
        raise SystemExit("brak bloków practicality: uruchom 2_find_analogs.py z --practicality")

    fig, ax = plt.subplots(figsize=(8, 6))
    for r in results:
        score = r["practicality"][f"{args.profile}_score" if args.profile == "facility" else "field_campaign_score"]
        if score is None:
            continue
        optimal = r["practicality"][f"pareto_{args.profile}"]
        excluded = r["constraints"]["hard_excluded"]
        ax.scatter(score, r["total_distance"], s=90 if optimal else 40, c="tab:green" if optimal else "tab:gray",
                   marker="x" if excluded else "o", zorder=3)
        ax.annotate(r["region"], (score, r["total_distance"]), fontsize=7, xytext=(4, 3), textcoords="offset points")
    ax.set_xlabel(f"practical feasibility ({args.profile} score, higher = easier/cheaper)")
    ax.set_ylabel("scientific analog distance (lower = better)")
    ax.invert_yaxis()
    ax.set_title(f"{data['moon']['patch_id']}: science vs practicality (green = Pareto, x = excluded)")
    ax.grid(alpha=0.3)
    out = OUTPUT_DIR / f"pareto_{args.profile}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"zapisano {out}")


if __name__ == "__main__":
    main()

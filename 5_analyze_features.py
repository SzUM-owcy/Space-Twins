"""Analiza cech terenu: redundancja, jakość cech kształtu i porównanie schematów ważenia.

Skrypt tylko czyta indeksy i zapisuje tabele do ``outputs/``:
  A. diagnostyka każdej z 12 cech (ICC między regionami, pokrycie Księżyca, redundancja, wpływ na ranking),
  B. porównanie schematów ważenia (default, equal, group, pca, reduced) na 18 miejscach Księżyca,
  C. luki w pokryciu: miejsca Księżyca bez bliskiego odpowiednika na Ziemi (wskazówka, jakie regiony dodać).

Uruchomienie:  PYTHONPATH=. uv run --frozen python 5_analyze_features.py [--noise 0.3 --seeds 20]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from config import DATA_DIR, FEATURE_NAMES, OUTPUT_DIR, PIXEL_SIZE_M
from src.morphometry import extract_patch_features
from src.scoring import distances, fit_scaler, transform

SLOPE = [f for f in FEATURE_NAMES if f.startswith("slope_")]
ROUGH = ["tri_mean", "rms_height", "relief_range"]
SHAPE = ["hypsometric_integral", "elev_skew"]
REDUCED = ["slope_p50", "slope_p90", "rms_height", "relief_range", "hypsometric_integral", "elev_skew"]
TOP_K = 10
# Sprawdzenie sensowności (nie walidacja): Cinder Lake zbudowano jako poligon treningowy Apollo.
APOLLO_SITES = ["moon_apollo_11", "moon_apollo_12", "moon_apollo_14", "moon_apollo_15", "moon_apollo_17"]
APOLLO_ANALOG = "cinder_lake"


def group_weights() -> dict[str, float]:
    """Każda grupa (nachylenia / chropowatość / kształt) ma tę samą wagę, wewnątrz grupy równo."""
    weights = {}
    for group in (SLOPE, ROUGH, SHAPE):
        weights.update({f: 1.0 / len(group) for f in group})
    return weights


def subset_weights(keep: list[str]) -> dict[str, float]:
    return {f: (1.0 if f in keep else 0.0) for f in FEATURE_NAMES}


def pca_projection(z_earth: np.ndarray, variance: float = 0.95) -> tuple[np.ndarray, np.ndarray]:
    """Wybielająca projekcja PCA (kolumny = składowe wyjaśniające ``variance`` wariancji Ziemi)."""
    cov = np.cov(z_earth, rowvar=False)
    vals, vecs = np.linalg.eigh(cov)
    order = np.argsort(vals)[::-1]
    vals, vecs = vals[order], vecs[:, order]
    k = int(np.searchsorted(np.cumsum(vals) / vals.sum(), variance) + 1)
    return vecs[:, :k], np.sqrt(vals[:k])


class Scorer:
    """Odległość terenowa wszystkich łatek Ziemi od jednego miejsca Księżyca, dla danego schematu."""

    def __init__(self, earth: pd.DataFrame) -> None:
        self.earth = earth
        self.scaler = fit_scaler(earth)
        self.z_earth = transform(earth, self.scaler)
        self.pca_vecs, self.pca_sd = pca_projection(self.z_earth)
        self.regions = earth["region"].to_numpy()

    def distance(self, scheme: str, moon: pd.Series, z_noise: np.ndarray | None = None) -> np.ndarray:
        moon_features = {f: float(moon[f]) for f in FEATURE_NAMES}
        if scheme == "pca":
            z_moon = transform(moon_features, self.scaler)[0]
            if z_noise is not None:
                z_moon = z_moon + z_noise
            diff = (self.z_earth - z_moon) @ self.pca_vecs / self.pca_sd
            return np.sqrt((diff**2).mean(axis=1))
        weights = {
            "default": None,
            "equal": {f: 1.0 for f in FEATURE_NAMES},
            "group": group_weights(),
            "reduced": subset_weights(REDUCED),
        }[scheme]
        if z_noise is None:
            return distances(moon_features, self.earth, self.scaler, feature_weights=weights)[
                "total_distance"
            ].to_numpy()
        z_moon = transform(moon_features, self.scaler)[0] + z_noise
        diff = self.z_earth - z_moon
        if weights is None:
            slope = np.sqrt((diff[:, [FEATURE_NAMES.index(f) for f in SLOPE]] ** 2).mean(axis=1))
            other = [f for f in FEATURE_NAMES if f not in SLOPE]
            shape = np.sqrt((diff[:, [FEATURE_NAMES.index(f) for f in other]] ** 2).mean(axis=1))
            return 0.5 * slope + 0.5 * shape
        w = np.array([weights.get(f, 1.0) for f in FEATURE_NAMES])
        return np.sqrt((diff**2) @ (w / w.sum()))

    def ranked_regions(self, dist: np.ndarray) -> pd.DataFrame:
        """Najlepsza łatka z każdego regionu, posortowana rosnąco (jak max_per_region=1)."""
        df = pd.DataFrame({"region": self.regions, "d": dist})
        return df.groupby("region", as_index=False)["d"].min().sort_values("d").reset_index(drop=True)


def top_regions(ranked: pd.DataFrame, k: int = TOP_K) -> list[str]:
    return ranked["region"].head(k).tolist()


def feature_diagnostics(scorer: Scorer, moon: pd.DataFrame) -> pd.DataFrame:
    z_earth = pd.DataFrame(scorer.z_earth, columns=FEATURE_NAMES)
    z_moon = pd.DataFrame(transform(moon, scorer.scaler), columns=FEATURE_NAMES)
    corr = z_earth.corr(method="spearman").abs()
    rows = []
    moon_by_id = moon.set_index("patch_id")
    base = {
        pid: top_regions(scorer.ranked_regions(scorer.distance("default", row)))
        for pid, row in moon_by_id.iterrows()
    }
    for f in FEATURE_NAMES:
        groups = z_earth[f].groupby(scorer.regions)
        grand = z_earth[f].mean()
        between = (groups.size() * (groups.mean() - grand) ** 2).sum()
        icc = float(between / ((z_earth[f] - grand) ** 2).sum())  # udział wariancji między regionami (eta^2)
        keep = {g: (0.0 if g == f else 1.0) for g in FEATURE_NAMES}
        only = {g: (1.0 if g == f else 0.0) for g in FEATURE_NAMES}
        drop_ov, only_ov = [], []
        for pid, row in moon_by_id.iterrows():
            feats = {c: float(row[c]) for c in FEATURE_NAMES}
            for weights, store in ((keep, drop_ov), (only, only_ov)):
                d = distances(feats, scorer.earth, scorer.scaler, feature_weights=weights)["total_distance"]
                store.append(len(set(top_regions(scorer.ranked_regions(d.to_numpy()))) & set(base[pid])))
        rows.append(
            {
                "feature": f,
                "eta2_between_regions": round(icc, 3),
                "moon_out_of_range_share": round(float((z_moon[f].abs() > 3).mean()), 2),
                "moon_z_std": round(float(z_moon[f].std()), 2),
                "max_abs_spearman_with_other": round(float(corr[f].drop(f).max()), 2),
                "top10_overlap_when_dropped": round(float(np.mean(drop_ov)), 1),
                "top10_overlap_when_alone": round(float(np.mean(only_ov)), 1),
            }
        )
    return pd.DataFrame(rows)


def compare_schemes(scorer: Scorer, moon: pd.DataFrame, noise: float, seeds: int) -> pd.DataFrame:
    schemes = ["default", "equal", "group", "pca", "reduced"]
    moon_by_id = moon.set_index("patch_id")
    rng = np.random.default_rng(0)
    rows = []
    results = {s: {} for s in schemes}
    for s in schemes:
        for pid, row in moon_by_id.iterrows():
            results[s][pid] = scorer.ranked_regions(scorer.distance(s, row))
    for s in schemes:
        overlap_default = np.mean(
            [len(set(top_regions(results[s][p])) & set(top_regions(results["default"][p]))) for p in moon_by_id.index]
        )
        stable = []
        for pid, row in moon_by_id.iterrows():
            ref = set(top_regions(results[s][pid]))
            for _ in range(seeds):
                z_noise = rng.normal(0.0, noise, len(FEATURE_NAMES))
                ranked = scorer.ranked_regions(scorer.distance(s, row, z_noise))
                stable.append(len(ref & set(top_regions(ranked))))
        apollo_ranks = []
        for pid in APOLLO_SITES:
            regs = results[s][pid]["region"].tolist()
            apollo_ranks.append(regs.index(APOLLO_ANALOG) + 1)
        used = {r for p in moon_by_id.index for r in top_regions(results[s][p], 5)}
        top1 = np.mean([results[s][p]["d"].iloc[0] for p in moon_by_id.index])
        rows.append(
            {
                "scheme": s,
                "n_features_effective": {"pca": len(scorer.pca_sd), "reduced": len(REDUCED)}.get(s, 12),
                "top10_overlap_with_default": round(float(overlap_default), 1),
                f"top10_stability_noise{noise}": round(float(np.mean(stable)), 2),
                "cinder_lake_rank_apollo_mean": round(float(np.mean(apollo_ranks)), 1),
                "regions_in_top5_all_sites": len(used),
            }
        )
    return pd.DataFrame(rows)


def coverage_gaps(scorer: Scorer, moon: pd.DataFrame) -> pd.DataFrame:
    """Miejsca Księżyca bez bliskiego odpowiednika na Ziemi: najlepsza odległość i cechy poza zakresem Ziemi."""
    z_moon = pd.DataFrame(transform(moon, scorer.scaler), columns=FEATURE_NAMES)
    rows = []
    for i, row in moon.iterrows():
        best = scorer.ranked_regions(scorer.distance("default", row)).iloc[0]
        out = {f: round(float(z_moon.loc[i, f]), 1) for f in FEATURE_NAMES if abs(z_moon.loc[i, f]) > 3}
        rows.append(
            {"patch_id": row["patch_id"], "best_region": best["region"], "best_distance": round(float(best["d"]), 2), "features_outside_earth_|z|>3": out}
        )
    return pd.DataFrame(rows).sort_values("best_distance", ascending=False)


def noise_reliability(earth: pd.DataFrame, sigma_m: float, n: int, seed: int = 0) -> pd.DataFrame:
    """Spearman między cechą z oryginalnej łatki a cechą po dodaniu szumu pionowego (odporność na błędy DEM)."""
    rng = np.random.default_rng(seed)
    ids = earth["patch_id"].sample(min(n, len(earth)), random_state=seed)
    orig, noisy = [], []
    for pid in ids:
        patch = np.load(DATA_DIR / "patches" / "earth" / f"{pid}.npy").astype(np.float64)
        orig.append(extract_patch_features(patch, PIXEL_SIZE_M))
        noisy.append(extract_patch_features(patch + rng.normal(0.0, sigma_m, patch.shape), PIXEL_SIZE_M))
    orig, noisy = pd.DataFrame(orig), pd.DataFrame(noisy)
    return pd.DataFrame(
        {
            "feature": FEATURE_NAMES,
            f"spearman_orig_vs_noise{sigma_m:g}m": [round(float(spearmanr(orig[f], noisy[f])[0]), 3) for f in FEATURE_NAMES],
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--noise", type=float, default=0.3, help="odch. std szumu dodawanego do z-score Księżyca")
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--vertical-noise-m", type=float, default=5.0, help="szum pionowy DEM do testu odporności cech")
    parser.add_argument("--noise-patches", type=int, default=1000)
    args = parser.parse_args()

    earth = pd.read_csv(DATA_DIR / "earth_index.csv")
    moon = pd.read_csv(DATA_DIR / "moon_index.csv")
    scorer = Scorer(earth)
    OUTPUT_DIR.mkdir(exist_ok=True)

    z = pd.DataFrame(scorer.z_earth, columns=FEATURE_NAMES)
    ev = np.linalg.eigvalsh(np.cov(scorer.z_earth, rowvar=False))[::-1]
    print(f"PCA: {len(scorer.pca_sd)} składowe wyjaśniają 95% wariancji; udziały {np.round(ev / ev.sum(), 2)[:4]}")
    rho = spearmanr(z["hypsometric_integral"], z["elev_skew"])[0]
    print(f"hypsometric_integral vs elev_skew: Spearman {rho:.2f}\n")

    diag = feature_diagnostics(scorer, moon)
    diag = diag.merge(noise_reliability(earth, args.vertical_noise_m, args.noise_patches), on="feature")
    diag.to_csv(OUTPUT_DIR / "feature_diagnostics.csv", index=False)
    print("A. Diagnostyka cech\n", diag.to_string(index=False), "\n")

    gaps = coverage_gaps(scorer, moon)
    gaps.to_csv(OUTPUT_DIR / "coverage_gaps.csv", index=False)
    print("C. Luki w pokryciu Ziemi (najgorsze dopasowania)\n", gaps.head(6).to_string(index=False), "\n")

    comp = compare_schemes(scorer, moon, args.noise, args.seeds)
    comp.to_csv(OUTPUT_DIR / "scoring_schemes.csv", index=False)
    print("B. Schematy ważenia\n", comp.to_string(index=False))


if __name__ == "__main__":
    main()

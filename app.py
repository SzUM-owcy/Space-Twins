"""Streamlit: znajdź na Ziemi analogi miejsca z Księżyca (CONTRACT §5, §6).

    uv run streamlit run app.py

Opcja „miejsce z listy” działa na samych plikach z gita (CSV + .npy/.npz). Własne współrzędne
wymagają rastra LOLA w data/lola/ (config.LOLA_GLOBAL_PATH); bez niego opcja jest wyłączona.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from config import (
    DATA_DIR,
    FEATURE_NAMES,
    LOLA_GLOBAL_PATH,
    PIXEL_SIZE_M,
    SHAPE_FEATURES,
    SLOPE_FEATURES,
)
from src.morphometry import extract_patch_features
from src.plotting import load_earth_patch, plot_comparison
from src.query import PatchRejected, find_analogs, moon_patch_for

EARTH_INDEX = DATA_DIR / "earth_index.csv"
MOON_INDEX = DATA_DIR / "moon_index.csv"
MOON_PATCH_DIR = DATA_DIR / "patches" / "moon"

FEATURE_UNITS = {
    **{name: "°" for name in SLOPE_FEATURES},
    "rms_height": "m",
    "tri_mean": "m",
    "relief_range": "m",
    "hypsometric_integral": "",
    "elev_skew": "",
}
SOURCE_SITE, SOURCE_CUSTOM = "Miejsce z listy", "Własne współrzędne"

st.set_page_config(page_title="Analogi Księżyc → Ziemia", layout="wide")


@st.cache_data
def load_indexes() -> tuple[pd.DataFrame, pd.DataFrame]:
    return pd.read_csv(EARTH_INDEX), pd.read_csv(MOON_INDEX)


@st.cache_data
def load_moon_site_patch(patch_id: str) -> np.ndarray:
    return np.load(MOON_PATCH_DIR / f"{patch_id}.npy").astype(np.float64)


@st.cache_data
def load_earth_patch_cached(patch_id: str) -> np.ndarray | None:
    return load_earth_patch(patch_id)


@st.cache_data(show_spinner="Wycinam łatkę z LOLA…")
def custom_moon_patch(lat: float, lon: float) -> np.ndarray:
    return moon_patch_for(lat, lon)


def sidebar_moon_choice(moon_index: pd.DataFrame) -> dict | None:
    """Wybór miejsca na Księżycu. Zwraca {label, lat, lon, patch_fn} albo None (błędny wybór)."""
    custom_ok = LOLA_GLOBAL_PATH.exists()
    options = [SOURCE_SITE, SOURCE_CUSTOM]
    source = st.sidebar.radio("Źródło łatki", options, index=0)

    if source == SOURCE_SITE:
        sites = moon_index.set_index("region")
        slug = st.sidebar.selectbox("Miejsce na Księżycu", list(sites.index))
        row = sites.loc[slug]
        st.sidebar.caption(f"{row.center_lat:.3f}°, {row.center_lon:.3f}° · {row.patch_id}")
        return {
            "label": slug,
            "lat": float(row.center_lat),
            "lon": float(row.center_lon),
            "patch_fn": lambda: load_moon_site_patch(row.patch_id),
        }

    if not custom_ok:
        st.sidebar.warning(
            f"Własne współrzędne wymagają rastra LOLA: brak pliku `{LOLA_GLOBAL_PATH}` "
            "na tym komputerze. Wybierz miejsce z listy."
        )
        return None
    lat = st.sidebar.number_input("Szerokość [°]", -90.0, 90.0, 14.0725, step=0.01, format="%.4f")
    lon = st.sidebar.number_input("Długość [°, wschodnia dodatnia]", -180.0, 180.0, -56.7493, step=0.01, format="%.4f")
    st.sidebar.caption("Obsługiwane: |szerokość| ≤ 75° oraz ≤ −80° (pas 75–80° i północ pomijamy).")
    return {
        "label": f"własny punkt ({lat:.3f}, {lon:.3f})",
        "lat": lat,
        "lon": lon,
        "patch_fn": lambda: custom_moon_patch(lat, lon),
    }


def run_query(choice: dict, earth: pd.DataFrame, top_k: int, w_slope: float, per_region: bool) -> dict | None:
    """Wycina łatkę, liczy cechy i ranking; błędy użytkownika pokazuje jako komunikat."""
    try:
        patch = choice["patch_fn"]()
        features = extract_patch_features(patch, PIXEL_SIZE_M)
        result = find_analogs(features, earth, top_k=top_k, w_slope=w_slope, max_per_region=1 if per_region else None)
    except PatchRejected as err:
        st.error(f"Tej łatki nie da się wyciąć: {err}")
        return None
    except ValueError as err:
        st.error(f"Błąd: {err}")
        return None
    return {
        "label": choice["label"],
        "lat": choice["lat"],
        "lon": choice["lon"],
        "w_slope": w_slope,
        "patch": patch,
        "features": features,
        "result": result,
        "out_of_range": list(result.attrs["out_of_range"]),
    }


def show_results(q: dict) -> None:
    result: pd.DataFrame = q["result"]
    st.subheader(f"Analogi dla: {q['label']}")
    st.caption(f"w_slope = {q['w_slope']:.2f} (nachylenia) · {1 - q['w_slope']:.2f} (kształt). Mniejsza odległość = większe podobieństwo.")

    if q["out_of_range"]:
        st.warning(
            "Cechy tego miejsca wychodzą poza zakres Ziemi w indeksie (|z| > 3): "
            f"**{', '.join(q['out_of_range'])}**. Ranking może być mniej wiarygodny."
        )

    st.dataframe(
        result.rename(columns={"slope_distance": "odl. nachyleń", "shape_distance": "odl. kształtu", "total_distance": "odl. łączna"}),
        hide_index=True,
        width="stretch",
        column_config={
            "center_lat": st.column_config.NumberColumn("lat", format="%.3f"),
            "center_lon": st.column_config.NumberColumn("lon", format="%.3f"),
            "odl. nachyleń": st.column_config.NumberColumn(format="%.3f"),
            "odl. kształtu": st.column_config.NumberColumn(format="%.3f"),
            "odl. łączna": st.column_config.NumberColumn(format="%.3f"),
        },
    )

    rank = st.selectbox(
        "Pokaż szczegóły analogu",
        result["rank"].tolist(),
        format_func=lambda r: f"#{r} · {result.loc[result['rank'] == r, 'region'].iloc[0]}",
    )
    analog = result[result["rank"] == rank].iloc[0]
    earth_patch = load_earth_patch_cached(analog.patch_id)
    earth_label = f"{analog.region} ({analog.center_lat:.2f}, {analog.center_lon:.2f})"

    fig = plot_comparison(q["patch"], earth_patch, q["label"], earth_label)
    st.pyplot(fig, width="stretch")

    c1, c2, c3 = st.columns(3)
    c1.metric("Odległość nachyleń", f"{analog.slope_distance:.3f}")
    c2.metric("Odległość kształtu", f"{analog.shape_distance:.3f}")
    c3.metric("Odległość łączna", f"{analog.total_distance:.3f}")

    earth_row = load_earth_features(analog.patch_id)
    table = pd.DataFrame(
        {
            "grupa": ["nachylenia"] * len(SLOPE_FEATURES) + ["kształt"] * len(SHAPE_FEATURES),
            "cecha": FEATURE_NAMES,
            "jednostka": [FEATURE_UNITS[f] for f in FEATURE_NAMES],
            "Księżyc": [q["features"][f] for f in FEATURE_NAMES],
            "analog (Ziemia)": [earth_row[f] for f in FEATURE_NAMES],
        }
    )
    st.markdown("**Surowe wartości cech** (przed log1p i normalizacją)")
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        column_config={
            "Księżyc": st.column_config.NumberColumn(format="%.3f"),
            "analog (Ziemia)": st.column_config.NumberColumn(format="%.3f"),
        },
    )


def load_earth_features(patch_id: str) -> pd.Series:
    earth, _ = load_indexes()
    return earth.set_index("patch_id").loc[patch_id]


def show_limitations() -> None:
    st.divider()
    with st.expander("Ograniczenia i interpretacja", expanded=True):
        st.markdown(
            """
- **To podobieństwo cech wynikających z wysokości, a nie przydatność lądowiska, bezpieczeństwo misji ani równoważność geologiczna.**
- Siatka LOLA 118 m jest w dużej części interpolowana między śladami altimetru, więc nachylenia i TRI Księżyca są nieco wygładzone względem Ziemi uśrednionej z prawdziwych 30 m. Wynik może systematycznie faworyzować płaskie analogi.
- Skaler i próg |z| > 3 zależą od ręcznie wybranego składu regionów Ziemi; łatki z jednego regionu są silnie skorelowane. Indeks nie jest próbą reprezentatywną dla całej Ziemi.
- NASADEM to model powierzchni (z koronami drzew), więc indeks celowo opiera się na terenach pustynnych i wulkanicznych; roślinność mogłaby zaburzać cechy.
- Różnica efektywnej rozdzielczości Księżyc/Ziemia (patrz wyżej). Łatki mają 10×10 km (85×85 px).
- Domyślnie z każdego regionu pokazujemy najwyżej jedną łatkę (inaczej ranking zajmuje jeden region).
"""
        )


def main() -> None:
    st.title("Analogi Księżyc → Ziemia")
    st.caption("Które miejsca na Ziemi mają rzeźbę podobną do wybranego miejsca na Księżycu? (łatki 10×10 km, 12 cech z modelu wysokości)")

    try:
        earth, moon_index = load_indexes()
    except FileNotFoundError as err:
        st.error(f"Brak pliku z indeksem: {err.filename}")
        st.stop()

    st.sidebar.header("Zapytanie")
    choice = sidebar_moon_choice(moon_index)
    top_k = st.sidebar.slider("Liczba analogów (top-K)", 1, 10, 5)
    w_slope = st.sidebar.slider("Waga nachyleń (w_slope)", 0.0, 1.0, 0.5, 0.05, help="0 = tylko kształt, 1 = tylko nachylenia")
    per_region = st.sidebar.checkbox("Jedna łatka na region", value=True)
    go = st.sidebar.button("Znajdź analogi", type="primary", disabled=choice is None)

    if go and choice is not None:
        st.session_state["query"] = run_query(choice, earth, top_k, w_slope, per_region)

    q = st.session_state.get("query")
    if q is not None:
        show_results(q)
    elif not go:
        st.info("Wybierz miejsce w panelu po lewej i kliknij **Znajdź analogi**.")
    show_limitations()


main()

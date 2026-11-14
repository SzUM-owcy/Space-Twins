# Composition proxy validation

`mafic_felsic_percentile` (0 = more felsic, 1 = more mafic, relative to its own body) is a coarse thermal-infrared
proxy: ASTER GED emissivity ratio on Earth, Diviner Christiansen Feature (CF) wavelength on the Moon. Raw Earth
and Moon values are never compared; each is converted to a percentile within its own body. Reproduce with
`uv run --frozen python 1e_build_composition.py validate` (writes `outputs/composition_validation.csv` and `.png`).

## Moon (done)

Product: `diviner_CF_space_weathering_corrected.tiff` (Zenodo 4558194; corrected for viewing geometry and space
weathering), 32 pixels/degree, ±70° latitude. The file has no georeferencing; the grid (row 0 = +70°, column 0 =
−180° east-positive) was identified by checking that mare locations read about 8.3 µm and highlands about 8.17 µm,
whereas a 0–360° origin gave no mare/highland contrast. The earlier viewing-geometry-only map (`DIVGLOB1701_CX3`)
is kept for comparison in `data/composition_moon_cf_comparison.csv`.

| Class | Sites (patch median CF, µm) |
|---|---|
| Mare (mafic) | Marius Hills 8.303, Mare Imbrium 8.299, Apollo 11 8.290, Mare Serenitatis 8.281, Apollo 12 8.267, Apollo 17 8.253 |
| Highlands (felsic) | Apollo 16 8.175, Maurolycus 8.171, Hipparchus 8.162 |

Every mare site is above every highland site (class medians 8.286 vs 8.171), so higher CF = more mafic
(`direction = higher_is_mafic`). The correction narrows the contrast and lifts the fresh craters off the extreme low
end (Tycho 8.036 to 8.191, Aristarchus 7.943 to 8.086; Aristarchus is still the lowest). The Diviner mineral rasters
agree (`data/composition_moon_minerals.csv`: mare 28-42 percent plagioclase and 46-63 percent pyroxene, Apollo 16 and
the highland sites about 82 percent plagioclase). The reference distribution uses 1552 area-uniform 5° cells within ±70°
(`data/processed/moon_composition_reference.json`). The 4 polar sites (Shackleton, Haworth, de Gerlache, Malapert)
are `outside_diviner_cf_coverage` and drop out of the score.

## Earth (not run yet)

ASTER GED AG100.003 is not available without credentials: the LP DAAC download redirects to the NASA Earthdata
login (free account), and the dataset is not on the Planetary Computer. The reader and builder are written and were
checked only on a synthetic AG100-style HDF5 tile (mafic half gives MI 1.016, felsic half 0.985; water and
vegetation pixels are excluded). Two assumptions must be confirmed on the first real tile: the HDF5 dataset names
(found by keyword) and the land value of the land/water map (`ASTER_LAND_CLASS = 1` in `config.py`).

To run it, add `machine urs.earthdata.nasa.gov login USER password PASS` to `~/.netrc` (or place the `.h5`
tiles in `data/aster_ged/`), then `1e_build_composition.py earth`, `validate`, `finalize`. Planned checks:

- mafic regions (craters_of_the_moon, mauna_loa, carrizozo, zuni_bandera, lava_beds, paricutin) vs
  anorthosite / felsic regions (sittampundi, saririaky, kamestastin): the median MI ordering decides the Earth
  direction (`finalize` picks it from this ordering and stores it in the reference; it is not assumed);
- confounders (white_sands gypsum, erg_chebbi / namib dunes, uyuni / dalangtan salt, lonar): QI and valid-pixel
  ratio are reported, QI above the Earth 95th percentile gives `low_quartz_confounder` confidence;
- no hard percentile thresholds are set before the observed distributions are seen.

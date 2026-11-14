# Composition proxy validation

`mafic_felsic_percentile` (0 = more felsic, 1 = more mafic, relative to its own body) is a coarse thermal-infrared
proxy: ASTER GED emissivity ratio on Earth, Diviner Christiansen Feature (CF) wavelength on the Moon. Raw Earth
and Moon values are never compared; each is converted to a percentile within its own body. Reproduce with
`uv run --frozen python 1e_build_composition.py validate` (writes `outputs/composition_validation.csv` and `.png`).

## Moon (done)

Product: `DIVGLOB1701_CX3` (Zenodo 4558235), 32 pixels/degree, ±70° latitude. The file has no georeferencing; the
grid (row 0 = +70°, column 0 = −180° east-positive) was identified by checking that mare locations read about
8.30 µm and highlands about 8.1 µm, whereas a 0–360° origin gave no mare/highland contrast.

| Class | Sites (patch median CF, µm) |
|---|---|
| Mare (mafic) | Apollo 11 8.300, Marius Hills 8.301, Mare Imbrium 8.289, Mare Serenitatis 8.284, Apollo 17 8.277, Apollo 12 8.269 |
| Highlands (felsic) | Apollo 16 8.149, Maurolycus 8.137, Hipparchus 8.130 |

Every mare site is above every highland site (class medians 8.286 vs 8.137), so higher CF = more mafic
(`direction = higher_is_mafic`). Fresh craters read lowest (Tycho 8.036, Aristarchus 7.943), consistent with
plagioclase-rich / immature material. The reference distribution uses 1552 area-uniform 5° cells within ±70°
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

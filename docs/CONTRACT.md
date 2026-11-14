# KONTRAKT (źródło prawdy dla obu osób)

> Ten dokument definiuje wszystko, co musi być **identyczne** po stronie Ziemi i Księżyca.
> Jeśli kod i kontrakt się różnią, **kontrakt wygrywa** (albo go zmieniacie wspólnie – patrz §0).
> Instrukcje pracy: [PERSON_A_EARTH.md](PERSON_A_EARTH.md), [PERSON_B_MOON.md](PERSON_B_MOON.md).

## 0. Zasady zmiany kontraktu

- Zmiana kontraktu = osobny commit na `main` zmieniający tylko ten plik (+ ewentualnie `config.py`/`src/contracts.py`) **i** wiadomość do drugiej osoby.
- Nie zmieniacie definicji cechy „po cichu” w swoim kodzie. Zmiana definicji cechy oznacza przeliczenie obu indeksów, więc po ok. T+8h robimy to tylko w ostateczności.
- Konwencja czasu: **T+0 = start hackathonu**, całość ma ok. 24 h.

---

## 1. Geometria łatki

| Parametr | Wartość |
|---|---|
| Rozmiar łatki | **10 km × 10 km** (kwadrat w lokalnym układzie metrycznym) |
| Siatka | **85 × 85 pikseli** |
| Rozmiar piksela | `PIXEL_SIZE_M = 10_000 / 85 ≈ 117.647 m` |
| Środek łatki | `(center_lat, center_lon)` |
| Orientacja | wiersz 0 = północ, kolumna 0 = zachód |
| Typ danych | `float64` w obliczeniach, `float32` przy zapisie `.npy` |
| Jednostka wysokości | **metry** |
| Konwencja długości geograficznej | **wschodnia dodatnia, zakres −180…180** (Marius Hills ≈ 14.0, −56.0). Z recenzji: globalny LOLA 118 m ma już długości −180…180 – **sprawdźcie `gdalinfo`**; konwersja 0…360 jest potrzebna tylko, jeśli plik albo dane wejściowe od użytkownika tego wymagają |

Wybór 85 × 85 nie jest przypadkowy: natywna rozdzielczość LOLA 118 m daje ok. 85 px na 10 km, więc Księżyc jest **w przybliżeniu** 1:1 (piksel rastra ma 118.45 m wzdłuż południka, ale tylko ok. 118.45·cos(lat) m wzdłuż równoleżnika), a Ziemia (NASADEM, 1″ ≈ 30 m) jest uśredniana ok. 4 × 4.

**Znane ograniczenie (musi trafić do README/UI):** siatka LOLA 118 m jest w dużej części interpolowana między śladami altimetru, więc nachylenia i TRI Księżyca są nieco wygładzone względem Ziemi uśrednionej z prawdziwych 30 m. Wynik może systematycznie faworyzować płaskie analogi.

## 2. Ekstrakcja łatki z rastra (algorytm identyczny dla obu ciał)

Funkcja: `src/raster_io.py::extract_patch(...)` (patrz §6). Algorytm:

1. **Docelowy CRS** to azymutalny równoodległościowy wyśrodkowany na łatce:
   ```
   +proj=aeqd +lat_0={center_lat} +lon_0={center_lon} +x_0=0 +y_0=0 {DATUM} +units=m +no_defs
   ```
   - Ziemia: `DATUM = "+datum=WGS84"`, CRS źródłowy `EPSG:4326` (stopnie).
   - Księżyc: `DATUM = "+R=1737400"` (kula 1737.4 km). **CRS źródłowy bierzemy z pliku LOLA** (według recenzji to projekcja equirectangular ze współrzędnymi **w metrach**, nie w stopniach – nie wolno go nadpisywać na `longlat`). Jeśli PROJ nie rozpozna księżycowego CRS z pliku, nadpisujemy **tylko wtedy** na: `+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +R=1737400 +units=m +no_defs`. Stała `LOLA_CRS_FALLBACK` w `config.py`. Zweryfikujcie to w `gdalinfo` przed użyciem.
2. **Odczyt źródła do tablicy**: wycinamy z rastra okno obejmujące łatkę + margines (łatka ±5 km w układzie docelowym, przeliczona na okno źródłowe, +kilka pikseli zapasu) i czytamy je do `ndarray`; dalej `reproject` bierze tablicę z jawnymi `src_transform` i `src_crs`. Wartości źródła: `nodata → NaN` (nodata podaje wywołujący jawnie, NASADEM i LOLA: `-32768`; **nie polegamy na `src.nodata`**, bo może być `None`), potem `z = value * scale + offset`. **`extract_patch` NIE czyta `src.scales`/`src.offsets`** – skalę podaje wywołujący (LOLA: `LOLA_SCALE = 0.5`, NASADEM: `1.0`), żeby nie skalować dwa razy.
3. **Odrzucenie na poziomie źródła**: jeśli w oknie źródłowym (zakres łatki, bez marginesu) jest **jakikolwiek** piksel nodata → `None`. (Powód: `Resampling.average` w GDAL pomija nodata i zwraca wartość, jeśli w pikselu docelowym jest choć jeden ważny piksel źródłowy, więc sam test NaN po `reproject` nie wyłapie częściowych dziur.) Jeśli okno wychodzi poza raster → `None`.
4. **Siatka docelowa**: `transform = rasterio.transform.from_bounds(-5000, -5000, 5000, 5000, 85, 85)`, wymiary 85 × 85.
5. **Resampling**: `rasterio.warp.reproject(..., resampling=Resampling.average, dst_nodata=nan)`.
6. **Walidacja po `reproject`**: jeśli w łatce jest **jakikolwiek** piksel niefinitywny (NaN/inf) → `None`. Nie wypełniamy dziur.
7. Dodatkowo tylko dla Ziemi (wody): `None`, jeśli **więcej niż 5% pikseli źródłowych w oknie ma wysokość dokładnie `0`** albo **więcej niż 20% pikseli wewnętrznych ma nachylenie dokładnie `0°`** (jeziora w SRTM/NASADEM są spłaszczone do stałej wysokości). A sprawdza na początku, czy te progi nie wycinają prawdziwie płaskich regionów (Uyuni, Black Rock) – w razie czego podnosi próg i zapisuje to tu.
   **Inne produkty DEM używają tego samego algorytmu** – zmienia się tylko plik wejściowy, `nodata`, `scale` i CRS źródłowy:
   - **COPDEM** (Ziemia, regiony >60°N): `EPSG:4326`, `scale=1.0`, `nodata` do sprawdzenia empirycznie (A). Liczba kolumn w kafelku GLO-30 zmienia się z szerokością geograficzną (większy krok po długości na wysokich szerokościach) – `reproject` to obsługuje, ale mozaikuj kafelki dopiero po wczytaniu z georeferencją. Woda i ocean są spłaszczone, więc reguły §2 pkt 7 obowiązują.
   - **LOLA polarny** (Księżyc, ≤ −80° szerokości): produkty w stereografii polarnej (metry), np. `LDEM_80S_20M` (nazwę, CRS, skalę i nodata **zweryfikuj w `gdalinfo`**, tak jak dla produktu globalnego). Używamy CRS z pliku, a docelowy aeqd wyśrodkowany na łatce działa także tuż przy biegunie. Wybór produktu: |lat| ≤ 75° → globalny 118 m; lat ≤ −80° → polarny; pomiędzy → odrzucamy.
8. **Test round-trip (obowiązkowy w C2)**: środek łatki (lat, lon) po transformacji do docelowego aeqd to (0, 0) z dokładnością < 1 m, dla Ziemi i dla Księżyca; oraz łatki Księżyca w (0, 0) i (14, −56) dają wysokości w sensownym zakresie (−9150…+10800 m).

Uzasadnienie: ta sama procedura po obu stronach oznacza, że różnice w cechach wynikają z terenu, a nie z odmiennego przetwarzania. **Nie** używamy żadnych innych resamplingów (bilinear/cubic) ani wygładzania.

## 3. Cechy terenu (dokładnie 12)

Funkcja: `src/morphometry.py::extract_patch_features(patch: np.ndarray, pixel_size_m: float) -> dict[str, float]`.

**Wejście:** `patch` o kształcie `(85, 85)`, `float`, w metrach, **bez NaN**. `pixel_size_m = PIXEL_SIZE_M`.
**Wyjście:** słownik z **dokładnie** kluczami z `FEATURE_NAMES` (wartości to zwykłe `float` Pythona).

### Nachylenie (stopnie)

Liczone **metodą Horna** (jądro 3×3), tylko dla pikseli wewnętrznych (**83 × 83**, krawędzie pomijamy – bez paddingu). Dla okna
```
a b c
d e f
g h i
```
```
dz/dx = ((c + 2f + i) − (a + 2d + g)) / (8 · pixel_size_m)
dz/dy = ((g + 2h + i) − (a + 2b + c)) / (8 · pixel_size_m)
slope_deg = degrees(arctan(sqrt(dz/dx² + dz/dy²)))
```
Percentyle: `np.percentile(slope_deg, q)` (interpolacja liniowa, domyślna).

| Cecha | Definicja |
|---|---|
| `slope_p05` | 5. percentyl nachylenia [°] |
| `slope_p10` | 10. percentyl [°] |
| `slope_p25` | 25. percentyl [°] |
| `slope_p50` | mediana [°] |
| `slope_p75` | 75. percentyl [°] |
| `slope_p90` | 90. percentyl [°] |
| `slope_p95` | 95. percentyl [°] |

### Kształt terenu

| Cecha | Definicja | Jednostka |
|---|---|---|
| `rms_height` | RMS reszt po odjęciu **płaszczyzny najlepszego dopasowania** (`z = ax + by + c`, metoda najmniejszych kwadratów, `x,y` w metrach, cała łatka 85×85): `sqrt(mean(residual²))` | m |
| `tri_mean` | **TRI Rileya (1999)** na pikselach wewnętrznych: `sqrt(Σ_8 sąsiadów (z_sąsiad − z_środek)²)`, następnie średnia po 83×83 | m |
| `relief_range` | `max(z) − min(z)` po całej łatce 85×85 | m |
| `hypsometric_integral` | `(mean(z) − min(z)) / (max(z) − min(z))` po całej łatce; jeśli `ptp(z) < 1e-6` → `0.5` (neutralna wartość; `0.0` byłoby ekstremum i zniekształcałoby z-score) | bezwymiarowa, 0…1 |
| `elev_skew` | skośność rozkładu wysokości, `scipy.stats.skew(z.ravel())` (bias=True, domyślnie); jeśli `ptp(z) < 1e-6` → `0.0` | bezwymiarowa |

### Zakazy

- Żadnych dodatkowych cech w słowniku (dodatkowe kolumny w indeksie są dozwolone, patrz §4, ale nie w `extract_patch_features`).
- Żadnych NaN w wyniku. Funkcja rzuca `ValueError`, jeśli wejście ma zły kształt lub zawiera NaN.

## 4. Schemat rekordu i pliki

### Kolumny (kolejność obowiązkowa, 17 kolumn)

```
patch_id, source, region, center_lat, center_lon,
slope_p05, slope_p10, slope_p25, slope_p50, slope_p75, slope_p90, slope_p95,
rms_height, tri_mean, relief_range, hypsometric_integral, elev_skew
```

| Kolumna | Typ | Reguły |
|---|---|---|
| `patch_id` | str | unikalny, `[a-z0-9_]`; Ziemia: `earth_{region}_{NNNN}`; Księżyc: `moon_{site}` |
| `source` | str | `NASADEM`, `COPDEM` (Copernicus DEM GLO-30, dla regionów >60°N, np. Islandia i Devon Island) albo `LOLA` (zarówno produkt globalny, jak i polarny) |
| `region` | str | slug `[a-z0-9_]` (Ziemia: nazwa regionu, Księżyc: nazwa miejsca) |
| `center_lat`, `center_lon` | float | stopnie dziesiętne, lon wschodnia dodatnia −180…180 |
| 12 cech | float | zgodnie z §3, bez NaN |

### Pliki

| Plik | Właściciel | W gicie? | Opis |
|---|---|---|---|
| `data/earth_index.csv` | A | tak | wszystkie łatki Ziemi (docelowo 1000–3000 wierszy) |
| `data/moon_index.csv` | B | tak | wybrane miejsca Księżyca (10–20 wierszy) |
| `data/patches/moon/{patch_id}.npy` | B | tak | łatka 85×85 `float32`, metry |
| `data/patches/earth/{patch_id}.npy` | A | **nie** | robocze łatki 85×85 `float32` na maszynie A |
| `data/patches/earth_patches.npz` | A | **tak, raz** (po C4, ok. 20–90 MB) | `np.savez_compressed`, klucze = `patch_id`, wartości `float32`. Dzięki temu wykres porównawczy działa na czystym klonie. Nie commitujemy go wielokrotnie (historia gita puchnie) – jedna wersja po C4, ewentualnie jedna poprawka po C5 |
| `data/nasadem/`, `data/lola/` | – | **nie** (`.gitignore`) | surowe rastry, każdy ma lokalnie |
| `outputs/latest_query.json` | B | nie | wynik ostatniego zapytania, schemat w §5 |

CSV: kodowanie UTF-8, separator `,`, kropka dziesiętna, nagłówek, `float` zapisywane z pełną precyzją (`float_format=None`).

## 5. Scoring (porównanie Księżyc ↔ Ziemia)

Implementuje B (`src/scoring.py`, `src/query.py`); A korzysta z tej definicji tylko przy walidacji.

**Grupy cech:**
- `SLOPE_FEATURES` = 7 cech `slope_p05 … slope_p95`
- `SHAPE_FEATURES` = `rms_height, tri_mean, relief_range, hypsometric_integral, elev_skew`

**Przygotowanie (`fit_scaler(earth_df)`):**
1. Dla `rms_height`, `tri_mean`, `relief_range` stosujemy `log1p` (rozkłady z ciężkim ogonem).
2. Standaryzacja z-score z użyciem **średniej i odchylenia standardowego indeksu Ziemi** (po log1p). Jeśli `std == 0` → używamy `1.0`.
3. Wektor Księżyca jest transformowany **tym samym** skalerem (statystyki Ziemi, nie Księżyca).

**Odległości (dla jednego Księżyca i jednej łatki Ziemi):**
```
slope_distance = sqrt( mean_over_SLOPE_FEATURES( (z_moon − z_earth)² ) )
shape_distance = sqrt( mean_over_SHAPE_FEATURES( (z_moon − z_earth)² ) )
total_distance = w_slope · slope_distance + (1 − w_slope) · shape_distance
```
Domyślnie `w_slope = 0.5`; `w_slope ∈ [0, 1]` (suwak w UI). Mniejsza odległość = bardziej podobny teren.

**Ranking:**
```python
find_analogs(moon_features: dict, earth_index: pd.DataFrame,
             top_k: int = 5, w_slope: float = 0.5,
             max_per_region: int = 1) -> pd.DataFrame
```
- `max_per_region = 1`: dla każdego regionu bierzemy tylko najlepszą łatkę, potem top-K regionów (żeby nie dostać 5 sąsiednich łatek z jednego miejsca). `None` = bez limitu.
- Zwracany `DataFrame` ma kolumny: `rank, patch_id, region, center_lat, center_lon, slope_distance, shape_distance, total_distance`, posortowany rosnąco po `total_distance`.
- Ostrzeżenie „poza zakresem”: jeśli któraś cecha Księżyca po standaryzacji ma `|z| > 3` względem Ziemi, `find_analogs` zapisuje listę takich cech w `df.attrs["out_of_range"]`.

**`outputs/latest_query.json`:**
```json
{
  "moon": {"patch_id": "...", "center_lat": 0.0, "center_lon": 0.0, "features": {"slope_p05": 0.0}},
  "w_slope": 0.5, "top_k": 5, "max_per_region": 1,
  "out_of_range": [],
  "results": [{"rank": 1, "patch_id": "...", "region": "...", "center_lat": 0.0, "center_lon": 0.0,
               "slope_distance": 0.0, "shape_distance": 0.0, "total_distance": 0.0}]
}
```

**Interpretacja (musi trafić do UI i README):** wynik to podobieństwo wybranych cech wynikających z wysokości, a nie przydatność lądowiska, bezpieczeństwo misji ani równoważność geologiczna.

**Dodatkowe ograniczenia do opisania w README/UI:**
- Skaler i próg `|z| > 3` zależą od ręcznie wybranego składu regionów Ziemi; łatki z jednego regionu są silnie skorelowane. Indeks nie jest próbą reprezentatywną dla całej Ziemi.
- NASADEM to model powierzchni (z koronami drzew), więc indeks celowo opiera się na terenach pustynnych/wulkanicznych; roślinność mogłaby zaburzać cechy.
- Różnica efektywnej rozdzielczości Księżyc/Ziemia (§1).
- **UI pokazuje także surowe wartości cech** Księżyc vs wybrany analog (nie tylko odległości), żeby użytkownik mógł ocenić podobieństwo.

## 6. API modułów

| Moduł | Funkcja | Właściciel |
|---|---|---|
| `config.py` | stałe: `PATCH_SIZE_M=10_000`, `GRID_N=85`, `PIXEL_SIZE_M`, `MOON_RADIUS_M=1_737_400`, `LOLA_SCALE=0.5`, `LOLA_NODATA=-32768`, `NASADEM_NODATA=-32768`, `LOLA_CRS_FALLBACK` (§2 pkt 1), `FEATURE_NAMES`, `SLOPE_FEATURES`, `SHAPE_FEATURES`, `RECORD_COLUMNS`, ścieżki. Wartości LOLA zweryfikuje B po `gdalinfo` i zgłosi poprawki A | A |
| `src/contracts.py` | `validate_records(df: pd.DataFrame) -> None` (rzuca `ValueError`: złe kolumny, NaN, duplikaty `patch_id`, zły `source`, lon poza zakresem) | A |
| `src/raster_io.py` | `extract_patch(src: rasterio.DatasetReader, center_lat: float, center_lon: float, body: Literal["earth","moon"], src_crs: CRS \| None = None, nodata: float \| None = None, scale: float = 1.0, offset: float = 0.0) -> np.ndarray \| None` – zwraca `(85,85) float64` albo `None` (odrzucona). Algorytm: §2. `src_crs=None` → CRS z pliku; `nodata` jawny (nie z `src.nodata`); `z = value * scale + offset`; funkcja **nie czyta** `src.scales` | A |
| `src/morphometry.py` | `extract_patch_features(patch, pixel_size_m) -> dict` | B |
| `src/scoring.py` | `fit_scaler(earth_df)`, `distances(moon_features, earth_df, scaler, w_slope)` | B |
| `src/query.py` | `find_analogs(...)` (§5), `moon_features_for(lat, lon, lola_path) -> dict` (na żywo z rastra na dysku; używa `extract_patch` + `extract_patch_features`; skala, nodata i CRS z `config.py`) | B |
| `src/plotting.py` | `plot_comparison(moon_patch: np.ndarray, earth_patch: np.ndarray, moon_label: str, earth_label: str) -> matplotlib.figure.Figure` – dwa obok siebie: cieniowany relief (hillshade) + wspólna skala wysokości względem minimum łatki | A |

Wspólne reguły: type hints, brak NaN w zwracanych cechach, wyjątki zamiast cichych błędów.

## 7. Własność plików i git

- Każdy plik ma **jednego właściciela** (tabela w §6 i niżej). Cudzych plików nie edytujecie – prosicie właściciela albo robicie PR.
- Pozostałe pliki: A: `requirements.txt`, `.gitignore`, `README.md`, `src/__init__.py`, `data/fake/`, `0_download_earth.py`, `1_build_index.py` (Ziemia), `3_plot_match.py`, `outputs/analog_comparison.png`, `tests/test_contract.py`, `tests/test_raster_io.py`, `tests/test_pipeline.py`. B: `0_download_moon.py`, `1b_build_moon_index.py`, `2_find_analogs.py`, `app.py`, `tests/test_morphometry.py`, `tests/test_scoring.py`. Pitch/prezentacja: wspólnie (A prowadzi szkic, B dodaje demo).
- Odstępstwo od README: skrypt pobierania i budowy indeksu są rozdzielone na Ziemię i Księżyc, żeby nie było konfliktów w jednym pliku.
- Branche: `earth` (A), `moon` (B). Na `main` łączycie często (co kilka godzin, najpóźniej na każdym checkpoincie); przed merge `git pull --rebase`, `pytest` ma przechodzić.
- Indeksy CSV są plikami własnymi (A → `earth_index.csv`, B → `moon_index.csv`), więc nie powinny się kolidować.

## 8. Checkpointy integracji

| ID | Kiedy | Co | Kto |
|---|---|---|---|
| **C0** | T+1h | na `main`: `config.py`, `src/contracts.py`, `requirements.txt`, `.gitignore`, sztuczne CSV (`data/fake/earth_index_fake.csv` ≥100 wierszy, `data/fake/moon_index_fake.csv` 3 wiersze, dane losowe zgodne ze schematem) | A |
| **C1** | T+2h | na `main`: `morphometry.py` + testy syntetyczne (płaszczyzna, sinusoida, płaska) | B |
| **C2** | T+4h | na `main`: `raster_io.extract_patch` + test; B potrafi wyciąć łatkę z LOLA | A |
| **C3** | T+8h | pierwszy end-to-end: `earth_index.csv` ≥50 wierszy, `moon_index.csv` z Marius Hills; B uruchamia `find_analogs` na prawdziwych danych | A + B |
| **C4** | T+14h | `earth_index.csv` ≥1000 wierszy (minimum awaryjne 300) z regionami COPDEM (Islandia, Devon Island) i regionami walidacyjnymi, `earth_patches.npz`, **`plotting.py` gotowy** (A), `moon_index.csv` ≥10 miejsc (w tym Apollo 12/14/16 i ≥3 miejsca polarne) i scoring gotowy (B) | A + B |
| **C5** | T+18h | Streamlit działa na prawdziwych danych z wykresem | A + B |
| **C6** | T+20h | **feature freeze**; do T+24h: README z ograniczeniami, test na czystym klonie, demo, bufor | oboje |

Jeśli któryś checkpoint się opóźnia o >1h, **od razu** piszecie do drugiej osoby i tniecie zakres (patrz „Plan awaryjny” w dokumentach A i B).

## 9. Poza zakresem MVP

Temperatura, oświetlenie, geologia, Mars, pas 75–80° szerokości księżycowej (bez produktu pokrywającego), globalne przeszukiwanie Ziemi, ocena przydatności lądowiska.

**Usprawnienia po MVP (nie robimy w 24 h):**
- dopasowanie efektywnej rozdzielczości Księżyca i Ziemi: dodatkowe wygładzanie Ziemi albo scalony DEM 59 m LOLA+Kaguya (±60°),
- regiony „kontrolne” niepodobne do Księżyca i bardziej reprezentatywna próba Ziemi,
- **narzędzie walidacyjne na znanych analogach** (pierwsza rzecz po MVP): dla par „miejsce na Księżycu ↔ znany analog na Ziemi” (np. tereny treningowe Apollo, testy sprzętu) sprawdza, na którym miejscu w rankingu ląduje znany analog. Metryki: percentyl rangi analogu, hit@5/hit@10, odwrotność rangi, baseline losowy i kontrole negatywne. Dane: `data/validation/known_analogs.csv` (`moon_site, earth_region, source, confidence, note`, cytowanie obowiązkowe). **Uwaga metodologiczna:** miejsca treningowe wybierano ze względu na geologię i logistykę, nie podobieństwo topografii w skali 10 km, więc chybienie nie jest dowodem błędu. Wynik opisujemy jako test spójności, nie dokładność. **Wymóg na MVP:** regiony i miejsca z tego zbioru muszą być już w indeksach (patrz lista w PERSON_A / PERSON_B).

## 10. Decyzje podjęte domyślnie (do zatwierdzenia przez zespół)

Te punkty to **moje propozycje**, nie ustalenia zespołu. Zmieńcie je teraz, jeśli się nie zgadzacie:

1. Układ docelowy aeqd na łatkę + `Resampling.average` (zamiast np. UTM + bilinear).
2. Nachylenie metodą Horna, 83×83 pikseli wewnętrznych.
3. `rms_height` po odjęciu płaszczyzny; `tri_mean` wg Rileya; `relief_range` jako max − min (bez wersji odpornej na outliery).
4. Odrzucanie (nie wypełnianie) łatek z nodata/NaN; reguły wody dla Ziemi (§2 pkt 7: >5% pikseli źródłowych = 0 m, >20% pikseli o nachyleniu dokładnie 0°).
5. Skaler z-score na indeksie Ziemi, `log1p` dla `rms_height`, `tri_mean`, `relief_range`.
6. `max_per_region = 1` domyślnie.
7. CSV zamiast Parquet (zgodnie z README); łatki Ziemi jako jeden skompresowany `earth_patches.npz` w gicie po C4 (zamiast zipa przez dysk współdzielony).
8. Streamlit obsługuje niestandardowe lat/lon na Księżycu przez odczyt LOLA z dysku. **Ustalone przez zespół:** demo jest uruchamiane z komputera zespołu z dostępem do internetu, więc raster LOLA jest lokalnie, a `/vsicurl/` jest zapasowym źródłem.
9. **Ustalone przez zespół:** w danych od początku są też Islandia i Devon Island (Copernicus DEM GLO-30, `source=COPDEM`), bieguny Księżyca (produkt polarny LOLA) oraz miejsca potrzebne do późniejszej walidacji na znanych analogach. Priorytet przy opóźnieniach (co tniemy jako pierwsze): 1) polarny LOLA, 2) COPDEM, 3) dodatkowe regiony walidacyjne. Rdzeń (NASADEM + LOLA globalny) nie może na tym ucierpieć.
13. Ponieważ część Ziemi pochodzi z innego DEM-u, A robi **kontrolę zgodności DEM-ów**: dla 1–2 regionów pokrytych obu produktami (np. Meteor Crater, Hawaje) liczy cechy z NASADEM i z COPDEM i zapisuje różnice (`slope_p50`, `rms_height`, `tri_mean`). Jeśli różnice są duże, wynik trafia do ograniczeń w README (regiony COPDEM nie są wtedy w pełni porównywalne).
10. `hypsometric_integral` płaskiej łatki = 0.5 (nie 0.0).
11. **Ustalone przez zespół:** różnica efektywnej rozdzielczości Księżyc/Ziemia jest w MVP tylko udokumentowana jako ograniczenie. Dodatkowe wygładzanie Ziemi i DEM 59 m LOLA+Kaguya to usprawnienia po MVP (§9).
12. `plotting.py` i `3_plot_match.py` robi A (gotowe na C4), żeby nie blokować B przy Streamlicie.

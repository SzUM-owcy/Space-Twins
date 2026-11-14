# OSOBA B – Księżyc (LOLA) + cechy + scoring + Streamlit

Przeczytaj najpierw [CONTRACT.md](CONTRACT.md). Tam jest definicja wszystkiego, co musi się zgadzać z częścią A.
**T+0 = start hackathonu.** Całość trwa ok. 24 h.

## Twoja odpowiedzialność

1. `src/morphometry.py::extract_patch_features` – **12 cech**, z której korzysta też A dla Ziemi.
2. Pobranie LOLA, wycięcie łatek Księżyca, `data/moon_index.csv`.
3. `src/scoring.py`, `src/query.py` – ranking analogów.
4. `app.py` – Streamlit, oraz skrypt `2_find_analogs.py`. (Wykres `plot_comparison` i `3_plot_match.py` robi A.)

Twoje pliki: `src/morphometry.py`, `src/scoring.py`, `src/query.py`, `0_download_moon.py`, `1b_build_moon_index.py`, `2_find_analogs.py`, `app.py`, `tests/test_morphometry.py`, `tests/test_scoring.py`, `data/moon_index.csv`, `data/patches/moon/`.

---

## Faza 0 (T+0 … T+1h): start pobierania – **zrób to w pierwszej kolejności**

- [ ] Wspólnie z A przeczytajcie `CONTRACT.md`, zatwierdźcie lub zmieńcie §10.
- [ ] **Natychmiast uruchom pobieranie LOLA w tle** (może trwać długo): strona produktu <https://astrogeology.usgs.gov/search/map/moon_lro_lola_dem_118m> (przekierowuje na S3; plik `Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif`, ok. **8,5 GB**). Zapisz do `data/lola/`. Jeśli pobieranie się wlecze, możesz pracować na zdalnym pliku przez GDAL `/vsicurl/<url>` (serwer S3 obsługuje range requests) i dociągnąć całość w tle.
- [ ] Gdy plik się pobiera, sprawdź w metadanych (`gdalinfo`). Recenzent odczytał nagłówek i podał, czego się spodziewać – **zweryfikuj**:
  - **projekcja**: equirectangular **w metrach** (nie w stopniach!), kula R = 1737400 m, więc **nie nadpisuj CRS na `longlat`**. Użyj CRS z pliku; jeśli PROJ go nie zna, `LOLA_CRS_FALLBACK` z CONTRACT §2,
  - **długości**: −180…180 (wschodnia dodatnia) – bez konwersji 0…360,
  - **typ**: `int16`, `SCALE=0.5`, `OFFSET=0`, nodata `-32768` (czyli `LOLA_SCALE = 0.5` w `config.py`; wartości bez skali są dwa razy większe: zobaczysz zakres ok. −18 300…+21 600 zamiast −9 150…+10 800 m),
  - **układ danych**: nieskompresowany BigTIFF z paskami po 1 wierszu (nie kafelki) – odczyt okna jest tani, **nie trzeba** konwertować do COG. Rozmiar ok. 92160 × 46080 px, piksel ok. 118,45 m.
  Wartości z tej listy, które się nie zgadzają, wpisz do `config.py` (właściciel: A) i napisz do A.

## Faza 1 (T+1h … T+2h): `morphometry.py` – checkpoint C1

Zaimplementuj `extract_patch_features` **dokładnie** wg CONTRACT §3 (Horn 83×83, TRI Rileya, płaszczyzna najlepszego dopasowania, itd.).

Testy `tests/test_morphometry.py` na danych syntetycznych:

| Test | Oczekiwanie |
|---|---|
| płaszczyzna o znanym nachyleniu θ (np. 10°) | `slope_p05 ≈ slope_p50 ≈ slope_p95 ≈ θ`, `rms_height ≈ 0`, `tri_mean = √6 · Δ · tan θ` (Δ = `pixel_size_m`, niezależnie od kierunku spadku) |
| płaszczyzna płaska | wszystkie nachylenia 0, `relief_range = 0`, `hypsometric_integral = 0.5`, `elev_skew = 0.0`, brak NaN |
| fala `z = A·cos(2πx/λ)`, λ ≥ 10·Δ (Horn to różnica centralna, więc zaniża nachylenie, a dopasowanie płaszczyzny usuwa część wariancji) | porównuj ze wzorem **dyskretnym**: maks. `dz/dx = A·sin(2πΔ/λ)/Δ` (p95 z tolerancją), `rms_height` ≤ `A/√2` i bliskie, gdy liczba okresów jest całkowita |
| kształt wejścia `(84, 85)` lub NaN | `ValueError` |
| zestaw kluczy | `set(result) == set(FEATURE_NAMES)` i dokładnie 12 kluczy |

**Push na `main` = C1 (T+2h)**, napisz do A. Po C0 dostępny jest `config.py` (jeśli go jeszcze nie ma, poczekaj kilka minut albo tymczasowo zdefiniuj `FEATURE_NAMES` lokalnie).

## Faza 2 (T+2h … T+8h): pierwsza łatka Księżyca i scoring – checkpoint C3

1. Gdy A wypchnie `raster_io.extract_patch` (C2, T+4h), użyj go: `extract_patch(src, 14.0, -56.0, body="moon", nodata=LOLA_NODATA, scale=LOLA_SCALE)` (stałe z `config.py`; `src_crs=None` → CRS z pliku). Funkcja **nie czyta `src.scales`** – skalę 0.5 podajesz sam, **raz**.
   - Do T+4h możesz przygotować resztę (otwieranie rastra, sanity checks) albo zbudować `scoring.py` na sztucznych CSV z `data/fake/` (od C0).
   - Jeśli C2 się spóźnia o >1h, napisz własną tymczasową wersję zgodną z CONTRACT §2.
2. **Sanity checks wartości LOLA** (zanim cokolwiek policzysz): po zastosowaniu skali globalne minimum ok. −9150 m (basen Biegun Południowy–Aitken), maksimum ok. +10800 m. Łatki w (0, 0) i (14, −56) muszą dawać wysokości w tym zakresie (test w CONTRACT §2 pkt 8). Marius Hills powinien leżeć rzędu kilku km poniżej sfery referencyjnej – to wartość orientacyjna, nie test.
3. Marius Hills (14.0, −56.0): wytnij łatkę, **obejrzyj** (`imshow`), policz cechy, zapisz wiersz do `moon_index.csv` i `data/patches/moon/moon_marius_hills.npy`.
4. **`scoring.py`** (CONTRACT §5): `fit_scaler(earth_df)`, `distances(...)`. Testy w `tests/test_scoring.py`:
   - odległość łatki od samej siebie = 0,
   - `w_slope=1` ignoruje cechy kształtu, `w_slope=0` ignoruje cechy nachylenia,
   - skaler używa statystyk Ziemi (przeskaluj Ziemię, wynik musi się zmienić, przeskaluj Księżyc, skaler nie).
5. **`query.py::find_analogs`** wg CONTRACT §5 (w tym `max_per_region`, `attrs["out_of_range"]`). Na początku pracuj na `data/fake/earth_index_fake.csv`.
6. **C3 (T+8h)**: uruchom `find_analogs` na prawdziwym (małym) `earth_index.csv` od A. Zgłoś wszystko, co wygląda dziwnie (np. wszystkie dopasowania z jednego regionu, rozkłady poza zakresem).

## Faza 3 (T+8h … T+14h): indeks Księżyca i `query.py` – checkpoint C4

1. `1b_build_moon_index.py`: **10–20 miejsc** (slug → lat/lon), propozycje z orientacyjnymi współrzędnymi do sprawdzenia:

   | Slug | Miejsce | lat | lon |
   |---|---|---|---|
   | `marius_hills` | Marius Hills (benchmark README) | 14.0 | −56.0 |
   | `apollo_11` | Morze Spokoju (Apollo 11) | 0.67 | 23.47 |
   | `apollo_17` | Taurus-Littrow (Apollo 17) | 20.19 | 30.77 |
   | `apollo_15` | Hadley Rille (Apollo 15) | 26.13 | 3.63 |
   | `tycho` | Tycho (centralny szczyt) | −43.3 | −11.4 |
   | `copernicus` | Copernicus (centralne szczyty) | 9.6 | −20.1 |
   | `aristarchus_crater` | krater Aristarchus (sam krater; płaskowyż leży ok. 25–27°N, 49–52°W) | 23.7 | −47.4 |
   | `mare_serenitatis` | Morze Pogody | 28.0 | 17.5 |
   | `mare_imbrium` | Morze Deszczów (maria, gładko) | 32.8 | −15.6 |
   | `highlands_maurolycus` | wyżyny przy kraterze Maurolycus (szorstko) | −42.0 | 14.0 |
   | `highlands_hipparchus` | wyżyny przy kraterze Hipparchus | −5.5 | 4.8 |
   | `apollo_12` | Ocean Burz (Apollo 12) | −3.01 | −23.42 |
   | `apollo_14` | Fra Mauro (Apollo 14) | −3.65 | −17.47 |
   | `apollo_16` | wyżyny Descartes (Apollo 16) | −8.97 | 15.50 |

   **Miejsca polarne (produkt polarny, patrz niżej)** – współrzędne orientacyjne, zweryfikuj: `shackleton` (ok. −89.9, 0.0), `haworth` (ok. −87.5, −5.0), `de_gerlache` (ok. −88.5, −87.1), `malapert` (ok. −85.9, 0.0). To kandydaci na bazy (Artemis), więc są sercem tematu wyzwania.

   Współrzędne są **orientacyjne** – sprawdź w LROC QuickMap lub na własnej łatce (hillshade), czy punkt trafia w zamierzony typ terenu.
   Zakres szerokości: **|lat| ≤ 75°** z produktu globalnego 118 m, **lat ≤ −80°** z produktu polarnego (CONTRACT §2, np. `LDEM_80S_20M`: nazwę, CRS i skalę **zweryfikuj w `gdalinfo`**, to nie jest sprawdzone). Pas 75–80° pomijamy. Mieszanka maria (gładkie) i wyżyn (szorstkie) jest ważna, żeby demo pokazało różne wyniki.
   Produkt polarny ma 20 m/px, więc uśrednianie do 117,6 m jest tu ok. 6×6 – lepiej niż 1:1 przy globalnym – i nie ma problemu zbieżności południków. Pobierz go dopiero po rdzeniu (global) – kolejność tnięcia: CONTRACT §10 pkt 9.
   Każde miejsce: `extract_patch` → cechy → wiersz `moon_index.csv` + `data/patches/moon/{patch_id}.npy` (**to idzie do gita**, bo małe). `patch_id = f"moon_{slug}"`, `source = "LOLA"`.
2. `query.py::moon_features_for(lat, lon, lola_path)` – żywa ekstrakcja z rastra na dysku (dla niestandardowych współrzędnych w UI). Wybiera produkt wg szerokości (|lat| ≤ 75° globalny, lat ≤ −80° polarny; ścieżkę do polarnego dodaj jako parametr z `config.py`), zwraca słownik cech lub rzuca `ValueError` dla pasa 75–80° / łatki odrzuconej.
3. `2_find_analogs.py`: CLI `--site marius_hills --top-k 5 --w-slope 0.5` → drukuje tabelę i zapisuje `outputs/latest_query.json` wg CONTRACT §5.
4. Wykres: `plotting.plot_comparison` i `3_plot_match.py` robi A (gotowe na C4). Do tego czasu używaj własnego `imshow`.
5. **C4 (T+14h)**: scoring gotowy, `moon_index.csv` ≥10 miejsc.

## Faza 4 (T+14h … T+20h): Streamlit – checkpoint C5

`app.py` – zakres zgodny z README, milestone 5:

- [ ] wybór miejsca z `moon_index.csv` (selectbox),
- [ ] **własne lat/lon**: `st.number_input` ×2 → `moon_features_for` (wymaga rastra LOLA w `data/lola/` na maszynie demonstracyjnej; jeśli go nie ma, ukryj tę opcję z komunikatem),
- [ ] `top_k` (slider 1–10), suwak `w_slope` (0–1),
- [ ] przycisk „Znajdź analogi” → tabela rankingowa (rank, region, lat/lon, trzy odległości),
- [ ] wykres porównawczy Księżyc | wybrany analog (`plot_comparison` od A; łatki Ziemi z `data/patches/earth_patches.npz`),
- [ ] komponenty podobieństwa (slope/shape/total) dla wybranego analogu **oraz tabela surowych wartości 12 cech** Księżyc vs analog,
- [ ] **sekcja „Ograniczenia”** (CONTRACT §1 „Znane ograniczenie”, §5 „Interpretacja” i „Dodatkowe ograniczenia”): to podobieństwo cech wynikających z wysokości, nie przydatność lądowiska, bezpieczeństwo ani równoważność geologiczna; ostrzeżenie `out_of_range`, jeśli niepuste,
- [ ] cache: `@st.cache_data` dla wczytywania indeksów, `@st.cache_resource` dla skalera.

Uruchamianie: `streamlit run app.py`. **Aplikacja musi działać na samych CSV w gicie** (bez rastrów) dla opcji z listy miejsc.

## Faza 5 (T+20h … T+24h)

- [ ] **Feature freeze o T+20h** – tylko poprawki błędów.
- [ ] Test na czystym klonie razem z A.
- [ ] Nagranie demo (na wypadek awarii na żywo): wybór miejsca → ranking → wykres → ograniczenia.

## Plan awaryjny (tnij zakres w tej kolejności)

1. Pobieranie LOLA za wolne → czytaj zdalnie przez `/vsicurl/` (S3 obsługuje range requests), całość dociągaj w tle. Mniejsza rozdzielczość (LDEM_64 ≈ 474 m/px) to ostateczność: 10 km to tylko ~21 px, a upsampling do 85×85 daje schodki i fałszywe nachylenia (`Resampling.average` działa tam jak nearest; trzeba by bilinear/cubic), co łamie kontrakt – wtedy napisz do A i uzgodnijcie zmianę oraz notkę w README.
2. `moon_features_for` (własne lat/lon) za trudne → zostaw tylko wybór z listy miejsc.
3. Za mało czasu na 10–20 miejsc → minimum 5 (Marius Hills, Apollo 11, Tycho, Copernicus, jedno z wyżyn).
4. Streamlit za wolny → `2_find_analogs.py` + wykres PNG w `outputs/` jako demo.
5. Polarny LOLA za trudny lub za duży → tniesz go **jako pierwszy** (CONTRACT §10 pkt 9), rdzeń i Apollo zostają. Napisz do A, żeby README opisało brak biegunów.

## Definicja „gotowe”

`moon_index.csv` ≥10 miejsc (min. 5), `find_analogs` zwraca ranking na prawdziwym `earth_index.csv`, `pytest` przechodzi, `streamlit run app.py` działa na świeżym klonie z samymi CSV.

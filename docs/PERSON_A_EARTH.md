# OSOBA A – Ziemia (NASADEM) + wspólna infrastruktura

Przeczytaj najpierw [CONTRACT.md](CONTRACT.md). Tam jest definicja wszystkiego, co musi się zgadzać z częścią B.
**T+0 = start hackathonu.** Całość trwa ok. 24 h.

## Twoja odpowiedzialność

1. Wspólna baza: `config.py`, `src/contracts.py`, `requirements.txt`, `.gitignore`, sztuczne CSV.
2. `src/raster_io.py::extract_patch` – **wspólna** funkcja wycinania łatki, której używa też B dla Księżyca.
3. Pobranie NASADEM, przetworzenie wielu łatek, `data/earth_index.csv`.
4. `src/plotting.py` – wykres porównawczy.
5. Pod koniec: README (ograniczenia), testy integracyjne, pomoc w demo.

Twoje pliki: `config.py`, `requirements.txt`, `.gitignore`, `README.md`, `src/__init__.py`, `src/contracts.py`, `src/raster_io.py`, `src/plotting.py`, `0_download_earth.py`, `1_build_index.py`, `3_plot_match.py`, `tests/test_contract.py`, `tests/test_raster_io.py`, `tests/test_pipeline.py`, `data/fake/`, `data/earth_index.csv`, `data/patches/earth_patches.npz`.

---

## Faza 0 (T+0 … T+1h): baza wspólna – **to blokuje B, rób to pierwsze**

- [ ] Wspólnie z B przeczytajcie `CONTRACT.md`, zatwierdźcie lub zmieńcie sekcję §10.
- [ ] Załóż **darmowe konto NASA Earthdata** (plan awaryjny dla pobierania, patrz niżej).
- [ ] `requirements.txt`: `numpy`, `scipy`, `pandas`, `rasterio`, `pyproj`, `pystac-client`, `planetary-computer`, `matplotlib`, `streamlit`, `pytest`. Python 3.11+, najlepiej wirtualne środowisko. Na Windows `pip install rasterio` zwykle działa z gotowych wheeli; jeśli nie, użyj conda-forge.
- [ ] `.gitignore`: `data/nasadem/`, `data/lola/`, `data/patches/earth/`, `outputs/`, `__pycache__/`, `.venv/`.
- [ ] `config.py` ze stałymi z CONTRACT §6 (`FEATURE_NAMES` w kolejności z §4).
- [ ] `src/contracts.py::validate_records` + `tests/test_contract.py`.
- [ ] Sztuczne CSV w `data/fake/` (`earth_index_fake.csv` ≥100 wierszy, 15 różnych `region`; `moon_index_fake.csv` 3 wiersze), losowe wartości o realistycznych zakresach (nachylenia 0–40°, `rms_height` 1–500 m). Muszą przejść `validate_records`.
- [ ] **Push na `main` = checkpoint C0 (T+1h).** Napisz do B.

## Faza 1 (T+1h … T+4h): jedna łatka i `extract_patch` – checkpoint C2

1. **Jeden kafelek NASADEM** z Planetary Computer (wymaga tylko internetu, bez konta):
   ```python
   import planetary_computer, pystac_client
   catalog = pystac_client.Client.open(
       "https://planetarycomputer.microsoft.com/api/stac/v1",
       modifier=planetary_computer.sign_inplace,
   )
   items = catalog.search(collections=["nasadem"], bbox=[-111.1, 35.0, -111.0, 35.1]).item_collection()
   href = items[0].assets["elevation"].href   # COG 1°×1° (3601×3601 int16, ~26 MB nieskompresowane)
   ```
   Nazwy kolekcji (`nasadem`) i klucza zasobu (`elevation`) sprawdził recenzent i są poprawne; zasięg to ok. −56…+61° szerokości.
   **Pobierz COG-i lokalnie do `data/nasadem/`** (np. `urllib`/`requests` po podpisanym URL-u) i dopiero z dysku buduj mozaikę – podpisane URL-e SAS wygasają, a czytanie łatka po łatce przez sieć jest wolne i kruche.
   Plan awaryjny, jeśli PC nie działa lub jest wolne: Earthdata Search → `NASADEM_HGT` → kafelki ręcznie albo przez `earthaccess`/`curl` z kontem Earthdata.
2. **Sprawdź empirycznie na jednym kafelku przybrzeżnym**: jakiego nodata używa NASADEM w COG z PC (spodziewane −32768) i jak zapisany jest ocean (0 czy nodata). Wynik wpisz do `config.py` (`NASADEM_NODATA`) i do CONTRACT §2 pkt 7.
3. **`extract_patch`** zgodnie z CONTRACT §2 i §6 (czytasz okno źródła do tablicy, nodata → NaN, `scale/offset`, odrzucenie przy nodata w oknie, dopiero potem `reproject` z jawnymi `src_transform`/`src_crs`). Szkic:
   ```python
   from rasterio.warp import reproject, Resampling
   from rasterio.transform import from_bounds
   dst = np.full((85, 85), np.nan, dtype=np.float64)
   reproject(source=window_array, src_transform=window_transform, src_crs=src_crs,
             destination=dst,
             dst_transform=from_bounds(-5000, -5000, 5000, 5000, 85, 85), dst_crs=aeqd_crs,
             src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.average)
   ```
   Uwagi:
   - **Funkcja nie czyta `src.scales`** – skalę podaje wywołujący (CONTRACT §6). B użyje jej dla LOLA z `scale=0.5`; udokumentuj to w docstringu.
   - Dla dużego pliku LOLA odczyt okna jest tani (paski jednowierszowe, bez kompresji), więc nie ma potrzeby konwersji do COG.
4. **Testy `tests/test_raster_io.py`** na syntetycznym GeoTIFF zapisanym w `tmp_path` (np. płaszczyzna o znanym nachyleniu): kształt 85×85, brak NaN, `None` przy dziurze nodata (także częściowej, na skraju okna), poprawność nachylenia po wycięciu, oraz **test round-trip z CONTRACT §2 pkt 8** (środek łatki → (0,0) w aeqd, dla Ziemi i Księżyca; dla Księżyca z syntetycznym rastrem w equirectangular w metrach).
5. Pierwsza łatka Ziemi (np. okolice Meteor Crater w Arizonie ok. 35.03, −111.02): wytnij, policz cechy funkcją od B (po C1), obejrzyj `matplotlib.imshow` i hillshade. **Sprawdź na oko**, czy kierunek (północ u góry) i skala są sensowne i czy krater jest widoczny.
6. **Push `extract_patch` na `main` = checkpoint C2 (T+4h).** Napisz do B.

## Faza 2 (T+4h … T+8h): regiony i pierwszy mały indeks – checkpoint C3

**Ważne: NASADEM pokrywa tylko ok. 60°N – 56°S.** Islandia, Devon Island, Alaska północna, Antarktyda i Svalbard są poza zasięgiem. Dla regionów >60°N używamy **Copernicus DEM GLO-30** (`source=COPDEM`): kolekcja `cop-dem-glo-30` w Planetary Computer ma zasięg globalny (sprawdzone w katalogu STAC). Klucz zasobu (prawdopodobnie `data`) **zweryfikuj** po pierwszym `search`. Algorytm `extract_patch` jest ten sam (CONTRACT §2), zmieniają się tylko pliki, `nodata` i `source`. `0_download_earth.py` i `1_build_index.py` przyjmują `--dem nasadem|copdem`.

Zdefiniuj w `1_build_index.py` listę regionów (slug + bbox 1° × 1°). Cel: **ok. 30 regionów** o zróżnicowanym terenie, żeby indeks pokrywał zarówno bardzo płasko, jak i stromo (księżycowe maria są gładkie, wyżyny szorstkie). Propozycje do wyboru (współrzędne środkowe sprawdź sam):

| Typ terenu | Regiony |
|---|---|
| płaskie | Salar de Uyuni (Boliwia), Black Rock Desert (Nevada), Bonneville Salt Flats (Utah) |
| wulkaniczne / lawa | Hawaje – Mauna Loa, Craters of the Moon (Idaho), Pinacate (Meksyk), Lanzarote, Teide (Teneryfa), Etna, Piton de la Fournaise (Reunion), Paricutín |
| kratery | Meteor Crater (Arizona), Aorounga (Czad) |
| pustynne / wydmy | Erg Chebbi (Maroko), Namib, Lut (Iran), Wadi Rum, Gran Desierto de Altar |
| górskie / strome | Alpy, Tibesti (Czad), Atacama – przedgórze Andów, Kamczatka (Klyuchevskoy ~56°N), Tien Shan |
| plateau / baseny | Colorado Plateau, Nevada Basin and Range, Patagonia (płaskowyż bazaltowy), Dolina Śmierci |

**Regiony wysokich szerokości (COPDEM, `source=COPDEM`)** – w danych od początku:

| Region | Orientacyjne współrzędne | Uwagi |
|---|---|---|
| Askja / Dyngjufjöll (Islandia) | ok. 65.0°N, −16.8° | blisko lodowca Vatnajökull, wybierz bbox poza lodem |
| Krafla / Myvatn (Islandia) | ok. 65.7°N, −16.8° | pola lawy, szczeliny |
| Holuhraun (Islandia) | ok. 64.85°N, −16.8° | świeże pole lawy |
| Hekla (Islandia) | ok. 64.0°N, −19.7° | wulkan |
| Haughton (Devon Island, Kanada) | ok. 75.4°N, −89.7° | krater uderzeniowy, analog Marsa/Księżyca (Haughton-Mars Project) |

**Regiony walidacyjne (znane analogi księżycowe, do zweryfikowania w literaturze, współrzędne orientacyjne):** Cinder Lake koło Flagstaff (ok. 35.4°N, −111.5° – to także punkt z przykładu w README), Meteor Crater (już na liście), Rio Grande Gorge (Nowy Meksyk, ok. 36.3°N, −105.7°), Ries (Niemcy, ok. 48.9°N, 10.5°E – `NASADEM`), Craters of the Moon (już na liście), Pinacate (już na liście), Mauna Kea (Hawaje, obok Mauna Loa – osobny region bez nakładania). Zapisz w `config.py`/w pliku regionów, które regiony należą do tego zbioru (flaga `validation=True`), żeby walidacja po MVP je znalazła.

Reguły: każdy region ma **unikalny slug** (kategoria to tylko etykieta pomocnicza, nie osobny region – np. Pinacate raz). **Bboxy regionów nie mogą się nakładać** (dodaj w `1_build_index.py` asercję), inaczej te same łatki trafią pod dwa regiony i `max_per_region` przestanie działać. Rozważ 1–2 regiony „kontrolne” bardzo niepodobne do Księżyca (np. Alpy), żeby indeks nie był samymi księżycopodobnymi terenami.

- Pobierz lokalnie wszystkie kafelki 1°×1° przecinające bbox regionu + margines **0.2°** (na 56°N 0.1° długości to tylko ok. 6 km, za mało przy łatce 10 km), połącz w mozaikę (`rasterio.merge` albo GDAL VRT) – łatki przy krawędzi kafelka nie mogą być obcinane.
- Podział na łatki: **siatka bez nakładania, krok 10 km** wzdłuż osi metrycznych w obrębie bbox. Środki łatek w lat/lon przelicz z metrów (aeqd wokół środka regionu albo prosty przelicznik z cos(lat) – niedokładność kilkuset metrów jest dopuszczalna, bo `extract_patch` i tak liczy własny układ wokół środka łatki).
- Dla każdej łatki: `extract_patch(..., body="earth")` → jeśli `None`, pomiń i zapisz do logu powód → `extract_patch_features` → rekord. `patch_id = f"earth_{region}_{i:04d}"`.
- Zapisuj `data/patches/earth/{patch_id}.npy` (`float32`).
- Wynik: `data/earth_index.csv`, kolumny z CONTRACT §4, po przejściu `validate_records`.
- **Dla C3 (T+8h) wystarczy ≥50 łatek z ~5 regionów**, żeby B mógł przetestować scoring na prawdziwych danych. Push `earth_index.csv` na `main`, napisz do B. (Łatki `.npy` nie są potrzebne do scoringu; `earth_patches.npz` idzie do gita dopiero po C4.)

## Faza 3 (T+8h … T+14h): pełny indeks – checkpoint C4

- [ ] Dodaj pozostałe regiony, uruchom batch równolegle: `concurrent.futures.ProcessPoolExecutor`, **każdy proces sam otwiera plik** (obiekty `rasterio` nie są przekazywalne między procesami). 64 GB RAM wystarcza na kilka procesów jednocześnie.
- [ ] Cel: **≥1000 wierszy** (minimum awaryjne 300), w tym regiony COPDEM i regiony walidacyjne.
- [ ] **Kontrola zgodności DEM-ów (CONTRACT §10 pkt 13):** dla Meteor Crater i jednego regionu na Hawajach policz cechy z NASADEM **i** z COPDEM, zapisz różnice `slope_p50`, `rms_height`, `tri_mean` (np. `docs/dem_crosscheck.md`). Jeśli różnice są duże (rzędu kilkudziesięciu procent), dopisz to do README jako ograniczenie dla regionów COPDEM.
- [ ] Pamiętaj o lodowcach (Islandia, Devon Island): powierzchnia lodu jest gładka i zafałszuje podobieństwo. Wybieraj bboxy poza lodowcami i obejrzyj hillshade kilku łatek.
- [ ] **Kolejność przy braku czasu:** najpierw rdzeń (NASADEM), potem COPDEM, potem dodatkowe regiony walidacyjne (CONTRACT §10 pkt 9).
- [ ] **Walidacja** (to ważne, żeby nie pokazać na demo bzdur):
  - Rozkłady cech: histogramy, brak NaN, brak zerowej wariancji w kolumnach.
  - Sanity checks: region „płaski” (Uyuni) ma niskie `slope_p50` (< 1°), „górski” (Alpy) wysokie (> 15°); Meteor Crater jest **widoczny na hillshade** (nie sprawdzaj liczby – krater ma ok. 1,2 km, czyli ok. 10 pikseli, a łatka obejmuje też regionalny spadek).
  - Łatki przybrzeżne (Lanzarote, Teide, Reunion, Hawaje): obejrzyj kilka, czy klify/morze nie zawyżają nachyleń; w razie potrzeby zaostrz regułę wody (CONTRACT §2 pkt 7).
  - Porównaj 3–4 łatki z mapą (Google Earth) czy wyglądają jak oczekiwano.
- [ ] **`src/plotting.py` gotowy do C4** (blokuje B przy Streamlicie, więc nie odkładaj): `plot_comparison` zgodnie z CONTRACT §6: dwa panele (Księżyc | Ziemia), hillshade (np. `matplotlib.colors.LightSource(azdeg=315, altdeg=45).hillshade(patch, vert_exag=1, dx=PIXEL_SIZE_M, dy=PIXEL_SIZE_M)`) i kolor z wysokości względem minimum łatki, wspólna skala wysokości, podpisy (nazwa, współrzędne). Łatki Ziemi czytaj z `earth_patches.npz` (jeśli brak łatki – komunikat zamiast wyjątku).
- [ ] `3_plot_match.py`: CLI (`--site marius_hills`), korzysta z `find_analogs` (B) i `plot_comparison`, zapisuje `outputs/analog_comparison.png`.
- [ ] Zbuduj `data/patches/earth_patches.npz` (`np.savez_compressed`, klucze = `patch_id`, `float32`) i **raz** zacommituj. Push `earth_index.csv` + `.npz` = **C4 (T+14h)**.

## Faza 4 (T+14h … T+20h): integracja – checkpoint C5

- [ ] Pomóż B z integracją wykresu w Streamlicie (kompatybilność `plot_comparison`, wydajność, wygląd).
- [ ] `tests/test_pipeline.py`: test end-to-end na sztucznych danych (syntetyczny raster → łatka → cechy → find_analogs).
- [ ] Dołóż brakujące regiony/łatki, jeśli walidacja pokazała dziury w pokryciu (np. brak bardzo szorstkich lub bardzo płaskich terenów).
- [ ] Jeśli konieczna poprawka `.npz` po C5, zrób **jedną** (nie commituj go wielokrotnie).

## Faza 5 (T+20h … T+24h)

- [ ] **Feature freeze o T+20h.**
- [ ] README: sekcja „Ograniczenia” (CONTRACT §1 „Znane ograniczenie”, §5 „Interpretacja” i „Dodatkowe ograniczenia” oraz „Scientific Scope” z README), aktualne instrukcje uruchomienia, status.
- [ ] Test na **czystym klonie** (nowy katalog, nowe venv, `pytest`, uruchomienie aplikacji z tylko CSV w gicie).
- [ ] Przygotuj pitch (3 minuty): problem → dane → metoda → wynik → ograniczenia.

## Plan awaryjny (tnij zakres w tej kolejności)

1. PC nie działa → pobieranie ręczne z Earthdata (konto).
2. Za mało czasu na 30 regionów → 15 regionów, ale wybierz je tak, żeby rozstęp płaski–stromy był zachowany.
3. Opóźnienie C2 o >1h → B pisze tymczasową wersję `extract_patch` zgodną z CONTRACT §2 w swoim pliku, a Ty łączysz po fakcie.
4. Brak czasu na walidację → minimum: histogramy i trzy sanity checks powyżej.

## Definicja „gotowe”

`data/earth_index.csv` ≥1000 wierszy (min. 300), `validate_records` przechodzi, `pytest` przechodzi, `plot_comparison` rysuje parę łatek, a README opisuje ograniczenia.

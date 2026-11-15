# Kontrakt API: backend <-> frontend

Backend i frontend są połączone **wyłącznie tym kontraktem**. Reszta (jak liczymy ranking, skąd dane) jest
szczegółem implementacji backendu.

| Co | Gdzie |
|---|---|
| Maszynowy kontrakt (OpenAPI 3) | [`api/openapi.json`](../api/openapi.json) - **commitowany, źródło prawdy dla frontu** |
| Modele (Pydantic) | [`api/schemas.py`](../api/schemas.py) |
| Przykładowe odpowiedzi do mocków | [`api/examples/*.json`](../api/examples) |
| Interaktywna dokumentacja | `http://localhost:8000/docs` po starcie serwera |
| Test pilnujący zgodności | [`tests/test_api.py`](../tests/test_api.py) |

## Uruchomienie

```bash
uv run uvicorn api.main:app --reload --port 8000
```

CORS jest otwarty dla `http://localhost:*` i `http://127.0.0.1:*` (Vite, CRA itd.). Wszystkie ścieżki mają prefiks `/api/v1`.

## Endpointy

| Metoda | Ścieżka | Odpowiedź | Opis |
|---|---|---|---|
| GET | `/health` | `Health` | Status; `custom_coordinates_available` = czy działają własne współrzędne (jest raster LOLA) |
| GET | `/meta` | `Meta` | 12 cech (nazwa, grupa, jednostka, opis), stałe siatki, domyślne `w_slope`/`top_k`, **lista ograniczeń do pokazania w UI** |
| GET | `/moon/sites` | `MoonSite[]` | 18 gotowych miejsc księżycowych (Apollo, Shackleton...) z cechami |
| GET | `/moon/patch?site_id=...` lub `?lat=..&lon=..` | `PatchGrid` | Siatka wysokości 85x85 łatki Księżyca (do 3D) |
| GET | `/earth/regions` | `EarthRegion[]` | Regiony Ziemi (bbox, flaga `validation`, liczba łatek) - do mapy |
| GET | `/earth/patches/{patch_id}` | `PatchGrid` | Siatka wysokości 85x85 łatki Ziemi |
| POST | `/analogs` | `AnalogsResponse` | Ranking analogów na Ziemi dla miejsca na Księżycu |
| POST | `/chat` | strumień SSE | Asystent (Gemini) odpowiadający na pytania o miejsce Księżyca i jego analogi |

### `POST /chat`

```json
{ "moon_site_id": "moon_apollo_15", "selected_twin_id": "earth_rio_grande_gorge_0004",
  "messages": [{ "role": "user", "content": "Which match is best for a field campaign?" }] }
```

- Front wysyła tylko identyfikator miejsca, opcjonalnie `patch_id` otwartego dopasowania (żeby "this one" miało sens) i historię rozmowy (ostatnia wiadomość od `user`, maks. 2000 znaków; backend bierze ostatnie 12). Kontekst (cechy, temperatura, oświetlenie, minerały, practicality, constraints dla 5 dopasowań, stałe wagi 0.6/0.2/0.2) składa backend.
- Odpowiedź `200` to `text/event-stream`: zdarzenia `delta` (`{"text": "..."}`), na końcu `done` albo `error` (`{"message": "..."}`, tekst do pokazania w UI).
- Błędy przed startem strumienia mają standardowy kształt: `404` (nieznane miejsce), `422`, `503` z `CHAT_UNAVAILABLE` (brak `GOOGLE_API_KEY`).
- Konfiguracja w `.env` (poza gitem; wzór w `.env.example`): `GOOGLE_API_KEY` (Google AI Studio), opcjonalnie `GEMINI_MODEL` (domyślnie `gemini-3.1-flash-lite`). Bot odpowiada po angielsku, wyłącznie z danych, i odmawia pytań spoza tematu.

### `POST /analogs`

```json
{ "moon": { "site_id": "moon_apollo_11" }, "top_k": 5, "w_slope": 0.5, "max_per_region": 1 }
```

- `moon`: **albo** `{ "site_id": "..." }`, **albo** `{ "lat": 0.67, "lon": 23.47 }` (nie oba naraz).
- `top_k` 1-50 (domyślnie 5), `w_slope` 0-1 (domyślnie 0.5; waga nachyleń, reszta to kształt), `max_per_region` >= 1 albo `null` (bez limitu; domyślnie 1).
- Odpowiedź: `moon` (cechy surowe + `z_scores`), `out_of_range` (cechy Księżyca z |z| > 3 - **pokaż ostrzeżenie o mniejszej wiarygodności**), `results[]` posortowane rosnąco po `total_distance` (mniejsza = bardziej podobny). Każdy wynik ma `features` i `z_scores` (do wykresu radarowego "dlaczego to dopasowanie"), `lat`/`lon` (do pina na mapie).
- Opcjonalnie `feature_weights`: słownik względnych ważności pojedynczych cech terenu (klucze z `/meta -> features`, wartości >= 0, pominięte = 1, nieznany klucz = 422). Zastępuje podział `w_slope`: odległość terenowa to ważone RMS z-score'ów. Razem z `w_thermal` i `w_illum` daje to wagę każdej cechy porównania.
- Opcjonalnie `w_thermal` i `w_illum` (0-1, domyślnie 0 = tylko teren, suma <= 1): dodają składniki zakresu temperatur i oświetlenia (waga terenu = 1 - w_thermal - w_illum). Wtedy każdy wynik ma `terrain_distance`, `thermal_distance`/`thermal_status`, `illumination_distance`/`illumination_status` (`missing` = składnik pominięty), a `moon` ma `thermal_range_percentile` i `solar_visibility_fraction` (null, gdy brak danych).
- Opcjonalnie `w_composition` (0-1, domyślnie 0; `w_thermal + w_illum + w_composition <= 1`): składnik składu mafic-felsic (percentyl proxy IR względem własnego ciała; to nie jest równość minerałów). Wynik ma wtedy `composition_distance`, `composition_status` (`ok`/`missing`), `composition_quality`, `composition_confidence` (`high`/`medium`/`low`/`low_quartz_confounder`) i `earth_mafic_felsic_percentile`; niezależnie od wag każdy wynik ma też objaśniające `dominant_lithology` (Macrostrat: `mafic`/`felsic`/`anorthosite`/`carbonate`/`evaporite`/`sedimentary`/`unconsolidated`/`unknown`) i `mixed_lithology_flag` (nie wchodzą do wyniku). Porównanie minerałów (diagnostyka, poza wynikiem): `moon.minerals` (udziały plagioklaz/piroksen/oliwin z Diviner, ±70°) oraz na łatce Ziemi `earth_plagioclase_fraction`, `earth_pyroxene_fraction`, `earth_olivine_fraction`, `earth_other_fraction`, `earth_mineral_status` (`estimated`/`no_lithology`) i `mineral_distance` (0 = identyczne, 1 = rozłączne). Gdy brak tabeli ASTER, składnik `w_composition` używa `mineral_distance` jako zapasu (`composition_source = lithology_minerals`, `composition_confidence = low_lithology_estimate`); łatki bez zmapowanej litologii wypadają z tego składnika. Ziemia to szacunek: litologia Macrostrat x typowy skład modalny klasy skały; `moon` ma `mafic_felsic_percentile` i `composition_status` (`outside_diviner_cf_coverage` dla biegunów, poniżej 70°S, gdzie składnik wypada z sumy).
- Do wyświetlania (niezależnie od wag): każdy wynik ma `thermal_range_k` (surowy zakres dobowy temperatury powierzchni, K) i `solar_visibility_fraction` (ułamek dnia, gdy teren nie zasłania Słońca, 0..1), a `moon` ma `thermal_range_k` (tylko miejsca z listy) i `solar_visibility_fraction` (to drugie tylko gdy `w_illum` > 0). Wartości Księżyca i Ziemi nie są bezpośrednio porównywalne - ranking opiera się na percentylach w obrębie każdego ciała.
- Opcjonalnie `include_practicality` (bool, domyślnie false): dołącza do każdego wyniku bloki `practicality` (wyniki 0-100: `access_score`, `buildability_score`, `emergency_support_score`, `infrastructure_score`, `population_score`, osobne `isolation_logistics_penalty` i `population_impact_penalty`, `field_campaign_score`/`facility_score` z klasami kosztu `LOW`/`MEDIUM`/`HIGH`/`VERY HIGH`/`EXCLUDED / MANUAL REVIEW`, `practicality_completeness`/`practicality_confidence`, `pareto_field`/`pareto_facility`) oraz `constraints` (flagi `ok`/`warning`/`manual_review`/`excluded`/`missing`: obszary chronione, dziedzictwo, prawa wspólnot, bioróżnorodność, woda, zagrożenia, bezpieczeństwo, plus `hard_excluded` i `exclusion_reasons`). Nie zmienia rankingu ani odległości naukowych; opis: `docs/practicality.md`.
- Gdy ustawione są `terrain_distance`/`thermal_distance`/`illumination_distance`, wynik ma też `terrain_quality`/`thermal_quality`/`illumination_quality` (`good` < 0.5, `moderate` < 1.0, `poor` dalej; null = brak danych). Opcjonalnie `stability_runs` (0-100, domyślnie 0): liczba przebiegów z szumem na cechach Księżyca; wtedy każdy wynik ma `stability` (ułamek przebiegów, w których jego region zostaje w top-K; null = nie liczone).
- Suwak `w_slope` w UI = ponowne wywołanie tego endpointu (zapytanie jest szybkie, rzędu dziesiątek ms).

### Siatka wysokości (`PatchGrid`)

- `heights_m[row][col]`, `grid_n x grid_n` (85 x 85), metry, zaokrąglone do 0.01 m.
- **row 0 = północ, col 0 = zachód.** Piksel ma `pixel_size_m` (~117.6 m), łatka ma `size_m` = 10 000 m.
- Wysokości są **bezwzględne** (nad poziomem odniesienia LOLA/NASADEM). Do wizualizacji odejmij `min_m`. Skala pionowa Księżyc vs Ziemia powinna być wspólna (jak w `src/plotting.py`).

### Błędy

Każdy błąd ma kształt `{ "code": "...", "message": "...", "details": [...]|null }`:

| HTTP | `code` | Kiedy | Co robi UI |
|---|---|---|---|
| 422 | `INVALID_REQUEST` | zły body/parametry (`details` = lista błędów pól) | błąd formularza |
| 404 | `NOT_FOUND` | nieznany `site_id` / `patch_id` | komunikat |
| 422 | `PATCH_REJECTED` | punkt poza obsługiwanym zakresem (obsługiwane: \|lat\| <= 75° oraz lat <= -80°; pas 75-80° i północ są pomijane), nodata albo poza rastrem | pokaż `message` |
| 503 | `RASTER_UNAVAILABLE` | brak rastra LOLA na tej maszynie | wyłącz własne współrzędne, zostaw `site_id` |
| 500 | `INTERNAL_ERROR` | nieoczekiwany błąd | komunikat ogólny |

`message` bywa po polsku (pochodzi z `src/`) - traktuj jako tekst diagnostyczny, a nie klucz tłumaczenia. Do logiki używaj `code`.

## Zasady współpracy

**Backend (może zmieniać swobodnie):** całe `src/`, `api/service.py`, dane i sposób liczenia, o ile odpowiedzi zgadzają się ze schematami.

**Zmiana kontraktu** (`api/schemas.py` lub ścieżek w `api/main.py`):
1. Zmiany **addytywne** (nowe pole w odpowiedzi, nowy endpoint, nowy opcjonalny parametr) - wolno, front ma ignorować nieznane pola.
2. Zmiany **łamiące** (usunięcie/zmiana typu/nazwy pola, zmiana semantyki) - tylko po uzgodnieniu z osobą od frontu; wtedy też podnosimy `version` w `api/main.py`.
3. Po każdej zmianie: `uv run python -m api.export_openapi` (i ewentualnie `uv run python -m api.export_examples`), commit razem z kodem.
4. Istniejący `tests/test_api.py` pilnuje, że `api/openapi.json` jest aktualny (szybki sprawdzian: `uv run python -m api.export_openapi --check`).

**Hackathon:** nie piszemy nowych testów, żeby oszczędzać czas.

**Frontend:**
- Typy klienta generuj z `api/openapi.json` (np. `npx openapi-typescript api/openapi.json -o src/api/schema.d.ts`).
- Do pracy bez backendu: mock z `api/examples/*.json` albo `npx @stoplight/prism-cli mock api/openapi.json`.
- Backend nie jest potrzebny do pracy nad UI; integracja = zmiana base URL na `http://localhost:8000/api/v1`.

## Planowane (jeszcze nie w kontrakcie)

Po uzgodnieniu dodamy jako zmiany addytywne:
- `GET /validation` - znane pary analogów (Apollo/Cinder Lake, Meteor Crater...) jako dowód działania metody (notatki w `scratch/notes/RESEARCH_ANALOGS.md`, lokalnie, poza gitem; flaga `validation` w `regions.csv`).
- Wskaźnik "similarity" 0-100 (wymaga decyzji, jak mapować odległość).
- Dane dla całego Księżyca (nie tylko 18 miejsc), tekstury/zdjęcia.

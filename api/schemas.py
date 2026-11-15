"""Kontrakt HTTP backend <-> frontend (źródło prawdy: te modele + api/openapi.json).

Zmiana tego pliku = zmiana kontraktu: zregeneruj ``api/openapi.json``
(``uv run python -m api.export_openapi``) i uzgodnij z osobą od frontu (docs/API_CONTRACT.md).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from config import FEATURE_NAMES

FeatureGroup = Literal["slope", "shape"]
Body = Literal["moon", "earth"]
ErrorCode = Literal[
    "INVALID_REQUEST",
    "NOT_FOUND",
    "PATCH_REJECTED",
    "RASTER_UNAVAILABLE",
    "CHAT_UNAVAILABLE",
    "INTERNAL_ERROR",
]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorResponse(Model):
    """Każdy błąd (4xx/5xx) ma ten kształt."""

    code: ErrorCode
    message: str = Field(description="Komunikat czytelny dla człowieka (można pokazać w UI).")
    details: list[dict] | None = Field(default=None, description="Szczegóły walidacji (INVALID_REQUEST).")


class Health(Model):
    status: Literal["ok"]
    custom_coordinates_available: bool = Field(
        description="false, gdy na tej maszynie brak rastra LOLA: POST /analogs z lat/lon zwróci RASTER_UNAVAILABLE."
    )
    moon_sites: int
    earth_patches: int


class FeatureInfo(Model):
    name: str
    group: FeatureGroup
    unit: str = Field(description='Jednostka ("°", "m" albo "" dla cech bezwymiarowych).')
    description: str


class Meta(Model):
    patch_size_m: int
    grid_n: int
    pixel_size_m: float
    default_w_slope: float
    default_top_k: int
    out_of_range_z: float = Field(description="Próg |z|, powyżej którego cecha Księżyca trafia do out_of_range.")
    features: list[FeatureInfo] = Field(description="12 cech w kolejności kontraktu (CONTRACT §3).")
    limitations: list[str] = Field(description="Ograniczenia interpretacji - mają być widoczne w UI.")


class MoonSite(Model):
    site_id: str = Field(description="= patch_id, np. moon_apollo_11.")
    name: str = Field(description="Nazwa do wyświetlenia, np. Apollo 11.")
    lat: float
    lon: float = Field(description="Stopnie, wschód dodatni, -180..180.")
    features: dict[str, float]
    thermal_range_k: float | None = Field(default=None, description="Surowy zakres dobowy temperatury powierzchni [K] (Diviner); null = brak danych.")
    solar_visibility_fraction: float | None = Field(
        default=None, description="Ułamek dnia, gdy teren nie zasłania Słońca (0..1); null = brak danych."
    )
    minerals: dict[str, float] | None = Field(
        default=None, description="Udziały plagioklaz/piroksen/oliwin (Diviner, ±70°); null poza zasięgiem. Mogą wychodzić poza 0..1 - normalizuj w UI."
    )


class EarthRegion(Model):
    region: str
    name: str
    dem: Literal["nasadem", "copdem"]
    validation: bool = Field(description="true = region z udokumentowanym analogiem księżycowym (walidacja).")
    bbox: tuple[float, float, float, float] = Field(description="[west, south, east, north] w stopniach.")
    patches: int = Field(description="Liczba łatek tego regionu w indeksie Ziemi.")


class PatchGrid(Model):
    """Siatka wysokości łatki 10x10 km. ``heights_m[row][col]``; row 0 = północ, col 0 = zachód."""

    patch_id: str | None = Field(description="null dla łatki Księżyca wyciętej z własnych współrzędnych.")
    body: Body
    region: str | None
    lat: float
    lon: float
    size_m: int
    grid_n: int
    pixel_size_m: float
    min_m: float
    max_m: float
    heights_m: list[list[float]] = Field(description="grid_n x grid_n, metry (zaokrąglone do 0.01 m).")


class MoonQuery(Model):
    """Miejsce na Księżycu: ALBO ``site_id`` ALBO para ``lat`` + ``lon``."""

    site_id: str | None = Field(default=None, examples=["moon_apollo_11"])
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _exactly_one(self) -> MoonQuery:
        has_point = self.lat is not None or self.lon is not None
        if self.site_id is not None and has_point:
            raise ValueError("podaj albo site_id, albo lat+lon - nie oba naraz")
        if self.site_id is None and (self.lat is None or self.lon is None):
            raise ValueError("podaj site_id albo obie współrzędne lat i lon")
        return self


class AnalogsRequest(Model):
    moon: MoonQuery
    include_practicality: bool = Field(
        default=False,
        description="Dołącz bloki practicality/constraints do każdego wyniku. Nie zmienia rankingu ani odległości naukowych.",
    )
    top_k: int = Field(default=5, ge=1, le=50)
    w_slope: float = Field(default=0.5, ge=0, le=1, description="Waga nachyleń; (1 - w_slope) = waga kształtu.")
    max_per_region: int | None = Field(
        default=1, ge=1, description="Maks. łatek z jednego regionu w rankingu; null = bez limitu."
    )
    w_thermal: float = Field(
        default=0.0, ge=0, le=1, description="Waga zakresu temperatur (percentyl); 0 = wyłączony (tylko teren)."
    )
    w_illum: float = Field(
        default=0.0, ge=0, le=1, description="Waga oświetlenia (widoczność Słońca); 0 = wyłączone. w_thermal + w_illum <= 1."
    )

    w_composition: float = Field(
        default=0.0, ge=0, le=1,
        description="Waga składu mafic-felsic (proxy IR; percentyl w obrębie ciała); 0 = wyłączony. w_thermal + w_illum + w_composition <= 1.",
    )
    stability_runs: int = Field(
        default=0, ge=0, le=100,
        description="Liczba przebiegów z szumem na cechach Księżyca (0 = wyłączone); wypełnia Analog.stability.",
    )

    feature_weights: dict[str, float] | None = Field(
        default=None,
        description=(
            "Względne ważności 12 cech terenu (klucze = nazwy z /meta -> features, wartości >= 0; pominięte = 1). "
            "Zastępuje podział w_slope. null = domyślny schemat w_slope."
        ),
        examples=[{"slope_p50": 3, "rms_height": 2, "elev_skew": 0}],
    )

    @model_validator(mode="after")
    def _weights_sum(self) -> AnalogsRequest:
        if self.feature_weights is not None:
            unknown = sorted(set(self.feature_weights) - set(FEATURE_NAMES))
            if unknown:
                raise ValueError(f"nieznane cechy w feature_weights: {unknown}")
            vals = list(self.feature_weights.values())
            if any(v < 0 for v in vals) or (len(vals) == len(FEATURE_NAMES) and sum(vals) <= 0):
                raise ValueError("feature_weights: wagi >= 0 i nie wszystkie zerowe")
        if self.w_thermal + self.w_illum + self.w_composition > 1.0:
            raise ValueError("w_thermal + w_illum + w_composition musi być <= 1")
        return self


class MoonSummary(Model):
    site_id: str | None
    name: str
    lat: float
    lon: float
    features: dict[str, float] = Field(description="Surowe wartości 12 cech.")
    z_scores: dict[str, float] = Field(description="Cechy po log1p + z-score względem indeksu Ziemi (CONTRACT §5).")
    thermal_range_percentile: float | None = Field(default=None, description="Percentyl zakresu temperatur (0..1) albo null.")
    thermal_range_k: float | None = Field(
        default=None, description="Surowy zakres dobowy temperatury powierzchni [K] (Diviner) dla miejsca z listy; null = brak danych albo własne współrzędne."
    )
    solar_visibility_fraction: float | None = Field(default=None, description="Ułamek czasu, gdy Słońce jest nad horyzontem terenu, albo null.")
    mafic_felsic_percentile: float | None = Field(
        default=None, description="Percentyl składu mafic-felsic (0 = felsic, 1 = mafic) względem Księżyca albo null (np. bieguny)."
    )
    minerals: dict[str, float] | None = Field(
        default=None, description="Udziały plagioklaz/piroksen/oliwin łatki Księżyca (Diviner, ±70°); null poza zasięgiem."
    )
    composition_status: str | None = Field(default=None, description="ok / outside_diviner_cf_coverage / missing; null = nie liczone.")


CostClass = Literal["LOW", "MEDIUM", "HIGH", "VERY HIGH", "EXCLUDED / MANUAL REVIEW", "missing"]
FlagStatus = Literal["ok", "warning", "manual_review", "excluded", "missing"]


class Practicality(Model):
    """Koszt/praktyczność symulacji (0-100, wyższe = łatwiej/taniej). Niezależne od podobieństwa naukowego."""

    access_score: float | None = None
    buildability_score: float | None = None
    emergency_support_score: float | None = None
    infrastructure_score: float | None = None
    population_score: float | None = None
    isolation_logistics_penalty: float | None = Field(default=None, description="0-100, wyższe = gorzej (mało ludzi = izolacja logistyczna).")
    population_impact_penalty: float | None = Field(default=None, description="0-100, wyższe = gorzej (dużo ludzi = wpływ społeczny); osobno od izolacji.")
    population_25km: float | None = None
    grid_source: Literal["osm", "estimated", "missing"] | None = Field(default=None, description="estimated = przybliżenie z wiedzy ogólnej, nie z mapy.")
    field_campaign_score: float | None = None
    field_cost_class: CostClass | None = None
    facility_score: float | None = None
    facility_cost_class: CostClass | None = None
    practicality_completeness: float | None = Field(default=None, description="Udział dostępnych wymiarów (0-1); niska wartość obniża pewność, nie wynik.")
    practicality_confidence: Literal["high", "medium", "low", "missing"] | None = None
    pareto_field: bool = Field(default=False, description="Niezdominowany (odległość naukowa vs field_campaign_score) wśród zwróconych kandydatów.")
    pareto_facility: bool = Field(default=False, description="To samo dla facility_score.")


class Constraints(Model):
    """Ograniczenia wewnętrzne lokalizacji (flagi, nie wynik liczbowy)."""

    protected_area_status: FlagStatus
    world_heritage_status: FlagStatus
    community_rights_status: FlagStatus = Field(description="Brak danych o prawach wspólnot nigdy nie oznacza 'ok' (manual_review).")
    biodiversity_status: FlagStatus
    water_stress_status: FlagStatus
    hazard_status: FlagStatus
    security_status: FlagStatus
    hard_excluded: bool
    exclusion_reasons: list[str]


class Analog(Model):
    rank: int
    patch_id: str
    region: str
    region_name: str
    source: Literal["NASADEM", "COPDEM"]
    lat: float
    lon: float
    slope_distance: float
    shape_distance: float
    total_distance: float = Field(description="Mniejsza = bardziej podobny teren.")
    terrain_distance: float | None = Field(default=None, description="Tylko teren; ustawione, gdy w_thermal lub w_illum > 0.")
    thermal_distance: float | None = None
    thermal_status: Literal["ok", "missing"] | None = None
    illumination_distance: float | None = None
    illumination_status: Literal["ok", "missing"] | None = None
    terrain_quality: Literal["good", "moderate", "poor"] | None = Field(
        default=None, description="Etykieta składnika (odległość < 0.5 good, < 1.0 moderate, dalej poor); ustawiona razem z terrain_distance."
    )
    thermal_quality: Literal["good", "moderate", "poor"] | None = None
    illumination_quality: Literal["good", "moderate", "poor"] | None = None
    composition_distance: float | None = None
    composition_status: Literal["ok", "missing"] | None = None
    composition_quality: Literal["good", "moderate", "poor"] | None = None
    composition_confidence: str | None = Field(
        default=None, description="high / medium / low / low_quartz_confounder (pewność proxy składu patch'a Ziemi)."
    )
    composition_source: Literal["aster_mi", "lithology_minerals"] | None = Field(
        default=None,
        description="Źródło składnika składu: lithology_minerals = zapas, gdy brak tabeli ASTER (mieszanka minerałów Diviner vs szacunek z litologii Macrostrat, confidence low_lithology_estimate).",
    )
    earth_mafic_felsic_percentile: float | None = None
    earth_plagioclase_fraction: float | None = Field(
        default=None, description="Szacunek (litologia Macrostrat x typowy skład modalny), nie pomiar."
    )
    earth_pyroxene_fraction: float | None = None
    earth_olivine_fraction: float | None = None
    earth_other_fraction: float | None = Field(default=None, description="Minerały bez odpowiednika na Księżycu (kwarc, skalenie K, węglany, ewaporaty, iły).")
    earth_mineral_status: Literal["estimated", "no_lithology"] | None = None
    mineral_distance: float | None = Field(
        default=None,
        description="Diagnostyka (poza wynikiem): połowa odległości L1 między składem Księżyca (Diviner: plagioklaz/piroksen/oliwin) i Ziemi (szacunek; minerały bez odpowiednika na Księżycu liczą się jako niezgodność); 0 = identyczne, 1 = rozłączne; null = brak danych.",
    )
    dominant_lithology: str | None = Field(
        default=None,
        description="Dominująca litologia podłoża (Macrostrat; mafic/felsic/anorthosite/carbonate/evaporite/sedimentary/unconsolidated/unknown). Tylko objaśnienie, nie wchodzi do wyniku.",
    )
    mixed_lithology_flag: bool | None = Field(default=None, description="True, gdy żadna klasa nie obejmuje >= 60% zmapowanych punktów łatki.")
    stability: float | None = Field(
        default=None, description="Ułamek przebiegów z szumem (stability_runs), w których łatka zostaje w top-K; null = nie liczone."
    )
    thermal_range_k: float | None = Field(
        default=None, description="Surowy zakres dobowy temperatury powierzchni łatki [K] (MODIS); null = brak danych. Tylko do wyświetlania."
    )
    solar_visibility_fraction: float | None = Field(
        default=None, description="Ułamek dnia (Słońce nad horyzontem astronomicznym), gdy teren nie zasłania Słońca (0..1); null = brak danych."
    )
    practicality: Practicality | None = Field(default=None, description="Tylko gdy include_practicality=true i tabela istnieje.")
    constraints: Constraints | None = None
    features: dict[str, float]
    z_scores: dict[str, float]


class AnalogsResponse(Model):
    moon: MoonSummary
    w_slope: float
    feature_weights: dict[str, float] | None = None
    w_thermal: float = 0.0
    w_illum: float = 0.0
    w_composition: float = 0.0
    top_k: int
    max_per_region: int | None
    out_of_range: list[str] = Field(
        description="Cechy Księżyca z |z| > out_of_range_z: ranking mniej wiarygodny - pokaż ostrzeżenie."
    )
    results: list[Analog]

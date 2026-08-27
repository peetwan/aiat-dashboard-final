from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, JsonValue


JsonObject = dict[str, Any]


class PublicApiModel(BaseModel):
    """Base contract for versioned public responses.

    The public artifacts can add reviewed fields without breaking older clients,
    while the fields declared by each model remain stable and visible in OpenAPI.
    """

    model_config = ConfigDict(extra="allow")


class PublicCatalogSummary(PublicApiModel):
    public_sources: int
    candidate_records_referenced: int
    provinces_with_evidence: int
    geocoded_cultural_points: int
    cultural_supporting_records: int
    restricted_sources_excluded: int
    unmapped_public_records: int


class PublicSourceResponse(PublicApiModel):
    ordinal: int
    source_id: str
    name_th: str
    url: str
    acquisition_mode: str
    expected_record_count: int
    readiness_status: str
    quality_label_th: str
    notes_th: str


class ProvinceResponse(PublicApiModel):
    province_code: str
    province_name_th: str
    province_name_en: str
    region: str
    centroid: list[float]
    sra_overall_score: int | float | None
    sra_dimension_scores: dict[str, int | float | None]
    sra_scope_status: str
    sra_as_of: str | None
    area_based_project_groups: int
    area_based_participant_records: int
    innovation_records: int
    cultural_records: int
    housing_observations: int
    housing_demand_responses: int
    pppconnext_aggregate_rows: int
    learning_dashboard_business_records: int
    apptech_registered_users: int | float | None
    apptech_interactions: int
    city_capital_cities: int
    disaster_source_count: int
    disaster_record_count: int
    disaster_sources: list[str]
    evidence_sources: list[str]
    evidence_source_count: int
    quality_status: str
    visual_index: dict[str, float]


class PublicCatalogResponse(PublicApiModel):
    schema_version: str
    generated_at: str
    publication_status: str
    warning_th: str
    summary: PublicCatalogSummary
    unmapped: JsonObject
    themes: list[JsonObject]
    metrics: dict[str, JsonObject]
    sources: list[PublicSourceResponse]
    provinces: list[ProvinceResponse]
    methodology: JsonObject


class PublicOverviewResponse(PublicApiModel):
    schema_version: str
    generated_at: str
    publication_status: str
    warning_th: str
    summary: PublicCatalogSummary
    themes: list[JsonObject]
    metrics: dict[str, JsonObject]
    methodology: JsonObject


class F1OverviewResponse(PublicApiModel):
    schema_version: str
    generated_at: str | None
    publication_status: str
    scope: JsonObject
    totals: JsonObject
    regions: list[JsonObject]
    provinces: list[JsonObject]
    quality: JsonObject


class F1ProvinceDetailResponse(PublicApiModel):
    schema_version: str
    generated_at: str
    publication_status: str
    source_id: Literal["f1_sradss_ppaos"]
    as_of: str
    source_url: str
    dashboard_url: str
    privacy: JsonObject
    province: JsonObject


class SourceInsightsResponse(PublicApiModel):
    schema_version: str
    generated_at: str
    publication_status: str
    warning_th: str
    audit_summary: JsonObject
    sources: dict[str, JsonObject]
    province_links: dict[str, JsonObject]
    methodology: JsonObject


class SourceCoverageSummary(PublicApiModel):
    registry_source_count: int
    catalog_metadata_source_count: int
    public_candidate_source_count: int
    metadata_only_source_count: int
    restricted_local_only_source_count: int
    sources_with_merged_index_entry: int
    public_candidates_with_observed_count: int
    current_public_data_artifact_source_count: int
    current_province_projection_source_count: int
    restricted_value_leak_count: int


class SourceCoverageItem(PublicApiModel):
    ordinal: int
    source_id: str
    group: str
    name_th: str
    url: str
    source_type: str
    sensitivity_lane: str
    status: JsonObject
    records: JsonObject
    geo: JsonObject
    public_visibility: JsonObject
    evidence: JsonObject
    notes_th: list[str]


class SourceCoverageResponse(PublicApiModel):
    schema_version: str
    generated_at: str
    coverage_scope: str
    inputs: JsonObject
    summary: SourceCoverageSummary
    sources: list[SourceCoverageItem]


class UnmappedRecordsResponse(PublicApiModel):
    schema_version: str
    generated_at: str
    publication_status: str
    total_records: int
    sources: dict[str, JsonObject]
    methodology_th: str


class LearningProvinceRow(PublicApiModel):
    source_row_number: int
    province_name_th: str
    province_code: str
    metric_label_th: str
    value: int | float
    unit: str | None
    as_of: str | None
    scope_warning_th: str
    source_url: str
    endpoint_url: str
    quality_status: str


class LearningDashboardResponse(PublicApiModel):
    schema_version: str
    generated_at: str
    publication_status: str
    source: JsonObject
    quality: JsonObject
    coverage: JsonObject
    province_rows: list[LearningProvinceRow]
    unmatched_province_rows: list[JsonObject]
    province_links: dict[str, LearningProvinceRow]
    non_province_tables: dict[str, JsonObject]
    non_province_impact: JsonObject
    evidence: list[str]


class DisasterSourceSummary(PublicApiModel):
    source_id: str
    name_th: str
    count: int
    dataset_keys: list[str]
    latest_observed_at: str | None
    latest_fetched_at: str | None
    quality_label_th: str
    insights: JsonObject
    records: list[JsonObject]


class DisasterTrackingResponse(PublicApiModel):
    province_code: str
    province_name: str
    source_count: int
    record_count: int
    latest_observed_at: str | None
    quality_label_th: str
    sources: dict[str, DisasterSourceSummary]


class DisasterProvinceIndexItem(PublicApiModel):
    province_name: str
    sources: list[str]
    total_records: int


class DisasterProvinceIndexResponse(PublicApiModel):
    provinces: dict[str, DisasterProvinceIndexItem]
    total_provinces: int


class DisasterTimeseriesResponse(PublicApiModel):
    province_code: str
    province_name: str | None = None
    series: list[JsonObject]


class DisasterStationHistoryResponse(PublicApiModel):
    province_code: str
    province_name: str | None = None
    station_id: str
    station_name: str | None = None
    metric: Literal["water", "rain"]
    grain: Literal["daily", "weekly", "monthly"]
    days: int
    window_start: str | None = None
    window_end: str | None = None
    unit: str
    history_status: Literal["available", "snapshot_only", "unavailable"]
    quality_label_th: str
    points: list[JsonObject]


class DatabaseCoverageResponse(PublicApiModel):
    status: Literal["complete", "incomplete"]
    database_backend: str
    serving_mode: str
    source_catalog_rows: int
    endpoint_catalog_rows: int
    runtime_enabled_endpoints: int
    public_value_sources: int
    public_policy_sources: int
    metadata_only_sources: int
    restricted_local_only_sources: int
    published_catalog_source_count: int
    published_catalog_ids_match_approved: bool
    restricted_catalog_sources_published: int
    public_artifacts_in_database: int
    public_artifacts_expected: int
    artifact_groups: dict[str, int]
    province_briefings: int
    executive_summaries: int
    spatial_features_in_database: int
    spatial_features_expected: int
    spatial_layer_counts: dict[str, int]
    spatial_complete: bool
    housing_demand_records_in_database: int
    housing_demand_records_expected: int
    housing_demand_complete: bool
    restricted_values_published: int
    operational_candidate_records: int
    raw_data_storage: str


class OperationsResponse(PublicApiModel):
    schema_version: str
    reviewed_at: str
    status: str
    summary: JsonObject
    scheduler: JsonObject
    last_connectivity_audit: JsonObject
    refresh_sources: list[JsonObject]
    snapshot_sources: list[JsonObject]
    pipeline: list[JsonObject]
    monitoring: JsonObject


class ProvinceIdentity(PublicApiModel):
    province_code: str
    province_name_th: str
    province_name_en: str
    region: str
    centroid: list[float]


class ProvinceSourceCoverage(PublicApiModel):
    source_id: str
    name_th: str
    url: str
    acquisition_mode: str
    readiness_status: str
    status: str
    records: int | None
    note_th: str | None
    quality_label_th: str | None = None
    source_note_th: str | None = None
    data_grain_th: str | None = None
    observed_as_of: str | None = None
    observed_fetched_at: str | None = None
    record_breakdown: JsonObject | None = None


class ProvinceBriefingSection(PublicApiModel):
    source_id: str
    title_th: str
    status: str
    total_records: int
    items: list[JsonObject]


class ProvincialBriefingResponse(PublicApiModel):
    schema_version: str
    generated_at: str
    publication_status: str
    province: ProvinceIdentity
    executive_signals: list[JsonObject]
    sections: dict[str, ProvinceBriefingSection]
    source_coverage: list[ProvinceSourceCoverage]
    quality: JsonObject
    available_source_ids: list[str]


class ExecutiveDimension(PublicApiModel):
    key: str
    label_th: str
    summary_th: str
    metrics: list[JsonObject]
    breakdowns: list[JsonObject]
    highlights: list[JsonObject]
    source_ids: list[str]


class ExecutiveSummaryResponse(PublicApiModel):
    schema_version: str
    generated_at: str
    publication_status: str
    province: ProvinceIdentity
    readout: JsonObject
    research_portfolio: JsonObject
    decision_chain: list[JsonObject]
    data_quality_overview: JsonObject
    dimensions: list[ExecutiveDimension]
    missing_dimensions: list[JsonObject]
    coverage: JsonObject
    source_coverage: list[ProvinceSourceCoverage]
    quality: JsonObject
    methodology: JsonObject


class GeoJSONGeometry(PublicApiModel):
    type: str
    coordinates: JsonValue


class GeoJSONFeature(PublicApiModel):
    type: Literal["Feature"]
    geometry: GeoJSONGeometry
    properties: dict[str, JsonValue]


class ProvinceFeatureCollectionResponse(PublicApiModel):
    type: Literal["FeatureCollection"]
    features: list[GeoJSONFeature]
    source: str
    license_note_th: str
    generated_at: str
    quality_status: str


class CulturalPointFeatureCollectionResponse(PublicApiModel):
    type: Literal["FeatureCollection"]
    name: str
    source_id: str
    quality_status: str
    features: list[GeoJSONFeature]


class HousingSpatialSummaryResponse(PublicApiModel):
    schema_version: str
    generated_at: str
    source_id: Literal["f3_housing_portal"]
    publication_status: str
    quality_status: str
    as_of: str
    counts: dict[str, int]
    total_spatial_features: int
    housing_points: JsonObject
    accessibility_grid: JsonObject
    flood_grid: JsonObject
    database_contract: JsonObject
    evidence: list[str]


class HousingSpatialFeatureCollectionResponse(PublicApiModel):
    type: Literal["FeatureCollection"]
    layer_id: str
    total_in_layer: int
    returned: int
    quality_status: str
    features: list[GeoJSONFeature]


class HousingDemandSummaryResponse(PublicApiModel):
    schema_version: str
    generated_at: str
    source_id: Literal["f3_housing_portal"]
    publication_status: str
    quality_status: str
    record_count: int
    province_count: int
    privacy_projection: JsonObject
    national: JsonObject
    provinces: dict[str, JsonObject]
    evidence: JsonObject


class HealthResponse(PublicApiModel):
    status: Literal["ok", "unhealthy"]
    database: Literal["connected", "disconnected"]
    database_backend: str
    public_artifacts: int
    public_artifacts_expected: int
    source_catalog_rows: int
    public_value_sources: int
    metadata_only_sources: int
    restricted_local_only_sources: int
    spatial_features: int
    spatial_features_expected: int
    spatial_complete: bool
    housing_demand_records: int
    housing_demand_records_expected: int
    housing_demand_complete: bool
    published_catalog_ids_match_approved: bool
    restricted_values_published: int
    app_env: str

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
    pppconnext_aggregate_rows: int
    learning_dashboard_business_records: int
    apptech_registered_users: int | float | None
    apptech_interactions: int
    city_capital_cities: int
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
    published_catalog_ids_match_approved: bool
    restricted_values_published: int
    app_env: str

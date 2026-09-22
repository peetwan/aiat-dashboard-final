import json
from types import SimpleNamespace

import pytest

from tools.f2_pipeline.common import PipelineError
from tools.f2_pipeline.domains.activities import TABLE_COLUMNS as ACTIVITY_COLUMNS
from tools.f2_pipeline.domains.activities import build_tables as build_activity_tables
from tools.f2_pipeline.domains.cultural_areas import build_tables as build_area_tables
from tools.f2_pipeline.domains.raw_inputs import SOURCE_IDS


def _raw_bundle(source_id, dataset, file, sha256, document):
    return {
        "datasets": {dataset: document},
        "metadata": {
            dataset: {
                "source_id": source_id,
                "run_id": "run-1",
                "file": file,
                "sha256": sha256,
            }
        },
        "files": [],
    }


def _observation(source_id, source_key, observation_id, file, sha256):
    return {
        "observation_id": observation_id,
        "source_id": source_id,
        "source_key": source_key,
        "raw_file": file,
        "row_locator": f"evidence://{source_id}/run-1/{file}#/data/0",
        "file_sha256": sha256,
        "captured_at": "2026-01-01T00:00:00Z",
    }


def _area_fixture():
    atlocal_id = SOURCE_IDS["atlocal"]
    cultural_map_id = SOURCE_IDS["cultural_map"]
    source_tables = {
        atlocal_id: {
            "areas": [
                {
                    "area_id": "area-atlocal",
                    "observation_id": "obs-atlocal",
                    "name": "Area A",
                    "description": "",
                    "source_key": "areas_16:1",
                    "images_json": "[]",
                    "identity_status": "source_named_cultural_area",
                }
            ],
            "source_observations": [
                _observation(
                    atlocal_id,
                    "areas_16:1",
                    "obs-atlocal",
                    "areas_16.json",
                    "sha-atlocal",
                )
            ],
        },
        cultural_map_id: {
            "mapped_subjects": [
                {
                    "subject_id": "area-map",
                    "source_keys_json": '["map_inspiration:CS-1"]',
                    "display_title": "Area B",
                    "cultural_area_eligible": "True",
                    "primary_category_codes_json": '["CS"]',
                }
            ],
            "mapped_listing_observations": [
                {
                    "subject_id": "area-map",
                    "observation_id": "obs-map",
                    "source_key": "map_inspiration:CS-1",
                    "title_raw": "Area B",
                    "primary_category_code": "CS",
                }
            ],
            "source_observations": [
                _observation(
                    cultural_map_id,
                    "map_inspiration:CS-1",
                    "obs-map",
                    "map_inspiration.json",
                    "sha-map",
                )
            ],
        },
    }
    raw_inputs = {
        atlocal_id: _raw_bundle(
            atlocal_id,
            "areas",
            "areas_16.json",
            "sha-atlocal",
            {"data": [{"area_id": "1"}]},
        ),
        cultural_map_id: _raw_bundle(
            cultural_map_id,
            "map_inspiration",
            "map_inspiration.json",
            "sha-map",
            {"data": [{"external_id": "CS-1"}]},
        ),
    }
    reviews = {
        "cross_source_cultural_areas/reviews.json": [
            {
                "atlocal_source_key": "areas_16:1",
                "cultural_map_source_key": "map_inspiration:CS-1",
                "decision": "separate",
                "decision_id": "area-review-1",
                "evidence": "Synthetic distinct subjects",
            }
        ],
        "cross_source_cultural_areas/runtime.json": {
            "schema_version": 1,
            "expected_counts": {
                "atlocal_eligible_members": 1,
                "cultural_map_eligible_members": 1,
                "eligible_cross_source_overlap": 0,
                "k01b_cultural_areas": 2,
                "global_subjects": 2,
                "source_members": 2,
                "assertions": 2,
                "accepted_links": 0,
                "accepted_separations": 1,
            },
        },
    }
    return source_tables, reviews, raw_inputs


def test_cultural_areas_preserve_boundaries_and_report_only_used_source_files():
    source_tables, reviews, raw_inputs = _area_fixture()

    tables = build_area_tables(source_tables, reviews, raw_inputs, None)

    decision = tables["identity_decisions"][0]
    assert decision["left_global_area_id"] != decision["right_global_area_id"]
    assert tables["source_files"] == [
        {
            "source_id": SOURCE_IDS["atlocal"],
            "file": "areas_16.json",
            "sha256": "sha-atlocal",
        },
        {
            "source_id": SOURCE_IDS["cultural_map"],
            "file": "map_inspiration.json",
            "sha256": "sha-map",
        },
    ]


def test_cultural_areas_fail_when_the_accepted_count_snapshot_changes():
    source_tables, reviews, raw_inputs = _area_fixture()
    reviews["cross_source_cultural_areas/runtime.json"]["expected_counts"][
        "global_subjects"
    ] = 1

    with pytest.raises(PipelineError, match="counts differ from accepted snapshot"):
        build_area_tables(source_tables, reviews, raw_inputs, None)


def _activity_fixture():
    icommunity_id = SOURCE_IDS["icommunity"]
    atlocal_id = SOURCE_IDS["atlocal"]
    cultural_map_id = SOURCE_IDS["cultural_map"]
    source_tables = {
        icommunity_id: {
            "source_observations": [
                _observation(
                    icommunity_id,
                    "I-1",
                    "obs-icommunity",
                    "icommunity.json",
                    "sha-icommunity",
                )
            ],
            "publications": [
                {
                    "publication_id": "publication-icommunity",
                    "observation_id": "obs-icommunity",
                    "source_id": "I-1",
                    "title": "Community activity",
                    "content": "Activity content",
                    "published_at": "",
                    "source_url": "https://example.invalid/icommunity",
                }
            ],
            "activities": [
                {
                    "activity_id": "activity-icommunity",
                    "publication_id": "publication-icommunity",
                    "observation_id": "obs-icommunity",
                    "name": "Community activity",
                    "start_date": "",
                    "end_date": "",
                    "status": "source_reported",
                    "identity_status": "source_local",
                    "evidence_excerpt": "Activity content",
                    "province": "Bangkok",
                }
            ],
            "activity_venue_evidence": [
                {
                    "activity_id": "activity-icommunity",
                    "venue_evidence_id": "venue-icommunity",
                    "raw_locator": "content_html",
                    "venue_name_raw": "Bangkok",
                    "province_raw": "Bangkok",
                    "location_role": "reported_activity_venue",
                }
            ],
        },
        atlocal_id: {
            "source_observations": [],
            "publications": [],
            "activities": [],
            "activity_sections": [],
        },
        cultural_map_id: {
            "source_observations": [
                _observation(
                    cultural_map_id,
                    "activities:G-1",
                    "obs-map-activity",
                    "activities.json",
                    "sha-activities",
                )
            ],
            "activity_occurrences": [
                {
                    "activity_id": "activity-map",
                    "publication_id": "publication-map",
                    "observation_id": "obs-map-activity",
                    "source_key": "activities:G-1",
                    "name": "Mapped activity",
                    "start_date": "",
                    "end_date": "",
                    "status": "source_reported",
                    "identity_status": "source_local",
                }
            ],
            "activity_publications": [
                {
                    "publication_id": "publication-map",
                    "activity_id": "activity-map",
                    "observation_id": "obs-map-activity",
                    "source_key": "activities:G-1",
                    "external_id": "G-1",
                    "title": "Mapped activity",
                    "description": "Mapped description",
                    "disposition": "counted_occurrence",
                    "parent_key": "",
                    "source_url": "https://example.invalid/map",
                }
            ],
            "activity_dates": [],
            "activity_locations": [],
            "activity_sessions": [],
            "activity_media": [
                {
                    "media_id": "media-map",
                    "activity_id": "activity-map",
                    "observation_id": "obs-map-activity",
                    "source_key": "activities:G-1",
                    "media_kind": "gallery_image",
                    "ordinal": "0",
                    "url_or_value": "image.jpg",
                    "caption": "",
                    "status": "reference_only_content_not_inspected",
                    "source_locator": "data/gallery_images/0",
                }
            ],
            "activity_narrative_evidence": [
                {
                    "evidence_id": "narrative-map",
                    "activity_id": "activity-map",
                    "observation_id": "obs-map-activity",
                    "source_key": "activities:G-1",
                    "field_name": "description",
                    "text": "Mapped description",
                    "source_locator": "data/description",
                }
            ],
        },
    }
    review = {
        "schema_version": 1,
        "activity_source_keys": {
            "icommunity": ["I-1"],
            "atlocal": [],
            "cultural_map": ["G-1"],
        },
        "session_publication_keys": [],
        "protected_boundaries": [
            {
                "review_id": "activity-boundary-1",
                "decision": "keep_separate",
                "reason": "Synthetic distinct activities",
                "members": ["icommunity:I-1", "cultural_map:G-1"],
            }
        ],
        "source_quality": [],
    }
    raw_inputs = {
        icommunity_id: _raw_bundle(
            icommunity_id,
            "pages",
            "icommunity.json",
            "sha-icommunity",
            {"data": [{"content_html": "Activity content"}]},
        ),
        cultural_map_id: _raw_bundle(
            cultural_map_id,
            "activities",
            "activities.json",
            "sha-activities",
            {
                "data": [
                    {
                        "data": {
                            "gallery_images": ["image.jpg"],
                            "description": "Mapped description",
                        }
                    }
                ]
            },
        ),
    }
    geography = SimpleNamespace(
        provinces=[{"provinceCode": "10", "provinceNameTh": "Bangkok"}]
    )
    return (
        source_tables,
        {"cross_source_activities_coverage/reviewed_evidence.json": review},
        raw_inputs,
        geography,
    )


def test_activity_media_and_narrative_resolve_global_identity_and_raw_evidence():
    source_tables, reviews, raw_inputs, geography = _activity_fixture()

    tables = build_activity_tables(source_tables, reviews, raw_inputs, geography)

    activity_id = next(
        row["global_activity_id"]
        for row in tables["global_activities"]
        if row["source"] == "cultural-map-v1"
    )
    media = tables["activity_media"][0]
    narrative = tables["activity_narrative_evidence"][0]
    assert set(media) == set(ACTIVITY_COLUMNS["activity_media"])
    assert set(narrative) == set(ACTIVITY_COLUMNS["activity_narrative_evidence"])
    assert media["global_activity_id"] == narrative["global_activity_id"] == activity_id
    assert media["raw_locator"] == (
        "evidence://f2_culturalmap_university/run-1/activities.json#/data/0/data/gallery_images/0"
    )
    assert narrative["raw_locator"] == (
        "evidence://f2_culturalmap_university/run-1/activities.json#/data/0/data/description"
    )
    boundary_members = json.loads(
        tables["activity_identity_decisions"][0]["global_members_json"]
    )
    assert len(boundary_members) == len(set(boundary_members)) == 2

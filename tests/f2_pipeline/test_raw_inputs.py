import pytest

from tools.f2_pipeline.common import PipelineError
from tools.f2_pipeline.domains.raw_inputs import SOURCE_IDS, observation_uri
from tools.f2_pipeline.domains.resolution import locator_matches


@pytest.mark.parametrize(
    "fields",
    [
        {"file_sha256": "locked-hash"},
        {"raw_file_sha256": "locked-hash"},
        {"file_sha256": "locked-hash", "raw_file_sha256": "locked-hash"},
        {},
        {"raw_file_sha256": "stale-hash"},
        {"file_sha256": "locked-hash", "raw_file_sha256": "conflicting-hash"},
    ],
)
def test_source_hash_column_variants_require_the_same_exact_declared_file(fields):
    source = SOURCE_IDS["learning_area_based"]
    raw = {
        source: {
            "metadata": {
                "records": {
                    "file": "records.json",
                    "sha256": "locked-hash",
                    "run_id": "run",
                }
            },
            "files": [{"path": "records.json", "sha256": "locked-hash"}],
        }
    }
    observation = {"raw_file": "records.json", "row_locator": "data/0", **fields}
    if fields and all(value == "locked-hash" for value in fields.values()):
        assert (
            observation_uri(raw, source, observation)
            == f"evidence://{source}/run/records.json#data/0"
        )
    else:
        with pytest.raises(PipelineError, match="hash differs"):
            observation_uri(raw, source, observation)


def test_learning_locator_aliases_preserve_source_run_and_record_boundaries():
    citation = "evidence://f2_learning_area_based/run/records.json.gz#data/0/text"
    assert locator_matches(
        citation, "evidence://f2_learning_area_based/run/records.json#data/0"
    )
    for other in (
        "evidence://f2_learning_dashboard/run/records.json#data/0",
        "evidence://f2_learning_area_based/other-run/records.json#data/0",
        "evidence://f2_learning_area_based/run/records.json#data/1",
    ):
        assert not locator_matches(citation, other)

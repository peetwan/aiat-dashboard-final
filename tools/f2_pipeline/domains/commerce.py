"""Pure reviewed cross-source operator and offering registry.

Only explicit reviewed matches create cross-source unions.  Source-local products,
operators, evidence, relationships, locations, prices, and media remain separate
records behind the ``build_tables`` seam.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any, Iterable

from ..common import PipelineError, canonical_json
from .commerce_sources import OfferingSources, load_sources
from .raw_inputs import SOURCE_IDS, resolve_evidence
from .resolution import (
    json_list,
    locator_matches,
    logical_source,
    review_payload,
    source_tables_for,
)

TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "global_operators": (
        "global_operator_id",
        "display_name",
        "aliases_json",
        "source_count",
        "source_entity_count",
        "identity_status",
    ),
    "global_offerings": (
        "global_offering_id",
        "display_name",
        "aliases_json",
        "source_count",
        "source_entity_count",
        "identity_status",
    ),
    "operator_crosswalk": (
        "global_operator_id",
        "source_operator_id",
        "source",
        "source_local_operator_id",
        "display_name",
        "identity_status",
        "source_details_json",
    ),
    "offering_crosswalk": (
        "global_offering_id",
        "source_offering_id",
        "source",
        "source_local_offering_id",
        "display_name",
        "identity_status",
        "source_details_json",
    ),
    "listing_evidence": (
        "source_listing_id",
        "source",
        "source_local_listing_id",
        "source_offering_id",
        "global_offering_id",
        "source_operator_id",
        "global_operator_id",
        "observation_id",
        "source_key",
        "raw_source_id",
        "raw_locator",
        "title_raw",
        "title_normalized",
        "description",
        "category_raw",
        "source_url",
        "listing_eligibility",
        "source_details_json",
    ),
    "seller_evidence": (
        "source_seller_evidence_id",
        "source",
        "source_operator_id",
        "global_operator_id",
        "source_offering_id",
        "global_offering_id",
        "source_listing_id",
        "observation_id",
        "source_key",
        "raw_locator",
        "role",
        "evidence_text",
        "basis",
        "source_details_json",
    ),
    "operator_offering_edges": (
        "source_operator_offering_edge_id",
        "source",
        "source_operator_id",
        "global_operator_id",
        "source_offering_id",
        "global_offering_id",
        "source_listing_id",
        "observation_id",
        "source_key",
        "raw_locator",
        "relationship",
        "evidence_text",
        "source_details_json",
    ),
    "locations": (
        "source_location_id",
        "source",
        "source_entity_id",
        "source_offering_id",
        "global_offering_id",
        "source_operator_id",
        "global_operator_id",
        "observation_id",
        "source_key",
        "raw_locator",
        "location_role",
        "province_raw",
        "district_raw",
        "province_normalized",
        "province_code",
        "district_normalized",
        "district_code",
        "subdistrict_normalized",
        "subdistrict_code",
        "status",
        "source_details_json",
    ),
    "prices": (
        "source_price_id",
        "source",
        "source_listing_id",
        "source_offering_id",
        "global_offering_id",
        "observation_id",
        "source_key",
        "raw_locator",
        "price_text_raw",
        "amounts_json",
        "currency",
        "parse_status",
        "source_details_json",
    ),
    "media": (
        "source_media_id",
        "source",
        "source_listing_id",
        "source_offering_id",
        "global_offering_id",
        "observation_id",
        "source_key",
        "raw_locator",
        "media_kind",
        "ordinal",
        "url_or_value",
        "label",
        "status",
        "source_details_json",
    ),
    "channels": (
        "source_channel_id",
        "source",
        "source_listing_id",
        "source_offering_id",
        "global_offering_id",
        "observation_id",
        "source_key",
        "raw_locator",
        "channel",
        "platform_shop_id",
        "channel_evidence",
        "source_details_json",
    ),
    "person_operator_links": (
        "source_person_operator_link_id",
        "source",
        "source_person_id",
        "global_person_id",
        "source_operator_id",
        "global_operator_id",
        "observation_id",
        "source_key",
        "raw_locator",
        "relationship",
        "evidence_text",
        "source_details_json",
    ),
    "source_local_boundaries": (
        "source_boundary_id",
        "source",
        "boundary_kind",
        "status",
        "reason",
        "source_keys_json",
        "observation_ids_json",
        "source_entity_ids_json",
        "source_locator",
        "global_operator_id",
        "global_offering_id",
    ),
    "identity_decisions": (
        "review_id",
        "entity_kind",
        "left",
        "right",
        "decision",
        "decision_origin",
        "reason",
        "left_source_keys_json",
        "right_source_keys_json",
        "evidence_json",
        "applied",
        "application",
    ),
    "candidate_pairs": (
        "review_id",
        "entity_kind",
        "left",
        "right",
        "decision",
        "decision_origin",
        "reason",
    ),
    "measure_results": ("measure", "value", "scope", "status"),
    "measure_contributions": ("measure", "entity_id"),
    "source_files": (
        "path",
        "sha256",
        "fingerprint_kind",
        "reviewed_sha256",
    ),
}


def json_text(value: Any) -> str:
    """Encode deterministic legacy JSON without escaping Unicode."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_id(prefix: str, *parts: str) -> str:
    """Return the accepted U+001F-delimited SHA-256 identity."""
    value = "\x1f".join(parts)
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]}"


class UnionFind:
    def __init__(self, values: Iterable[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> bool:
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return False
        keep, drop = sorted((left_root, right_root))
        self.parent[drop] = keep
        return True


def components(union: UnionFind) -> list[list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for value in union.parent:
        grouped[union.find(value)].append(value)
    return sorted(
        (sorted(values) for values in grouped.values()), key=lambda values: values
    )


def _raw_file_index(raw_inputs: dict[str, dict]) -> dict[str, str]:
    """Index each declared raw path by that path's own immutable byte hash."""
    index: dict[str, str] = {}
    commerce_source_ids = {
        SOURCE_IDS[source] for source in ("atlocal", "cultural_map", "icommunity")
    }
    for canonical_source_id in sorted(commerce_source_ids):
        bundle = raw_inputs.get(canonical_source_id)
        if not isinstance(bundle, dict):
            raise PipelineError(
                f"commerce input contract: missing raw input {canonical_source_id}"
            )
        metadata = bundle.get("metadata", {})
        runs = {
            str(item.get("run_id", ""))
            for item in metadata.values()
            if isinstance(item, dict) and item.get("run_id")
        }
        if len(runs) != 1:
            raise PipelineError(
                f"commerce input contract: raw input {canonical_source_id} lacks one run identity"
            )
        run_id = next(iter(runs))
        for item in bundle.get("files", []):
            if (
                not isinstance(item, dict)
                or not item.get("path")
                or not item.get("sha256")
            ):
                continue
            path = f"evidence://{canonical_source_id}/{run_id}/{item['path']}"
            own_hash = str(item["sha256"])
            if path in index and index[path] != own_hash:
                raise PipelineError(
                    f"commerce input contract: raw path has conflicting hashes {path}"
                )
            index[path] = own_hash
    return index


def _table_fingerprint(rows: list[dict], path: str) -> str:
    if any(
        not isinstance(row, dict)
        or any(not isinstance(value, str) for value in row.values())
        for row in rows
    ):
        raise PipelineError(
            f"commerce input contract: normalized producer is not a CSV-scalar table {path}"
        )
    return hashlib.sha256(canonical_json(rows).encode("utf-8")).hexdigest()


def _validate_runtime_pins(
    runtime: dict[str, Any],
    source_tables: dict[str, dict[str, list[dict]]],
    raw_inputs: dict[str, dict],
    people_tables: dict[str, list[dict]],
) -> list[dict[str, str]]:
    if runtime.get("schema_version") != 1 or not isinstance(
        runtime.get("source_input_pins"), list
    ):
        raise PipelineError("commerce input contract: unsupported runtime schema")
    if not isinstance(runtime.get("review_counts"), dict):
        raise PipelineError("commerce input contract: runtime review_counts is missing")
    if (
        runtime.get("review_file")
        != "review-config://cross_source_offerings/reviews/reviewed_evidence.json"
    ):
        raise PipelineError(
            "commerce input contract: runtime review_file does not name the locked evidence"
        )
    raw_index = _raw_file_index(raw_inputs)
    source_files: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for pin in runtime["source_input_pins"]:
        if not isinstance(pin, dict):
            raise PipelineError(
                "commerce input contract: runtime pin must be an object"
            )
        path = str(pin.get("path", ""))
        expected = str(pin.get("sha256", ""))
        if not path or not expected or path in seen_paths:
            raise PipelineError(
                "commerce input contract: runtime pin has a missing value or duplicate path"
            )
        seen_paths.add(path)
        if path.startswith("evidence://"):
            current_sha = raw_index.get(path)
            if current_sha is None:
                raise PipelineError(
                    f"commerce input contract: missing declared raw source path {path}"
                )
            fingerprint_kind = "raw_file"
        # Normalized hashes describe the frozen CSV serialization.  At this
        # pure seam, fingerprint the fresh producer table instead of treating
        # that historical byte hash as current validation.
        elif path == "normalized://cross_source/people-v1/person_crosswalk.csv":
            table_rows = people_tables.get("person_crosswalk")
            if not isinstance(table_rows, list):
                raise PipelineError(
                    f"commerce input contract: missing normalized producer endpoint {path}"
                )
            current_sha = _table_fingerprint(table_rows, path)
            fingerprint_kind = "canonical_json_table"
        elif path.startswith("normalized://source_local/"):
            parts = path.removeprefix("normalized://source_local/").split("/")
            if (
                len(parts) != 2
                or not parts[0].endswith("-v1")
                or not parts[1].endswith(".csv")
            ):
                raise PipelineError(
                    f"commerce input contract: malformed normalized source endpoint {path}"
                )
            source = logical_source(parts[0].removesuffix("-v1"))
            _, tables = source_tables_for(source_tables, source)
            table_name = parts[1].removesuffix(".csv")
            table_rows = tables.get(table_name)
            if not isinstance(table_rows, list):
                raise PipelineError(
                    f"commerce input contract: missing normalized producer endpoint {path}"
                )
            current_sha = _table_fingerprint(table_rows, path)
            fingerprint_kind = "canonical_json_table"
        elif path.startswith("normalized://"):
            raise PipelineError(
                f"commerce input contract: unsupported normalized producer endpoint {path}"
            )
        else:
            raise PipelineError(
                f"commerce input contract: runtime contains non-immutable pin {path}"
            )
        source_files.append(
            {
                "path": path,
                "sha256": current_sha,
                "fingerprint_kind": fingerprint_kind,
                "reviewed_sha256": expected,
            }
        )
    return sorted(source_files, key=lambda row: row["path"])


def _citation_locator(
    source: str,
    item: dict[str, Any],
    current: dict[str, Any],
    raw_inputs: dict[str, dict],
) -> None:
    reviewed = str(item.get("raw_locator", ""))
    if not reviewed:
        return
    try:
        resolve_evidence(raw_inputs, reviewed)
    except PipelineError as exc:
        raise PipelineError(
            f"commerce input contract: review raw locator is stale: {source}:{current['observation_id']}"
        ) from exc
    if not locator_matches(reviewed, str(current["raw_locator"])):
        raise PipelineError(
            f"commerce input contract: review raw locator belongs to another source record: {source}:{current['observation_id']}"
        )


def _load_reviews(
    reviews: dict[str, Any],
    runtime: dict[str, Any],
    bundle: OfferingSources,
    raw_inputs: dict[str, dict],
) -> list[dict[str, Any]]:
    evidence = review_payload(
        reviews, "cross_source_offerings/reviews/reviewed_evidence.json"
    )
    if not isinstance(evidence, dict):
        raise PipelineError(
            "commerce input contract: invalid reviewed evidence payload"
        )
    offering_reviews = evidence.get("offering_reviews")
    operator_reviews = evidence.get("operator_reviews")
    additional_reviews = evidence.get("additional_reviews", [])
    if (
        not isinstance(offering_reviews, list)
        or not isinstance(operator_reviews, list)
        or not isinstance(additional_reviews, list)
    ):
        raise PipelineError("commerce input contract: invalid review collections")

    listing_index = {
        (str(row["source"]), str(row["observation_id"])): row
        for row in bundle.listing_evidence
    }
    listings_by_source_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(
        list
    )
    for row in bundle.listing_evidence:
        listings_by_source_key[(str(row["source"]), str(row["source_key"]))].append(row)
    seller_index = {
        (
            str(row["source"]),
            str(row["source_operator_id"]),
            str(row["observation_id"]),
        ): row
        for row in bundle.seller_evidence
    }
    sellers_by_source_key: dict[tuple[str, str, str], list[dict[str, Any]]] = (
        defaultdict(list)
    )
    for row in bundle.seller_evidence:
        sellers_by_source_key[
            (
                str(row["source"]),
                str(row["source_operator_id"]),
                str(row["source_key"]),
            )
        ].append(row)

    def check_listing(
        source: str,
        item: dict[str, Any],
        *,
        expected_offering: str = "",
        expected_operator: str = "",
    ) -> None:
        if not isinstance(item, dict):
            raise PipelineError(
                "commerce input contract: listing citation must be an object"
            )
        listing = item.get("listing", item)
        if not isinstance(listing, dict):
            raise PipelineError("commerce input contract: invalid listing citation")
        observation_id = str(listing.get("observation_id", ""))
        source_key = str(listing.get("source_key", ""))
        current = listing_index.get((source, observation_id))
        if current is not None and str(current["source_key"]) != source_key:
            raise PipelineError(
                f"commerce input contract: review source key is stale {source}:{observation_id}"
            )
        if current is None:
            candidates = listings_by_source_key.get((source, source_key), [])
            if expected_offering:
                candidates = [
                    row
                    for row in candidates
                    if row["source_offering_id"]
                    == namespaced(source, expected_offering)
                ]
            if expected_operator:
                candidates = [
                    row
                    for row in candidates
                    if row["source_operator_id"]
                    == namespaced(source, expected_operator)
                ]
            if len(candidates) != 1:
                raise PipelineError(
                    f"commerce input contract: review listing observation cannot be uniquely rebased {source}:{observation_id}"
                )
            current = candidates[0]
        _citation_locator(source, item, current, raw_inputs)
        if expected_offering and current["source_offering_id"] != namespaced(
            source, expected_offering
        ):
            raise PipelineError(
                f"commerce input contract: offering citation belongs to another identity {source}:{observation_id}"
            )
        if expected_operator and current["source_operator_id"] != namespaced(
            source, expected_operator
        ):
            raise PipelineError(
                f"commerce input contract: operator listing belongs to another identity {source}:{observation_id}"
            )

    def check_seller(source: str, item: dict[str, Any], local_operator: str) -> None:
        observation_id = str(item.get("observation_id", ""))
        source_key = str(item.get("source_key", ""))
        source_operator_id = namespaced(source, local_operator)
        current = seller_index.get((source, source_operator_id, observation_id))
        if current is not None and str(current["source_key"]) != source_key:
            raise PipelineError(
                f"commerce input contract: seller evidence source key is stale {source}:{observation_id}"
            )
        if current is None:
            candidates = sellers_by_source_key.get(
                (source, source_operator_id, source_key), []
            )
            if len(candidates) != 1:
                raise PipelineError(
                    f"commerce input contract: seller evidence cannot be uniquely rebased {source}:{observation_id}"
                )
            current = candidates[0]
        _citation_locator(source, item, current, raw_inputs)

    def check_admission(item: dict[str, Any], left: Any, right: Any) -> None:
        if item.get("status") != "reviewed":
            raise PipelineError(
                f"commerce input contract: review is not reviewed {item.get('review_id', '')}"
            )
        if not str(item.get("reason", "")).strip():
            raise PipelineError(
                f"commerce input contract: review has no reason {item.get('review_id', '')}"
            )
        if (
            not isinstance(left, list)
            or not left
            or not isinstance(right, list)
            or not right
        ):
            raise PipelineError(
                f"commerce input contract: review lacks two-sided evidence {item.get('review_id', '')}"
            )

    result: list[dict[str, Any]] = []
    for item in offering_reviews:
        if not isinstance(item, dict):
            raise PipelineError(
                "commerce input contract: offering review must be an object"
            )
        left_evidence = item.get("atlocal_evidence")
        right_evidence = item.get("cultural_map_evidence")
        check_admission(item, left_evidence, right_evidence)
        left_local = str(item.get("atlocal_id", ""))
        right_local = str(item.get("cultural_map_id", ""))
        left, right = (
            namespaced("atlocal", left_local),
            namespaced("cultural_map", right_local),
        )
        if left not in bundle.offerings or right not in bundle.offerings:
            raise PipelineError(
                f"commerce input contract: offering review endpoint no longer resolves {item.get('review_id', '')}"
            )
        for citation in left_evidence:
            check_listing("atlocal", citation, expected_offering=left_local)
        for citation in right_evidence:
            check_listing("cultural_map", citation, expected_offering=right_local)
        left_keys = item.get("atlocal_source_keys")
        right_keys = item.get("cultural_map_source_keys")
        if not isinstance(left_keys, list) or set(map(str, left_keys)) != {
            str(citation["listing"]["source_key"]) for citation in left_evidence
        }:
            raise PipelineError(
                f"commerce input contract: offering review source keys disagree with citations {item.get('review_id', '')}"
            )
        if not isinstance(right_keys, list) or set(map(str, right_keys)) != {
            str(citation["listing"]["source_key"]) for citation in right_evidence
        }:
            raise PipelineError(
                f"commerce input contract: offering review source keys disagree with citations {item.get('review_id', '')}"
            )
        result.append(
            {
                "review_id": str(item.get("review_id", "")),
                "entity_kind": "offering",
                "left": left,
                "right": right,
                "decision": item.get("decision", ""),
                "decision_origin": item.get("decision_origin", ""),
                "reason": item.get("reason", ""),
                "left_source_keys_json": json_text(left_keys),
                "right_source_keys_json": json_text(right_keys),
                "evidence_json": json_text(
                    {"atlocal": left_evidence, "cultural_map": right_evidence}
                ),
            }
        )
    for item in operator_reviews:
        if not isinstance(item, dict):
            raise PipelineError(
                "commerce input contract: operator review must be an object"
            )
        left_evidence = item.get("atlocal_evidence")
        right_evidence = item.get("cultural_map_evidence")
        check_admission(item, left_evidence, right_evidence)
        atlocal = item.get("atlocal")
        cultural = item.get("cultural_map")
        if not isinstance(atlocal, dict) or not isinstance(cultural, dict):
            raise PipelineError("commerce input contract: invalid operator endpoints")
        left_local, right_local = (
            str(atlocal.get("seller_id", "")),
            str(cultural.get("seller_id", "")),
        )
        left, right = (
            namespaced("atlocal", left_local),
            namespaced("cultural_map", right_local),
        )
        if left not in bundle.operators or right not in bundle.operators:
            raise PipelineError(
                f"commerce input contract: operator review endpoint no longer resolves {item.get('review_id', '')}"
            )
        for citation in left_evidence:
            check_seller("atlocal", citation, left_local)
        for citation in right_evidence:
            check_seller("cultural_map", citation, right_local)
        left_listings = item.get("atlocal_listings")
        right_listings = item.get("cultural_map_listings")
        if not isinstance(left_listings, list) or not isinstance(right_listings, list):
            raise PipelineError(
                "commerce input contract: operator listing evidence is invalid"
            )
        for citation in left_listings:
            check_listing("atlocal", citation, expected_operator=left_local)
        for citation in right_listings:
            check_listing("cultural_map", citation, expected_operator=right_local)
        left_listing_keys = {
            str(citation["listing"]["source_key"]) for citation in left_listings
        }
        right_listing_keys = {
            str(citation["listing"]["source_key"]) for citation in right_listings
        }
        if (
            not {str(citation.get("source_key", "")) for citation in left_evidence}
            <= left_listing_keys
            or not {str(citation.get("source_key", "")) for citation in right_evidence}
            <= right_listing_keys
        ):
            raise PipelineError(
                f"commerce input contract: operator review source keys disagree with citations {item.get('review_id', '')}"
            )
        result.append(
            {
                "review_id": str(item.get("review_id", "")),
                "entity_kind": "operator",
                "left": left,
                "right": right,
                "decision": item.get("decision", ""),
                "decision_origin": item.get("decision_origin", "analyst_review"),
                "reason": item.get("reason", ""),
                "left_source_keys_json": json_text(
                    [row.get("source_key", "") for row in left_evidence]
                ),
                "right_source_keys_json": json_text(
                    [row.get("source_key", "") for row in right_evidence]
                ),
                "evidence_json": json_text(
                    {"atlocal": left_evidence, "cultural_map": right_evidence}
                ),
            }
        )
    for item in additional_reviews:
        if not isinstance(item, dict):
            raise PipelineError(
                "commerce input contract: additional review must be an object"
            )
        left_endpoint, right_endpoint = item.get("left"), item.get("right")
        if not isinstance(left_endpoint, dict) or not isinstance(right_endpoint, dict):
            raise PipelineError("commerce input contract: invalid additional endpoints")
        check_admission(
            item, left_endpoint.get("citations"), right_endpoint.get("citations")
        )
        kind = str(item.get("entity_kind", ""))
        if kind not in {"operator", "offering"}:
            raise PipelineError(
                "commerce input contract: unsupported reviewed entity kind"
            )
        endpoints: list[str] = []
        for endpoint in (left_endpoint, right_endpoint):
            source = logical_source(str(endpoint.get("source", "")))
            if source not in {
                "atlocal",
                "cultural_map",
                "icommunity",
            }:
                raise PipelineError(
                    "commerce input contract: unsupported commerce source"
                )
            local_id = str(endpoint.get("local_id", ""))
            identifier = namespaced(source, local_id)
            records = bundle.operators if kind == "operator" else bundle.offerings
            if identifier not in records:
                raise PipelineError(
                    f"commerce input contract: review endpoint no longer resolves {identifier}"
                )
            citations = endpoint.get("citations")
            if not isinstance(citations, list):
                raise PipelineError(
                    "commerce input contract: invalid additional citations"
                )
            for citation in citations:
                check_listing(
                    source,
                    citation,
                    **{f"expected_{kind}": local_id},
                )
                if kind == "operator":
                    check_seller(source, citation, local_id)
            endpoints.append(identifier)
        result.append(
            {
                "review_id": str(item.get("review_id", "")),
                "entity_kind": kind,
                "left": endpoints[0],
                "right": endpoints[1],
                "decision": item.get("decision", ""),
                "decision_origin": item.get("decision_origin", ""),
                "reason": item.get("reason", ""),
                "left_source_keys_json": json_text(
                    [row.get("source_key", "") for row in left_endpoint["citations"]]
                ),
                "right_source_keys_json": json_text(
                    [row.get("source_key", "") for row in right_endpoint["citations"]]
                ),
                "evidence_json": json_text(
                    {"left": left_endpoint, "right": right_endpoint}
                ),
            }
        )

    review_ids = [row["review_id"] for row in result]
    if "" in review_ids or len(review_ids) != len(set(review_ids)):
        raise PipelineError("commerce input contract: missing or duplicate review IDs")
    allowed = {
        "keep_separate",
        "retain_separate_insufficient_identity_evidence",
        "unresolved",
        "match",
    }
    if any(row["decision"] not in allowed for row in result):
        raise PipelineError("commerce input contract: unsupported review decision")
    if any(row["left"] == row["right"] for row in result):
        raise PipelineError(
            "commerce input contract: review endpoints must be distinct identities"
        )
    counts = runtime["review_counts"]
    if sum(row["entity_kind"] == "offering" for row in result) != counts.get(
        "offerings"
    ):
        raise PipelineError("commerce input contract: offering review coverage changed")
    if sum(row["entity_kind"] == "operator" for row in result) != counts.get(
        "operators"
    ):
        raise PipelineError("commerce input contract: operator review coverage changed")
    return sorted(result, key=lambda row: row["review_id"])


def namespaced(source: str, local_id: str) -> str:
    return f"{source}:{local_id}" if local_id else ""


def _apply_reviewed_unions(
    values: Iterable[str], reviews: Iterable[dict[str, Any]], *, entity_kind: str
) -> tuple[UnionFind, list[dict[str, Any]]]:
    union = UnionFind(values)
    protected_decisions = {
        "keep_separate",
        "retain_separate_insufficient_identity_evidence",
        "unresolved",
    }
    protected = {
        frozenset((review["left"], review["right"]))
        for review in reviews
        if review["entity_kind"] == entity_kind
        and review["decision"] in protected_decisions
    }
    for pair in protected:
        left, right = tuple(pair)
        if left not in union.parent or right not in union.parent:
            raise PipelineError(
                "commerce input contract: protected review endpoint is missing"
            )
    applied: list[dict[str, Any]] = []
    relevant = sorted(
        (row for row in reviews if row["entity_kind"] == entity_kind),
        key=lambda row: row["review_id"],
    )
    for review in relevant:
        if review["decision"] in protected_decisions:
            applied.append(
                {
                    **review,
                    "applied": False,
                    "application": "protected_separation",
                }
            )
            continue
        if review["decision"] != "match":
            raise PipelineError(
                f"commerce input contract: unsupported review decision {review['decision']}"
            )
        merge_roots = {
            union.find(review["left"]),
            union.find(review["right"]),
        }
        for pair in protected:
            left, right = tuple(pair)
            protected_roots = {union.find(left), union.find(right)}
            if len(protected_roots) == 1 or (
                len(merge_roots) == 2 and protected_roots == merge_roots
            ):
                raise PipelineError(
                    f"commerce input contract: reviewed match crosses protected component boundary {review['review_id']}"
                )
        changed = union.union(review["left"], review["right"])
        applied.append(
            {
                **review,
                "applied": changed,
                "application": "reviewed_match",
            }
        )
    for pair in protected:
        left, right = tuple(pair)
        if union.find(left) == union.find(right):
            raise PipelineError(
                "commerce input contract: reviewed matches collapse a protected separation"
            )
    return union, applied


def _validate_source_local_identity_preserved(
    records: dict[str, dict[str, Any]], union: UnionFind
) -> None:
    for members in components(union):
        by_source: dict[str, list[str]] = defaultdict(list)
        for member in members:
            by_source[str(records[member]["source"])].append(member)
        duplicates = {
            source: values for source, values in by_source.items() if len(values) > 1
        }
        if duplicates:
            raise PipelineError(
                f"commerce input contract: cross-source review collapses source-local identities {duplicates}"
            )


def _registry_rows(
    records: dict[str, dict[str, Any]],
    union: UnionFind,
    prefix: str,
    local_column: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    globals_: list[dict[str, Any]] = []
    crosswalk: list[dict[str, Any]] = []
    source_to_global: dict[str, str] = {}
    for members in components(union):
        items = [records[item] for item in members]
        global_id = stable_id(prefix, *members)
        aliases = sorted(
            {
                str(alias)
                for item in items
                for alias in [
                    item.get("display_name", ""),
                    *json_list(item.get("aliases_json", "[]")),
                ]
                if str(alias)
            }
        )
        displays = sorted(
            (
                str(item.get("display_name", ""))
                for item in items
                if item.get("display_name")
            ),
            key=lambda value: (-len(value), value.casefold()),
        )
        globals_.append(
            {
                f"global_{prefix}_id": global_id,
                "display_name": displays[0] if displays else "",
                "aliases_json": json_text(aliases),
                "source_count": len({item["source"] for item in items}),
                "source_entity_count": len(items),
                "identity_status": "reviewed_cross_source"
                if len({item["source"] for item in items}) > 1
                else "source_local_identity",
            }
        )
        for item in items:
            source_id = str(item[f"source_{prefix}_id"])
            if source_id in source_to_global:
                raise PipelineError(
                    f"commerce input contract: duplicate source {prefix} crosswalk endpoint"
                )
            source_to_global[source_id] = global_id
            crosswalk.append(
                {
                    f"global_{prefix}_id": global_id,
                    f"source_{prefix}_id": source_id,
                    "source": item["source"],
                    local_column: item[f"source_local_{prefix}_id"],
                    "display_name": item.get("display_name", ""),
                    "identity_status": item.get("identity_status", ""),
                    "source_details_json": json_text(item),
                }
            )
    return (
        sorted(globals_, key=lambda row: row[f"global_{prefix}_id"]),
        sorted(crosswalk, key=lambda row: row[f"source_{prefix}_id"]),
        source_to_global,
    )


def _decorate(
    rows: Iterable[dict[str, Any]],
    operator_map: dict[str, str],
    offering_map: dict[str, str],
) -> list[dict[str, Any]]:
    result = []
    for source in rows:
        row = dict(source)
        row["global_operator_id"] = operator_map.get(
            str(row.get("source_operator_id", "")), ""
        )
        row["global_offering_id"] = offering_map.get(
            str(row.get("source_offering_id", "")), ""
        )
        result.append(row)
    return result


def validate_output(rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Validate baseline/reviewed commerce global foreign keys and summarize it."""
    required = {
        "global_operators",
        "global_offerings",
        "operator_crosswalk",
        "offering_crosswalk",
    }
    if not required <= rows.keys():
        raise PipelineError(
            f"commerce output contract: missing tables {sorted(required - rows.keys())}"
        )
    operator_values = [
        str(row.get("global_operator_id", "")) for row in rows["global_operators"]
    ]
    offering_values = [
        str(row.get("global_offering_id", "")) for row in rows["global_offerings"]
    ]
    operator_ids, offering_ids = set(operator_values), set(offering_values)
    if "" in operator_ids or len(operator_values) != len(operator_ids):
        raise PipelineError(
            "commerce output contract: missing or duplicate global operator ID"
        )
    if "" in offering_ids or len(offering_values) != len(offering_ids):
        raise PipelineError(
            "commerce output contract: missing or duplicate global offering ID"
        )
    for table, values in rows.items():
        if not isinstance(values, list):
            raise PipelineError(
                f"commerce output contract: table {table} is not a row list"
            )
        for row in values:
            if (
                row.get("global_operator_id")
                and row["global_operator_id"] not in operator_ids
            ):
                raise PipelineError(
                    f"commerce output contract: broken global operator FK in {table}"
                )
            if (
                row.get("global_offering_id")
                and row["global_offering_id"] not in offering_ids
            ):
                raise PipelineError(
                    f"commerce output contract: broken global offering FK in {table}"
                )
    return {
        "status": "passed",
        "global_operator_count": len(operator_ids),
        "global_offering_count": len(offering_ids),
        "operator_cross_source_unions": len(rows["operator_crosswalk"])
        - len(operator_ids),
        "offering_cross_source_unions": len(rows["offering_crosswalk"])
        - len(offering_ids),
    }


def build_tables(
    source_tables: dict[str, dict[str, list[dict]]],
    reviews: dict[str, Any],
    raw_inputs: dict[str, dict],
    geography: Any,
    people_tables: dict[str, list[dict]],
) -> dict[str, list[dict]]:
    """Build baseline commerce solely from injected normalized, review, and raw inputs."""
    del geography
    runtime = review_payload(reviews, "cross_source_offerings/runtime.json")
    if not isinstance(runtime, dict):
        raise PipelineError("commerce input contract: invalid runtime review payload")
    source_files = _validate_runtime_pins(
        runtime, source_tables, raw_inputs, people_tables
    )
    bundle = load_sources(source_tables, raw_inputs, people_tables)
    reviewed = _load_reviews(reviews, runtime, bundle, raw_inputs)
    operator_union, operator_decisions = _apply_reviewed_unions(
        bundle.operators, reviewed, entity_kind="operator"
    )
    offering_union, offering_decisions = _apply_reviewed_unions(
        bundle.offerings, reviewed, entity_kind="offering"
    )
    _validate_source_local_identity_preserved(bundle.operators, operator_union)
    _validate_source_local_identity_preserved(bundle.offerings, offering_union)
    global_operators, operator_crosswalk, operator_map = _registry_rows(
        bundle.operators,
        operator_union,
        "operator",
        "source_local_operator_id",
    )
    global_offerings, offering_crosswalk, offering_map = _registry_rows(
        bundle.offerings,
        offering_union,
        "offering",
        "source_local_offering_id",
    )
    decisions = sorted(
        operator_decisions + offering_decisions,
        key=lambda row: row["review_id"],
    )
    measures = [
        {
            "measure": "K05_source_supported_operators",
            "value": len(global_operators),
            "scope": "AtLocal, Cultural Map and iCommunity source-local operator identities after reviewed cross-source links",
            "status": "demonstration",
        },
        {
            "measure": "K07_source_reported_offerings",
            "value": len(global_offerings),
            "scope": "AtLocal, Cultural Map and iCommunity source-local offering identities after reviewed cross-source links",
            "status": "demonstration",
        },
    ]
    output: dict[str, list[dict[str, Any]]] = {
        "global_operators": global_operators,
        "global_offerings": global_offerings,
        "operator_crosswalk": operator_crosswalk,
        "offering_crosswalk": offering_crosswalk,
        "listing_evidence": _decorate(
            bundle.listing_evidence, operator_map, offering_map
        ),
        "seller_evidence": _decorate(
            bundle.seller_evidence, operator_map, offering_map
        ),
        "operator_offering_edges": _decorate(
            bundle.operator_offering_edges, operator_map, offering_map
        ),
        "locations": _decorate(bundle.locations, operator_map, offering_map),
        "prices": _decorate(bundle.prices, operator_map, offering_map),
        "media": _decorate(bundle.media, operator_map, offering_map),
        "channels": _decorate(bundle.channels, operator_map, offering_map),
        "person_operator_links": _decorate(
            bundle.person_operator_links, operator_map, offering_map
        ),
        "source_local_boundaries": _decorate(
            bundle.source_local_boundaries, operator_map, offering_map
        ),
        "identity_decisions": decisions,
        "candidate_pairs": [
            {key: row[key] for key in TABLE_COLUMNS["candidate_pairs"]}
            for row in decisions
        ],
        "measure_results": measures,
        "measure_contributions": [
            {
                "measure": "K05_source_supported_operators",
                "entity_id": row["global_operator_id"],
            }
            for row in global_operators
        ]
        + [
            {
                "measure": "K07_source_reported_offerings",
                "entity_id": row["global_offering_id"],
            }
            for row in global_offerings
        ],
        "source_files": source_files,
    }
    projected = {
        name: [
            {column: row.get(column, "") for column in columns} for row in output[name]
        ]
        for name, columns in TABLE_COLUMNS.items()
    }
    validate_output(projected)
    return projected

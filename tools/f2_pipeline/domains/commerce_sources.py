"""Adapt source-local AtLocal, Cultural Map, and iCommunity commerce tables.

The adapters preserve source-local identity and evidence grains.  They perform no
identity discovery and resolve every raw locator only through injected capture
bundles.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..common import PipelineError
from .raw_inputs import resolve_evidence
from .resolution import evidence_locator, json_list, source_tables_for

SOURCE_ORDER = ("atlocal", "cultural_map", "icommunity")


@dataclass
class OfferingSources:
    operators: dict[str, dict[str, Any]]
    offerings: dict[str, dict[str, Any]]
    listing_evidence: list[dict[str, Any]]
    seller_evidence: list[dict[str, Any]]
    operator_offering_edges: list[dict[str, Any]]
    locations: list[dict[str, Any]]
    prices: list[dict[str, Any]]
    media: list[dict[str, Any]]
    channels: list[dict[str, Any]]
    person_operator_links: list[dict[str, Any]]
    source_local_boundaries: list[dict[str, Any]]
    canonical_source_ids: dict[str, str]


def namespaced(source: str, local_id: Any) -> str:
    value = str(local_id or "")
    return f"{source}:{value}" if value else ""


def _source_details(row: dict[str, Any], excluded: set[str]) -> str:
    return json.dumps(
        {key: value for key, value in row.items() if key not in excluded},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class _Builder:
    def __init__(
        self,
        source_tables: dict[str, dict[str, list[dict]]],
        raw_inputs: dict[str, dict],
        people_tables: dict[str, list[dict]],
    ) -> None:
        self.source_tables = source_tables
        self.raw_inputs = raw_inputs
        self.operators: dict[str, dict[str, Any]] = {}
        self.offerings: dict[str, dict[str, Any]] = {}
        self.listing_evidence: list[dict[str, Any]] = []
        self.seller_evidence: list[dict[str, Any]] = []
        self.operator_offering_edges: list[dict[str, Any]] = []
        self.locations: list[dict[str, Any]] = []
        self.prices: list[dict[str, Any]] = []
        self.media: list[dict[str, Any]] = []
        self.channels: list[dict[str, Any]] = []
        self.person_operator_links: list[dict[str, Any]] = []
        self.source_local_boundaries: list[dict[str, Any]] = []
        self.tables: dict[str, dict[str, list[dict]]] = {}
        self.canonical_source_ids: dict[str, str] = {}
        self.observations: dict[str, dict[str, dict[str, Any]]] = {}
        self._checked_locators: set[str] = set()
        crosswalk = people_tables.get("person_crosswalk")
        if not isinstance(crosswalk, list):
            raise PipelineError(
                "commerce input contract: missing fresh people person_crosswalk"
            )
        self.person_crosswalk: dict[str, str] = {}
        for row in crosswalk:
            source_entity_id = str(row.get("source_entity_id", ""))
            global_person_id = str(row.get("global_person_id", ""))
            if (
                not source_entity_id
                or not global_person_id
                or source_entity_id in self.person_crosswalk
            ):
                raise PipelineError(
                    "commerce input contract: people crosswalk has missing or duplicate source identity"
                )
            self.person_crosswalk[source_entity_id] = global_person_id

        for source in SOURCE_ORDER:
            canonical, tables = source_tables_for(source_tables, source)
            raw_input = raw_inputs.get(canonical)
            if not isinstance(raw_input, dict):
                raise PipelineError(
                    f"commerce input contract: missing raw_inputs for {canonical}"
                )
            self.tables[source] = tables
            self.canonical_source_ids[source] = canonical
            rows = self.table(source, "source_observations")
            index = {str(row.get("observation_id", "")): row for row in rows}
            if "" in index or len(index) != len(rows):
                raise PipelineError(
                    f"commerce input contract: {source} source_observations has missing or duplicate observation_id"
                )
            self.observations[source] = index

    def table(self, source: str, name: str) -> list[dict]:
        rows = self.tables.get(source, {}).get(name)
        if not isinstance(rows, list):
            raise PipelineError(
                f"commerce input contract: missing {source} source table {name}"
            )
        return rows

    def locator(self, source: str, observation_id: Any) -> str:
        oid = str(observation_id or "")
        observation = self.observations[source].get(oid)
        if observation is None:
            raise PipelineError(
                f"commerce input contract: missing {source} observation {oid}"
            )
        canonical = self.canonical_source_ids[source]
        raw_input = self.raw_inputs[canonical]
        locator = evidence_locator(raw_input, observation)
        if locator not in self._checked_locators:
            resolve_evidence(self.raw_inputs, locator)
            self._checked_locators.add(locator)
        return locator

    def raw_source_id(self, source: str, observation_id: Any) -> str:
        return str(
            self.observations[source]
            .get(str(observation_id or ""), {})
            .get("source_id", "")
        )

    def source_key(self, source: str, observation_id: Any) -> str:
        return str(
            self.observations[source]
            .get(str(observation_id or ""), {})
            .get("source_key", "")
        )

    def add_operator(self, row: dict[str, Any]) -> None:
        identifier = str(row["source_operator_id"])
        if not identifier or identifier in self.operators:
            raise PipelineError(
                f"commerce input contract: missing or duplicate source operator {identifier}"
            )
        self.operators[identifier] = row

    def add_offering(self, row: dict[str, Any]) -> None:
        identifier = str(row["source_offering_id"])
        if not identifier or identifier in self.offerings:
            raise PipelineError(
                f"commerce input contract: missing or duplicate source offering {identifier}"
            )
        self.offerings[identifier] = row

    def finish(self) -> OfferingSources:
        self._validate_unique_ids()
        self._validate_foreign_keys()
        self._validate_locators()
        return OfferingSources(
            operators=dict(sorted(self.operators.items())),
            offerings=dict(sorted(self.offerings.items())),
            listing_evidence=sorted(
                self.listing_evidence, key=lambda row: str(row["source_listing_id"])
            ),
            seller_evidence=sorted(
                self.seller_evidence,
                key=lambda row: str(row["source_seller_evidence_id"]),
            ),
            operator_offering_edges=sorted(
                self.operator_offering_edges,
                key=lambda row: str(row["source_operator_offering_edge_id"]),
            ),
            locations=sorted(
                self.locations, key=lambda row: str(row["source_location_id"])
            ),
            prices=sorted(self.prices, key=lambda row: str(row["source_price_id"])),
            media=sorted(self.media, key=lambda row: str(row["source_media_id"])),
            channels=sorted(
                self.channels, key=lambda row: str(row["source_channel_id"])
            ),
            person_operator_links=sorted(
                self.person_operator_links,
                key=lambda row: str(row["source_person_operator_link_id"]),
            ),
            source_local_boundaries=sorted(
                self.source_local_boundaries,
                key=lambda row: str(row["source_boundary_id"]),
            ),
            canonical_source_ids=dict(self.canonical_source_ids),
        )

    def _validate_unique_ids(self) -> None:
        for label, rows, key in (
            ("listing evidence", self.listing_evidence, "source_listing_id"),
            ("seller evidence", self.seller_evidence, "source_seller_evidence_id"),
            (
                "operator offering edges",
                self.operator_offering_edges,
                "source_operator_offering_edge_id",
            ),
            ("locations", self.locations, "source_location_id"),
            ("prices", self.prices, "source_price_id"),
            ("media", self.media, "source_media_id"),
            ("channels", self.channels, "source_channel_id"),
            (
                "person operator links",
                self.person_operator_links,
                "source_person_operator_link_id",
            ),
            ("source boundaries", self.source_local_boundaries, "source_boundary_id"),
        ):
            values = [str(row.get(key, "")) for row in rows]
            if "" in values or len(values) != len(set(values)):
                raise PipelineError(
                    f"commerce input contract: missing or duplicate {label} IDs"
                )

    def _validate_foreign_keys(self) -> None:
        listing_ids = {str(row["source_listing_id"]) for row in self.listing_evidence}
        for row in self.listing_evidence:
            self._check_fk(row, "source_offering_id", self.offerings)
            self._check_fk(row, "source_operator_id", self.operators)
        for rows, fields in (
            (self.seller_evidence, ("source_operator_id", "source_offering_id")),
            (
                self.operator_offering_edges,
                ("source_operator_id", "source_offering_id"),
            ),
            (self.person_operator_links, ("source_operator_id",)),
        ):
            for row in rows:
                for field in fields:
                    targets = (
                        self.operators
                        if field == "source_operator_id"
                        else self.offerings
                    )
                    self._check_fk(row, field, targets)
        for row in self.locations:
            entity_id = str(row.get("source_entity_id", ""))
            offering_id = str(row.get("source_offering_id", ""))
            operator_id = str(row.get("source_operator_id", ""))
            if entity_id not in self.offerings and entity_id not in self.operators:
                raise PipelineError(
                    f"commerce input contract: location has missing source entity {entity_id}"
                )
            if (offering_id == entity_id) == (operator_id == entity_id):
                raise PipelineError(
                    "commerce input contract: location must have exactly one role-specific source entity"
                )
            self._check_fk(row, "source_offering_id", self.offerings)
            self._check_fk(row, "source_operator_id", self.operators)
        for rows in (self.prices, self.media, self.channels):
            for row in rows:
                self._check_fk(row, "source_offering_id", self.offerings)
                listing_id = str(row.get("source_listing_id", ""))
                if listing_id and listing_id not in listing_ids:
                    raise PipelineError(
                        f"commerce input contract: detail has missing listing evidence {listing_id}"
                    )

    @staticmethod
    def _check_fk(
        row: dict[str, Any], field: str, targets: dict[str, dict[str, Any]]
    ) -> None:
        value = str(row.get(field, ""))
        if value and value not in targets:
            raise PipelineError(
                f"commerce input contract: {field} has missing target {value}"
            )

    def _validate_locators(self) -> None:
        for rows in (
            self.listing_evidence,
            self.seller_evidence,
            self.operator_offering_edges,
            self.locations,
            self.prices,
            self.media,
            self.channels,
            self.person_operator_links,
        ):
            for row in rows:
                locator = str(row.get("raw_locator", ""))
                if not locator:
                    raise PipelineError(
                        f"commerce input contract: evidence row has no raw locator {row}"
                    )
                if locator not in self._checked_locators:
                    resolve_evidence(self.raw_inputs, locator)
                    self._checked_locators.add(locator)
        for row in self.person_operator_links:
            if not row["global_person_id"]:
                raise PipelineError(
                    "commerce input contract: explicit source person/operator link is missing from the fresh people crosswalk: "
                    f"{row['source_person_operator_link_id']}"
                )


def _load_atlocal(builder: _Builder) -> None:
    source = "atlocal"
    pilot = "atlocal-v1"
    products = builder.table(source, "products")
    sellers = builder.table(source, "sellers")
    listings = builder.table(source, "listing_observations")
    seller_evidence = builder.table(source, "seller_evidence")
    edges = builder.table(source, "product_sellers")
    locations = builder.table(source, "locations")
    prices = builder.table(source, "product_prices")
    images = builder.table(source, "images")
    channels = builder.table(source, "listing_channels")
    person_sellers = builder.table(source, "person_sellers")
    identity_decisions = builder.table(source, "identity_decisions")
    review_cases = builder.table(source, "review_cases")

    for row in products:
        local_id = str(row.get("product_id", ""))
        builder.add_offering(
            {
                "source_offering_id": namespaced(source, local_id),
                "source": source,
                "source_local_offering_id": local_id,
                "display_name": row.get("name", ""),
                "aliases_json": row.get("aliases_json", "[]"),
                "source_keys_json": row.get("source_keys_json", "[]"),
                "identity_status": row.get("identity_status", ""),
                "name_quality": row.get("name_quality", ""),
            }
        )
    for row in sellers:
        local_id = str(row.get("seller_id", ""))
        builder.add_operator(
            {
                "source_operator_id": namespaced(source, local_id),
                "source": source,
                "source_local_operator_id": local_id,
                "display_name": row.get("name", ""),
                "identity_status": row.get("identity_status", ""),
                "name_quality": row.get("name_quality", ""),
                "province": row.get("province", ""),
                "district": row.get("district", ""),
                "province_code": row.get("province_code", ""),
                "district_code": row.get("district_code", ""),
            }
        )
    listing_by_observation: dict[str, dict[str, Any]] = {}
    for row in listings:
        oid = str(row.get("observation_id", ""))
        evidence = {
            "source_listing_id": namespaced(source, row.get("listing_id", "")),
            "source": source,
            "source_local_listing_id": row.get("listing_id", ""),
            "source_offering_id": namespaced(source, row.get("product_id", "")),
            "source_operator_id": namespaced(source, row.get("seller_id", "")),
            "observation_id": oid,
            "source_key": row.get("source_key", ""),
            "raw_source_id": builder.raw_source_id(source, oid),
            "raw_locator": builder.locator(source, oid),
            "title_raw": row.get("name_raw", ""),
            "title_normalized": row.get("name_normalized", ""),
            "description": row.get("description", ""),
            "category_raw": row.get("category_raw", ""),
            "source_url": row.get("source_url", ""),
            "listing_eligibility": row.get("product_eligibility", ""),
            "source_details_json": _source_details(
                row,
                {
                    "listing_id",
                    "product_id",
                    "seller_id",
                    "observation_id",
                    "source_key",
                    "name_raw",
                    "name_normalized",
                    "description",
                    "category_raw",
                    "source_url",
                    "product_eligibility",
                },
            ),
        }
        builder.listing_evidence.append(evidence)
        if oid in listing_by_observation:
            raise PipelineError(
                "commerce input contract: AtLocal listing observation is duplicated"
            )
        listing_by_observation[oid] = evidence
    for row in seller_evidence:
        oid = str(row.get("observation_id", ""))
        listing = listing_by_observation.get(oid, {})
        builder.seller_evidence.append(
            {
                "source_seller_evidence_id": namespaced(
                    source,
                    f"seller_evidence:{row.get('seller_id', '')}:{oid}",
                ),
                "source": source,
                "source_operator_id": namespaced(source, row.get("seller_id", "")),
                "source_offering_id": listing.get("source_offering_id", ""),
                "source_listing_id": listing.get("source_listing_id", ""),
                "observation_id": oid,
                "source_key": row.get("source_key", ""),
                "raw_locator": builder.locator(source, oid),
                "role": "source_reported_operator",
                "evidence_text": row.get("evidence", ""),
                "basis": row.get("basis", ""),
                "source_details_json": json.dumps(
                    row, ensure_ascii=False, sort_keys=True
                ),
            }
        )
    for row in edges:
        oid = str(row.get("observation_id", ""))
        builder.operator_offering_edges.append(
            {
                "source_operator_offering_edge_id": namespaced(
                    source,
                    f"product_seller:{row.get('product_id', '')}:{row.get('seller_id', '')}:{oid}",
                ),
                "source": source,
                "source_offering_id": namespaced(source, row.get("product_id", "")),
                "source_operator_id": namespaced(source, row.get("seller_id", "")),
                "source_listing_id": listing_by_observation.get(oid, {}).get(
                    "source_listing_id", ""
                ),
                "observation_id": oid,
                "source_key": builder.source_key(source, oid),
                "raw_locator": builder.locator(source, oid),
                "relationship": row.get("relationship", ""),
                "evidence_text": "",
                "source_details_json": json.dumps(
                    row, ensure_ascii=False, sort_keys=True
                ),
            }
        )
    for row in locations:
        entity_id = namespaced(source, row.get("entity_id", ""))
        is_offering, is_operator = (
            entity_id in builder.offerings,
            entity_id in builder.operators,
        )
        if not is_offering and not is_operator:
            continue
        if is_offering and is_operator:
            raise PipelineError(
                "commerce input contract: AtLocal location entity is ambiguous across roles"
            )
        oid = str(row.get("observation_id", ""))
        builder.locations.append(
            {
                "source_location_id": namespaced(source, row.get("location_id", "")),
                "source": source,
                "source_entity_id": entity_id,
                "source_offering_id": entity_id if is_offering else "",
                "source_operator_id": entity_id if is_operator else "",
                "observation_id": oid,
                "source_key": row.get("source_key", ""),
                "raw_locator": builder.locator(source, oid),
                "location_role": row.get("location_role", ""),
                "province_raw": row.get("province_raw", ""),
                "district_raw": row.get("district_raw", ""),
                "province_normalized": row.get("province_normalized", ""),
                "province_code": row.get("province_code", ""),
                "district_normalized": row.get("district_normalized", ""),
                "district_code": row.get("district_code", ""),
                "subdistrict_normalized": row.get("subdistrict_normalized", ""),
                "subdistrict_code": row.get("subdistrict_code", ""),
                "status": row.get("status", ""),
                "source_details_json": _source_details(
                    row,
                    {
                        "location_id",
                        "entity_id",
                        "observation_id",
                        "source_key",
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
                    },
                ),
            }
        )
    for row in prices:
        oid = str(row.get("observation_id", ""))
        listing = listing_by_observation.get(oid)
        if listing is None:
            raise PipelineError("commerce input contract: AtLocal price lacks listing")
        builder.prices.append(
            {
                "source_price_id": namespaced(source, f"price:{oid}"),
                "source": source,
                "source_listing_id": listing["source_listing_id"],
                "source_offering_id": namespaced(source, row.get("product_id", "")),
                "observation_id": oid,
                "source_key": row.get("source_key", ""),
                "raw_locator": builder.locator(source, oid),
                "price_text_raw": row.get("amount_raw", ""),
                "amounts_json": json.dumps(
                    [row.get("amount_thb")]
                    if row.get("amount_thb") not in (None, "")
                    else [],
                    ensure_ascii=False,
                ),
                "currency": row.get("currency", ""),
                "parse_status": row.get("interpretation", ""),
                "source_details_json": json.dumps(
                    row, ensure_ascii=False, sort_keys=True
                ),
            }
        )
    for row in images:
        oid = str(row.get("observation_id", ""))
        listing = listing_by_observation.get(oid)
        if listing is None:
            raise PipelineError("commerce input contract: AtLocal media lacks listing")
        builder.media.append(
            {
                "source_media_id": namespaced(source, row.get("image_id", "")),
                "source": source,
                "source_listing_id": listing["source_listing_id"],
                "source_offering_id": namespaced(source, row.get("product_id", "")),
                "observation_id": oid,
                "source_key": row.get("source_key", ""),
                "raw_locator": builder.locator(source, oid),
                "media_kind": "image",
                "ordinal": "",
                "url_or_value": row.get("image_url", ""),
                "label": "",
                "status": row.get("status", ""),
                "source_details_json": json.dumps(
                    row, ensure_ascii=False, sort_keys=True
                ),
            }
        )
    for row in channels:
        oid = str(row.get("observation_id", ""))
        listing = listing_by_observation.get(oid)
        if listing is None:
            raise PipelineError(
                "commerce input contract: AtLocal channel lacks listing"
            )
        builder.channels.append(
            {
                "source_channel_id": namespaced(source, f"channel:{oid}"),
                "source": source,
                "source_listing_id": listing["source_listing_id"],
                "source_offering_id": namespaced(source, row.get("product_id", "")),
                "observation_id": oid,
                "source_key": row.get("source_key", ""),
                "raw_locator": builder.locator(source, oid),
                "channel": row.get("channel", ""),
                "platform_shop_id": row.get("platform_shop_id", ""),
                "channel_evidence": row.get("sale_channel_json", ""),
                "source_details_json": _source_details(
                    row,
                    {
                        "observation_id",
                        "product_id",
                        "source_key",
                        "channel",
                        "platform_shop_id",
                        "sale_channel_json",
                    },
                ),
            }
        )
    people = {str(row.get("person_id", "")) for row in builder.table(source, "people")}
    for row in person_sellers:
        person_id = str(row.get("person_id", ""))
        if person_id not in people:
            raise PipelineError(
                "commerce input contract: AtLocal person/operator link has missing person"
            )
        oid = str(row.get("observation_id", ""))
        source_person_id = namespaced(source, person_id)
        builder.person_operator_links.append(
            {
                "source_person_operator_link_id": namespaced(
                    source,
                    f"person_seller:{person_id}:{row.get('seller_id', '')}:{oid}",
                ),
                "source": source,
                "source_person_id": source_person_id,
                "global_person_id": builder.person_crosswalk.get(source_person_id, ""),
                "source_operator_id": namespaced(source, row.get("seller_id", "")),
                "observation_id": oid,
                "source_key": builder.source_key(source, oid),
                "raw_locator": builder.locator(source, oid),
                "relationship": row.get("relationship", ""),
                "evidence_text": "",
                "source_details_json": json.dumps(
                    row, ensure_ascii=False, sort_keys=True
                ),
            }
        )
    listing_by_key = {
        str(row["source_key"]): row
        for row in builder.listing_evidence
        if row["source"] == source
    }
    for row in identity_decisions:
        source_keys = [
            str(value) for value in json_list(row.get("evidence_observation_ids_json"))
        ]
        endpoint_entities = sorted(
            {
                entity_id
                for source_key in (
                    str(row.get("left_source_key", "")),
                    str(row.get("right_source_key", "")),
                )
                for entity_id in (
                    listing_by_key.get(source_key, {}).get("source_offering_id", ""),
                    listing_by_key.get(source_key, {}).get("source_operator_id", ""),
                )
                if entity_id
            }
        )
        builder.source_local_boundaries.append(
            {
                "source_boundary_id": namespaced(source, row.get("decision_id", "")),
                "source": source,
                "boundary_kind": "source_identity_decision",
                "status": row.get("outcome", ""),
                "reason": row.get("rule", ""),
                "source_keys_json": json.dumps(
                    [row.get("left_source_key", ""), row.get("right_source_key", "")],
                    ensure_ascii=False,
                ),
                "observation_ids_json": json.dumps(source_keys, ensure_ascii=False),
                "source_entity_ids_json": json.dumps(
                    endpoint_entities, ensure_ascii=False
                ),
                "source_locator": f"normalized://source_local/{pilot}/identity_decisions.csv#decision_id={row.get('decision_id', '')}",
            }
        )
    relevant_kinds = {
        "marketplace_operator_unresolved",
        "unnamed_offering",
        "ambiguous_cross_table_product",
        "same_seller_title_multiple_offerings",
        "accepted_unresolved_offering_group",
        "seller_alias_unresolved",
        "offering_after_operator_merge",
        "unnamed_map_possible_recovery",
        "code_only_operator_identity",
    }
    for row in review_cases:
        if row.get("kind") not in relevant_kinds:
            continue
        source_keys = [str(value) for value in json_list(row.get("source_keys_json"))]
        linked = [listing_by_key[key] for key in source_keys if key in listing_by_key]
        entities = sorted(
            {
                item["source_offering_id"]
                for item in linked
                if item["source_offering_id"]
            }
            | {
                item["source_operator_id"]
                for item in linked
                if item["source_operator_id"]
            }
        )
        builder.source_local_boundaries.append(
            {
                "source_boundary_id": namespaced(source, row.get("review_id", "")),
                "source": source,
                "boundary_kind": f"source_review_case:{row.get('kind', '')}",
                "status": row.get("status", ""),
                "reason": row.get("reason", ""),
                "source_keys_json": row.get("source_keys_json", "[]"),
                "observation_ids_json": "[]",
                "source_entity_ids_json": json.dumps(entities, ensure_ascii=False),
                "source_locator": f"normalized://source_local/{pilot}/review_cases.csv#review_id={row.get('review_id', '')}",
            }
        )


def _load_cultural_map(builder: _Builder) -> None:
    source = "cultural_map"
    pilot = "cultural-map-v1"
    offerings = builder.table(source, "offerings")
    sellers = builder.table(source, "sellers")
    listings = builder.table(source, "offering_listing_observations")
    seller_evidence = builder.table(source, "seller_evidence")
    edges = builder.table(source, "product_sellers")
    locations = builder.table(source, "offering_locations")
    prices = builder.table(source, "offering_prices")
    media = builder.table(source, "offering_media")
    person_evidence = builder.table(source, "person_role_evidence")
    identity_decisions = builder.table(source, "identity_decisions")
    review_cases = builder.table(source, "review_cases")

    for row in offerings:
        local_id = str(row.get("offering_id", ""))
        builder.add_offering(
            {
                "source_offering_id": namespaced(source, local_id),
                "source": source,
                "source_local_offering_id": local_id,
                "display_name": row.get("display_title", ""),
                "aliases_json": row.get("aliases_json", "[]"),
                "source_keys_json": row.get("source_keys_json", "[]"),
                "identity_status": row.get("identity_status", ""),
                "cultural_scope_eligibility": row.get("cultural_scope_eligibility", ""),
                "generic_name_flag": row.get("generic_name_flag", ""),
            }
        )
    for row in sellers:
        local_id = str(row.get("seller_id", ""))
        builder.add_operator(
            {
                "source_operator_id": namespaced(source, local_id),
                "source": source,
                "source_local_operator_id": local_id,
                "display_name": row.get("name", ""),
                "identity_status": row.get("identity_status", ""),
                "source_scope": row.get("source_scope", ""),
                "current_status": row.get("current_status", ""),
            }
        )
    listing_by_observation: dict[str, dict[str, Any]] = {}
    for row in listings:
        oid = str(row.get("observation_id", ""))
        evidence = {
            "source_listing_id": namespaced(source, row.get("listing_id", "")),
            "source": source,
            "source_local_listing_id": row.get("listing_id", ""),
            "source_offering_id": namespaced(source, row.get("offering_id", "")),
            "source_operator_id": namespaced(source, row.get("seller_id", "")),
            "observation_id": oid,
            "source_key": row.get("source_key", ""),
            "raw_source_id": builder.raw_source_id(source, oid),
            "raw_locator": builder.locator(source, oid),
            "title_raw": row.get("title_raw", ""),
            "title_normalized": row.get("title_normalized", ""),
            "description": row.get("description", ""),
            "category_raw": row.get("product_category_raw", ""),
            "source_url": row.get("source_url", ""),
            "listing_eligibility": "source_reported_offering",
            "source_details_json": _source_details(
                row,
                {
                    "listing_id",
                    "offering_id",
                    "seller_id",
                    "observation_id",
                    "source_key",
                    "title_raw",
                    "title_normalized",
                    "description",
                    "product_category_raw",
                    "source_url",
                },
            ),
        }
        builder.listing_evidence.append(evidence)
        if oid in listing_by_observation:
            raise PipelineError(
                "commerce input contract: Cultural Map listing observation is duplicated"
            )
        listing_by_observation[oid] = evidence
        builder.channels.append(
            {
                "source_channel_id": namespaced(
                    source, f"channel:{row.get('listing_id', '')}"
                ),
                "source": source,
                "source_listing_id": evidence["source_listing_id"],
                "source_offering_id": evidence["source_offering_id"],
                "observation_id": oid,
                "source_key": row.get("source_key", ""),
                "raw_locator": evidence["raw_locator"],
                "channel": "cultural_map_sales_fields",
                "platform_shop_id": "",
                "channel_evidence": row.get("sales_channels_raw", ""),
                "source_details_json": json.dumps(
                    {
                        "sales_accounts_json": row.get("sales_accounts_json", "[]"),
                        "external_links_json": row.get("external_links_json", "[]"),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            }
        )
    for row in seller_evidence:
        oid = str(row.get("observation_id", ""))
        listing = listing_by_observation.get(oid)
        if listing is None:
            raise PipelineError(
                "commerce input contract: Cultural Map seller evidence lacks listing"
            )
        builder.seller_evidence.append(
            {
                "source_seller_evidence_id": namespaced(
                    source, row.get("evidence_id", "")
                ),
                "source": source,
                "source_operator_id": namespaced(source, row.get("seller_id", "")),
                "source_offering_id": namespaced(source, row.get("offering_id", "")),
                "source_listing_id": listing["source_listing_id"],
                "observation_id": oid,
                "source_key": row.get("source_key", ""),
                "raw_locator": builder.locator(source, oid),
                "role": row.get("role", ""),
                "evidence_text": row.get("evidence_passage", ""),
                "basis": row.get("basis", ""),
                "source_details_json": json.dumps(
                    row, ensure_ascii=False, sort_keys=True
                ),
            }
        )
    for row in edges:
        oid = str(row.get("observation_id", ""))
        listing = listing_by_observation.get(oid)
        if listing is None:
            raise PipelineError(
                "commerce input contract: Cultural Map operator edge lacks listing"
            )
        builder.operator_offering_edges.append(
            {
                "source_operator_offering_edge_id": namespaced(
                    source, row.get("relationship_id", "")
                ),
                "source": source,
                "source_offering_id": namespaced(source, row.get("offering_id", "")),
                "source_operator_id": namespaced(source, row.get("seller_id", "")),
                "source_listing_id": listing["source_listing_id"],
                "observation_id": oid,
                "source_key": row.get("source_key", ""),
                "raw_locator": builder.locator(source, oid),
                "relationship": row.get("relationship", ""),
                "evidence_text": row.get("evidence_passage", ""),
                "source_details_json": json.dumps(
                    row, ensure_ascii=False, sort_keys=True
                ),
            }
        )
    for row in locations:
        oid = str(row.get("observation_id", ""))
        offering_id = namespaced(source, row.get("offering_id", ""))
        builder.locations.append(
            {
                "source_location_id": namespaced(source, row.get("location_id", "")),
                "source": source,
                "source_entity_id": offering_id,
                "source_offering_id": offering_id,
                "source_operator_id": "",
                "observation_id": oid,
                "source_key": row.get("source_key", ""),
                "raw_locator": builder.locator(source, oid),
                "location_role": row.get("location_role", ""),
                "province_raw": row.get("province_raw", ""),
                "district_raw": row.get("district_raw", ""),
                "province_normalized": row.get("province_normalized", ""),
                "province_code": row.get("province_code", ""),
                "district_normalized": row.get("district_normalized", ""),
                "district_code": row.get("district_code", ""),
                "subdistrict_normalized": row.get("subdistrict_normalized", ""),
                "subdistrict_code": row.get("subdistrict_code", ""),
                "status": row.get("status", ""),
                "source_details_json": _source_details(
                    row,
                    {
                        "location_id",
                        "offering_id",
                        "observation_id",
                        "source_key",
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
                    },
                ),
            }
        )
    for row in prices:
        oid = str(row.get("observation_id", ""))
        listing = listing_by_observation.get(oid)
        if listing is None:
            raise PipelineError(
                "commerce input contract: Cultural Map price lacks listing"
            )
        builder.prices.append(
            {
                "source_price_id": namespaced(source, row.get("price_id", "")),
                "source": source,
                "source_listing_id": listing["source_listing_id"],
                "source_offering_id": namespaced(source, row.get("offering_id", "")),
                "observation_id": oid,
                "source_key": row.get("source_key", ""),
                "raw_locator": builder.locator(source, oid),
                "price_text_raw": row.get("price_text_raw", ""),
                "amounts_json": row.get("amounts_json", "[]"),
                "currency": row.get("currency", ""),
                "parse_status": row.get("parse_status", ""),
                "source_details_json": _source_details(
                    row,
                    {
                        "price_id",
                        "offering_id",
                        "observation_id",
                        "source_key",
                        "price_text_raw",
                        "amounts_json",
                        "currency",
                        "parse_status",
                    },
                ),
            }
        )
    for row in media:
        oid = str(row.get("observation_id", ""))
        listing = listing_by_observation.get(oid)
        if listing is None:
            raise PipelineError(
                "commerce input contract: Cultural Map media lacks listing"
            )
        builder.media.append(
            {
                "source_media_id": namespaced(source, row.get("media_id", "")),
                "source": source,
                "source_listing_id": listing["source_listing_id"],
                "source_offering_id": namespaced(source, row.get("offering_id", "")),
                "observation_id": oid,
                "source_key": row.get("source_key", ""),
                "raw_locator": builder.locator(source, oid),
                "media_kind": row.get("media_kind", ""),
                "ordinal": row.get("ordinal", ""),
                "url_or_value": row.get("url_or_value", ""),
                "label": row.get("label", ""),
                "status": row.get("status", ""),
                "source_details_json": json.dumps(
                    row, ensure_ascii=False, sort_keys=True
                ),
            }
        )
    people = {str(row.get("person_id", "")) for row in builder.table(source, "people")}
    for row in person_evidence:
        if not row.get("seller_id"):
            continue
        person_id = str(row.get("person_id", ""))
        if person_id not in people:
            raise PipelineError(
                "commerce input contract: Cultural Map person/operator link has missing person"
            )
        oid = str(row.get("observation_id", ""))
        source_person_id = namespaced(source, person_id)
        builder.person_operator_links.append(
            {
                "source_person_operator_link_id": namespaced(
                    source, f"person_role:{row.get('evidence_id', '')}"
                ),
                "source": source,
                "source_person_id": source_person_id,
                "global_person_id": builder.person_crosswalk.get(source_person_id, ""),
                "source_operator_id": namespaced(source, row.get("seller_id", "")),
                "observation_id": oid,
                "source_key": row.get("source_key", ""),
                "raw_locator": builder.locator(source, oid),
                "relationship": row.get("role", ""),
                "evidence_text": row.get("evidence_passage", ""),
                "source_details_json": json.dumps(
                    row, ensure_ascii=False, sort_keys=True
                ),
            }
        )
    relevant_kinds = {
        "offering_price_parse",
        "offering_non_qualifying_role",
        "offering_operator_role_ambiguous",
        "offering_supported_duplicate",
        "offering_external_targets_unresolved",
        "offering_external_target_missing",
    }
    listing_by_key = {
        str(row["source_key"]): row
        for row in builder.listing_evidence
        if row["source"] == source
    }
    for row in review_cases:
        if row.get("kind") not in relevant_kinds:
            continue
        source_keys = [str(value) for value in json_list(row.get("source_keys_json"))]
        linked = [listing_by_key[key] for key in source_keys if key in listing_by_key]
        entities = sorted(
            {
                item["source_offering_id"]
                for item in linked
                if item["source_offering_id"]
            }
            | {
                item["source_operator_id"]
                for item in linked
                if item["source_operator_id"]
            }
        )
        builder.source_local_boundaries.append(
            {
                "source_boundary_id": namespaced(source, row.get("review_id", "")),
                "source": source,
                "boundary_kind": f"source_review_case:{row.get('kind', '')}",
                "status": row.get("status", ""),
                "reason": row.get("reason", ""),
                "source_keys_json": row.get("source_keys_json", "[]"),
                "observation_ids_json": row.get("evidence_observation_ids_json", "[]"),
                "source_entity_ids_json": json.dumps(entities, ensure_ascii=False),
                "source_locator": f"normalized://source_local/{pilot}/review_cases.csv#review_id={row.get('review_id', '')}",
            }
        )
    for row in identity_decisions:
        if row.get("namespace") != "offering":
            continue
        source_keys = [str(value) for value in json_list(row.get("source_keys_json"))]
        entity_ids = sorted(
            {
                listing_by_key[key]["source_offering_id"]
                for key in source_keys
                if key in listing_by_key and listing_by_key[key]["source_offering_id"]
            }
        )
        builder.source_local_boundaries.append(
            {
                "source_boundary_id": namespaced(source, row.get("decision_id", "")),
                "source": source,
                "boundary_kind": "source_identity_decision:offering",
                "status": row.get("status", ""),
                "reason": row.get("rule", ""),
                "source_keys_json": row.get("source_keys_json", "[]"),
                "observation_ids_json": row.get("evidence_observation_ids_json", "[]"),
                "source_entity_ids_json": json.dumps(entity_ids, ensure_ascii=False),
                "source_locator": f"normalized://source_local/{pilot}/identity_decisions.csv#decision_id={row.get('decision_id', '')}",
            }
        )


def _load_icommunity(builder: _Builder) -> None:
    source = "icommunity"
    pilot = "icommunity-v1"
    products = builder.table(source, "products")
    sellers = builder.table(source, "sellers")
    edges = builder.table(source, "product_sellers")
    edge_by_product: dict[str, dict[str, Any]] = {}
    for row in edges:
        product_id = str(row.get("product_id", ""))
        if not product_id or product_id in edge_by_product:
            raise PipelineError(
                "commerce input contract: iCommunity product has multiple operators"
            )
        edge_by_product[product_id] = row
    for row in sellers:
        builder.add_operator(
            {
                **row,
                "source": source,
                "source_operator_id": namespaced(source, row.get("seller_id", "")),
                "source_local_operator_id": row.get("seller_id", ""),
                "display_name": row.get("name", ""),
                "aliases_json": json.dumps([row.get("name", "")], ensure_ascii=False),
            }
        )
    contexts: dict[str, dict[str, Any]] = {}
    for row in products:
        local_id = str(row.get("product_id", ""))
        oid = str(row.get("observation_id", ""))
        edge = edge_by_product.get(local_id, {})
        context = {
            "source": source,
            "source_offering_id": namespaced(source, local_id),
            "source_operator_id": namespaced(source, edge.get("seller_id", "")),
            "source_listing_id": namespaced(source, oid),
            "observation_id": oid,
            "source_key": builder.source_key(source, oid),
            "raw_locator": builder.locator(source, oid),
        }
        contexts[local_id] = context
        builder.add_offering(
            {
                **row,
                "source": source,
                "source_offering_id": context["source_offering_id"],
                "source_local_offering_id": local_id,
                "display_name": row.get("name", ""),
                "aliases_json": json.dumps([row.get("name", "")], ensure_ascii=False),
            }
        )
        builder.listing_evidence.append(
            {
                **context,
                "source_local_listing_id": oid,
                "raw_source_id": row.get("source_id", ""),
                "title_raw": row.get("name", ""),
                "title_normalized": row.get("name", ""),
                "description": row.get("description", ""),
                "category_raw": row.get("categories_json", ""),
                "source_url": row.get("permalink", ""),
                "listing_eligibility": "source_reported_offering",
                "source_details_json": _source_details(row, set()),
            }
        )
        if edge:
            evidence = {
                **context,
                "evidence_text": edge.get("evidence_passage", ""),
                "source_details_json": _source_details(edge, set()),
            }
            builder.seller_evidence.append(
                {
                    **evidence,
                    "source_seller_evidence_id": namespaced(source, "seller:" + oid),
                    "role": edge.get("relationship", ""),
                    "basis": "source_product_operator_passage",
                }
            )
            builder.operator_offering_edges.append(
                {
                    **evidence,
                    "source_operator_offering_edge_id": namespaced(
                        source, "edge:" + oid
                    ),
                    "relationship": edge.get("relationship", ""),
                }
            )
        for ordinal, value in enumerate(json_list(row.get("images_json"))):
            media = value if isinstance(value, dict) else {"src": value}
            builder.media.append(
                {
                    **context,
                    "source_media_id": namespaced(source, f"{oid}:image:{ordinal}"),
                    "media_kind": "image",
                    "ordinal": ordinal,
                    "url_or_value": media.get("src", ""),
                    "label": media.get("name", ""),
                    "status": "source_reference_not_inspected",
                    "source_details_json": json.dumps(media, ensure_ascii=False),
                }
            )
    for row in builder.table(source, "product_prices"):
        product_id = str(row.get("product_id", ""))
        if product_id not in contexts:
            raise PipelineError(
                "commerce input contract: iCommunity price lacks product"
            )
        amount = row.get("amount_thb")
        builder.prices.append(
            {
                **contexts[product_id],
                "source_price_id": namespaced(
                    source, product_id + ":" + str(row.get("price_kind", ""))
                ),
                "price_text_raw": row.get("amount_raw", ""),
                "amounts_json": json.dumps(
                    [amount] if amount not in (None, "") else [], ensure_ascii=False
                ),
                "currency": row.get("currency", ""),
                "parse_status": "source_minor_units"
                if amount not in (None, "")
                else "missing",
                "source_details_json": _source_details(row, set()),
            }
        )
    for row in builder.table(source, "locations"):
        entity_id = str(row.get("entity_id", ""))
        if entity_id not in contexts:
            continue
        context = contexts[entity_id]
        builder.locations.append(
            {
                **row,
                **context,
                "source_entity_id": namespaced(source, entity_id),
                "source_location_id": namespaced(source, row.get("location_id", "")),
                "source_details_json": _source_details(row, set()),
            }
        )
    for row in builder.table(source, "review_cases"):
        entity_id = str(row.get("entity_id", ""))
        if entity_id not in contexts:
            continue
        context = contexts[entity_id]
        builder.source_local_boundaries.append(
            {
                "source_boundary_id": namespaced(source, row.get("review_id", "")),
                "source": source,
                "boundary_kind": row.get("kind", ""),
                "status": row.get("status", ""),
                "reason": row.get("reason", ""),
                "source_keys_json": json.dumps([context["source_key"]]),
                "observation_ids_json": json.dumps([row.get("observation_id", "")]),
                "source_entity_ids_json": json.dumps([context["source_offering_id"]]),
                "source_locator": f"normalized://source_local/{pilot}/review_cases.csv#review_id={row.get('review_id', '')}",
            }
        )


def load_sources(
    source_tables: dict[str, dict[str, list[dict]]],
    raw_inputs: dict[str, dict],
    people_tables: dict[str, list[dict]],
) -> OfferingSources:
    """Return all source-local commerce evidence without discovering identities."""
    builder = _Builder(source_tables, raw_inputs, people_tables)
    _load_atlocal(builder)
    _load_cultural_map(builder)
    _load_icommunity(builder)
    return builder.finish()

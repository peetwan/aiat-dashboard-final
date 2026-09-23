"""Pure AtLocal source-local normalization preserving the accepted legacy semantics."""

from __future__ import annotations

import itertools
import json
import re
from collections import defaultdict
from decimal import Decimal
from typing import Any

from ..common import Components, normalize, readable, safe_text, stable_id

DATASET_KEYS = (
    "areas",
    "articles",
    "cultures",
    "entrepreneurs",
    "festivals",
    "marketplace_products",
    "product_map",
)
ID_FIELDS = {
    "product_map": "map_product_id",
    "marketplace_products": "marketplace_product_id",
    "areas": "area_id",
    "festivals": "festival_id",
    "entrepreneurs": "entrepreneur_id",
    "cultures": "culture_id",
    "articles": "article_id",
}
SEMANTIC_DATASETS = {"areas": "areas_16"}
TABLE_COLUMNS = {
    "activities": [
        "activity_id",
        "observation_id",
        "publication_id",
        "name",
        "province",
        "start_date",
        "end_date",
        "status",
        "date_evidence_json",
        "identity_status",
    ],
    "activity_sections": [
        "section_id",
        "publication_id",
        "observation_id",
        "activity_id",
        "line_index",
        "text",
        "attribution",
    ],
    "areas": [
        "area_id",
        "observation_id",
        "name",
        "description",
        "source_key",
        "images_json",
        "identity_status",
    ],
    "entity_observations": ["entity_id", "entity_type", "observation_id", "source_key"],
    "identity_decisions": [
        "decision_id",
        "left_source_key",
        "right_source_key",
        "rule",
        "outcome",
        "evidence_observation_ids_json",
    ],
    "images": [
        "image_id",
        "observation_id",
        "product_id",
        "source_key",
        "image_url",
        "status",
    ],
    "listing_channels": [
        "observation_id",
        "product_id",
        "source_key",
        "channel",
        "platform_shop_id",
        "sale_channel_json",
        "fulfilment_json",
    ],
    "listing_observations": [
        "listing_id",
        "observation_id",
        "source_key",
        "product_id",
        "seller_id",
        "name_raw",
        "name_normalized",
        "description",
        "category_raw",
        "active_raw",
        "stock_quantity_raw",
        "exclusive_raw",
        "tags_json",
        "created_at",
        "updated_at",
        "source_url",
        "product_eligibility",
        "source_warnings_json",
    ],
    "locations": [
        "location_id",
        "observation_id",
        "entity_id",
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
        "correction_reason",
    ],
    "measure_contributions": ["measure", "entity_id", "scope", "status"],
    "measure_results": ["measure", "value", "scope", "status", "note"],
    "people": [
        "person_id",
        "display_name",
        "aliases_json",
        "name_quality",
        "identity_status",
        "eligibility",
    ],
    "person_evidence": [
        "person_id",
        "publication_id",
        "observation_id",
        "source_key",
        "role",
        "evidence",
    ],
    "person_sellers": ["person_id", "seller_id", "observation_id", "relationship"],
    "prior_component_comparison": [
        "prior_product_id",
        "source_keys_json",
        "current_product_ids_json",
        "status",
        "note",
    ],
    "product_prices": [
        "observation_id",
        "product_id",
        "source_key",
        "amount_raw",
        "amount_thb",
        "currency",
        "interpretation",
    ],
    "product_sellers": ["product_id", "seller_id", "observation_id", "relationship"],
    "products": [
        "product_id",
        "name",
        "aliases_json",
        "source_keys_json",
        "identity_status",
        "name_quality",
    ],
    "publications": [
        "publication_id",
        "observation_id",
        "source_key",
        "title",
        "content",
        "published_at",
        "source_url",
        "classification_raw",
        "active_raw",
        "status",
    ],
    "review_cases": [
        "review_id",
        "kind",
        "source_keys_json",
        "reason",
        "possible_impact",
        "status",
        "user_decision",
        "names_json",
    ],
    "seller_evidence": [
        "seller_id",
        "observation_id",
        "source_key",
        "name_raw",
        "evidence",
        "basis",
    ],
    "sellers": [
        "seller_id",
        "name",
        "province",
        "district",
        "province_code",
        "district_code",
        "identity_status",
        "name_quality",
    ],
    "source_files": ["dataset", "file", "sha256", "row_count", "envelope_json"],
    "source_observations": [
        "observation_id",
        "dataset",
        "source_id",
        "source_key",
        "raw_file",
        "row_locator",
        "file_sha256",
        "captured_at",
        "disposition",
    ],
}
TABLE_GRAINS = {
    "source_files": "one supplied AtLocal capture file",
    "source_observations": "one record in one supplied AtLocal capture",
    "areas": "one source-named cultural area",
    "products": "one reviewed source-local product identity component",
    "listing_observations": "one source marketplace or map offering assertion",
    "product_prices": "one price assertion for one source listing",
    "locations": "one source listing or cultural-area location assertion",
    "images": "one source image reference; content not inspected",
    "listing_channels": "one source channel assertion for one listing",
    "sellers": "one reviewed source-local operator identity",
    "seller_evidence": "one source observation supporting an operator identity",
    "product_sellers": "one observed product-to-operator relationship",
    "publications": "one source narrative publication",
    "activities": "one reviewed parent festival occurrence",
    "activity_sections": "one attributed narrative line from a festival publication",
    "people": "one explicitly reviewed narrative person",
    "person_evidence": "one publication supporting a reviewed person",
    "person_sellers": "one reviewed person-to-operator relationship",
    "identity_decisions": "one applied source-local product identity rule",
    "review_cases": "one retained source-local ambiguity or reviewed treatment",
    "prior_component_comparison": "one accepted prior component compared with rebuilt identities",
    "entity_observations": "one entity-to-source-observation lineage link",
    "measure_results": "one source-local accounting result, not a cross-source dashboard result",
    "measure_contributions": "one entity contribution to source-local accounting",
}


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def matching_text(value):
    return normalize(value).casefold()


def _fail(message):
    raise ValueError(f"AtLocal input contract: {message}")


class AtLocal:
    def __init__(self, datasets, reviews, geography, input_metadata):
        if set(datasets) != set(DATASET_KEYS):
            _fail(f"datasets must be exactly {', '.join(DATASET_KEYS)}")
        if not isinstance(reviews, dict):
            _fail("reviews must be an object")
        config = reviews.get("reviewed_cases.json", reviews.get("reviewed_cases"))
        prior = reviews.get(
            "prior_product_components.json", reviews.get("prior_product_components")
        )
        if not isinstance(config, dict):
            _fail("reviewed_cases.json must be supplied")
        if not isinstance(prior, dict) or not isinstance(prior.get("components"), list):
            _fail("prior_product_components.json must contain components")
        self.config, self.prior = config, prior
        self.datasets, self.input_metadata, self.geography = (
            datasets,
            input_metadata,
            geography,
        )
        self.tables = {name: [] for name in TABLE_COLUMNS}
        self.data = {}
        self.observations = {}
        self.listings = {}
        self.addresses = {}
        self.seller_for_listing = {}
        self.sellers = {}

    def metadata(self, dataset):
        value = self.input_metadata.get(dataset)
        required = (
            "source_id",
            "run_id",
            "file",
            "sha256",
            "size",
            "captured_at",
            "originating_system",
        )
        if not isinstance(value, dict) or any(
            key not in value or value[key] in (None, "") for key in required
        ):
            _fail(f"metadata for {dataset} must include {', '.join(required)}")
        return value

    def raw_locator(self, dataset, index):
        metadata = self.metadata(dataset)
        return f"evidence://{metadata['source_id']}/{metadata['run_id']}/{metadata['file']}#/data/{index}"

    def add(self, table, **row):
        self.tables[table].append(row)

    def review(self, kind, keys, reason, impact, status="unresolved"):
        keys = sorted(set(keys))
        decisions = {
            "code_only_operator_identity": "User accepted code-only operator labels for KPI eligibility; retain name-quality flags.",
            "seller_alias_unresolved": "Supported aliases merged under the user's reviewed instructions; products are not automatically merged.",
            "unnamed_map_possible_recovery": "User confirmed the same shop and offering; link map 1274 to existing marketplace 390 product.",
        }
        decision = decisions.get(kind, "")
        if decision:
            status = "resolved_by_review"
        self.add(
            "review_cases",
            review_id=stable_id("atlocal_review", kind, keys),
            kind=kind,
            source_keys_json=keys,
            reason=reason,
            possible_impact=impact,
            status=status,
            user_decision=decision,
        )

    def ingest(self):
        for dataset, id_field in ID_FIELDS.items():
            envelope = self.datasets[dataset]
            metadata = self.metadata(dataset)
            semantic_dataset = SEMANTIC_DATASETS.get(dataset, dataset)
            if not isinstance(envelope, dict) or not isinstance(
                envelope.get("data"), list
            ):
                _fail(f"{dataset} must be a data-list capture envelope")
            rows = envelope["data"]
            if envelope.get("record_count") not in (None, len(rows)):
                _fail(f"{dataset} record_count differs from data length")
            if not all(
                isinstance(row, dict) and row.get(id_field) is not None for row in rows
            ):
                _fail(f"{dataset} records must contain {id_field}")
            if len({str(row[id_field]) for row in rows}) != len(rows):
                _fail(f"{dataset} source IDs must be unique")
            self.data[dataset] = rows
            self.add(
                "source_files",
                dataset=semantic_dataset,
                file=metadata["file"],
                sha256=metadata["sha256"],
                row_count=len(rows),
                envelope_json={
                    key: value for key, value in envelope.items() if key != "data"
                },
            )
            for index, row in enumerate(rows):
                key = semantic_dataset + ":" + str(row[id_field])
                observation_id = stable_id(
                    "atlocal_obs", semantic_dataset, metadata["sha256"], index
                )
                self.observations[key] = observation_id
                self.add(
                    "source_observations",
                    observation_id=observation_id,
                    dataset=semantic_dataset,
                    source_id=str(row[id_field]),
                    source_key=key,
                    raw_file=metadata["file"],
                    row_locator=self.raw_locator(dataset, index),
                    file_sha256=metadata["sha256"],
                    captured_at=metadata["captured_at"],
                    disposition="retained_with_lineage",
                )

    def seller_name(self, name):
        name = normalize(name)
        return self.config["seller_aliases"].get(name, name)

    def register_seller(self, name, address, key, evidence, basis):
        name = self.seller_name(name)
        if not name:
            return ""
        sid = stable_id(
            "atlocal_seller",
            matching_text(name),
            address["province_code"],
            address["district_code"] or address["district_normalized"],
        )
        if sid not in self.sellers:
            self.sellers[sid] = {
                "seller_id": sid,
                "name": name,
                "province": address["province_normalized"],
                "district": address["district_normalized"],
                "province_code": address["province_code"],
                "district_code": address["district_code"],
                "identity_status": "provisional_source_local_operator",
                "name_quality": "code_only_operator_label"
                if re.fullmatch(r"[\d_\-\s]+", name)
                else "named_operator",
            }
        self.add(
            "seller_evidence",
            seller_id=sid,
            observation_id=self.observations[key],
            source_key=key,
            name_raw=name
            if basis != "map_seller_field"
            else self.listings[key]["shop_name"],
            evidence=safe_text(evidence),
            basis=basis,
        )
        return sid

    def prepare_listings(self):
        for dataset in ["product_map", "marketplace_products"]:
            for row in self.data[dataset]:
                key = dataset + ":" + str(row[ID_FIELDS[dataset]])
                self.listings[key] = row
                address = self.geography.resolve(
                    row.get("province"), row.get("district")
                )
                self.addresses[key] = address
                if address["status"] != "hierarchy_match":
                    self.review(
                        "geography",
                        [key],
                        address["status"],
                        "Location detail; raw values retained",
                        "documented_correction"
                        if address["correction_reason"]
                        else "unresolved",
                    )
                if dataset == "product_map":
                    self.seller_for_listing[key] = self.register_seller(
                        row.get("shop_name"),
                        address,
                        key,
                        normalize(row.get("shop_name")),
                        "map_seller_field",
                    )
        # Seller identification is independent of identifying a specific product.
        for key, row in self.listings.items():
            if not key.startswith("marketplace_products:"):
                continue
            description = matching_text(row.get("description_raw"))
            address = self.addresses[key]
            matches = []
            for sid, seller in self.sellers.items():
                name = matching_text(seller["name"])
                same_place = (
                    seller["province_code"] == address["province_code"]
                    and address["province_code"]
                )
                district_ok = (
                    not address["district_code"]
                    or seller["district_code"] == address["district_code"]
                )
                # Exact description or an initial named seller phrase avoids incidental mentions.
                starts = description == name or (
                    description.startswith(name)
                    and len(description) > len(name)
                    and description[len(name)] in " ,:;(/-–"
                )
                if same_place and district_ok and starts:
                    matches.append(sid)
            exact_names = [
                sid
                for sid in matches
                if description == matching_text(self.sellers[sid]["name"])
            ]
            if exact_names:
                matches = exact_names
            # Prefer an explicitly written full operator name over its shorter prefix.
            # Example: "ใบคราม สกล" is stronger than incidental prefix "ใบคราม".
            matches = [
                sid
                for sid in matches
                if not any(
                    sid != other
                    and matching_text(self.sellers[other]["name"]).startswith(
                        matching_text(self.sellers[sid]["name"]) + " "
                    )
                    for other in matches
                )
            ]
            if len(matches) == 1:
                sid = matches[0]
                self.seller_for_listing[key] = sid
                self.add(
                    "seller_evidence",
                    seller_id=sid,
                    observation_id=self.observations[key],
                    source_key=key,
                    name_raw=self.sellers[sid]["name"],
                    evidence=safe_text(normalize(row.get("description_raw"))),
                    basis="unique_named_map_seller_in_marketplace_description",
                )
            else:
                self.review(
                    "marketplace_operator_unresolved",
                    [key],
                    "No unique supported local operator from description/location; platform shop_id is not a seller",
                    "Operator coverage partial; offering retained",
                )
        by_name = defaultdict(list)
        for sid, seller in self.sellers.items():
            by_name[matching_text(seller["name"])].append(sid)
        for name, ids in by_name.items():
            if len(ids) > 1:
                keys = [k for k, sid in self.seller_for_listing.items() if sid in ids]
                self.review(
                    "seller_across_locations",
                    keys,
                    f"Same operator name across locations: {name}",
                    "K05 identity unresolved",
                )

    def resolve_products(self):
        eligible = {k for k, r in self.listings.items() if normalize(r.get("name"))}
        recovered = self.config.get("recovered_offering_pairs", [])
        eligible.update(key for pair in recovered for key in pair)
        components = Components(eligible, self.config["cannot_link_products"])
        for left, right in recovered:
            assert self.seller_for_listing[left] == self.seller_for_listing[right]
            assert (
                self.addresses[left]["district_code"]
                == self.addresses[right]["district_code"]
            )
            self.merge(
                components, left, right, "user_confirmed_unnamed_offering_recovery"
            )
        # Generic/specific uncertainty does not block a separate, supported channel match.
        held = {
            k
            for group in self.config["unresolved_product_groups"]
            if len(group) > 2
            for k in group
        }
        for group in self.config["unresolved_product_groups"]:
            self.review(
                "accepted_unresolved_offering_group",
                group,
                "Accepted unresolved variants or generic/specific overlap; preserve each listing identity",
                "K07 provisional; do not subtract pair counts",
            )
        # Same-source rows merge only if the complete semantic payload, including images, agrees.
        fingerprints = defaultdict(list)
        for key in sorted(eligible):
            row = self.listings[key]
            omitted = {
                ID_FIELDS[key.split(":", 1)[0]],
                "created_at",
                "updated_at",
                "product_url",
                "map_url",
            }
            fingerprint = dump({k: v for k, v in row.items() if k not in omitted})
            fingerprints[key.split(":", 1)[0], fingerprint].append(key)
        for keys in fingerprints.values():
            for other in keys[1:]:
                if not set(keys) & held:
                    self.merge(
                        components,
                        keys[0],
                        other,
                        "identical_semantic_payload_including_images",
                    )
        by_title = defaultdict(list)
        for key in sorted(eligible):
            by_title[matching_text(self.listings[key]["name"])].append(key)
        candidates = defaultdict(set)
        for keys in by_title.values():
            maps = [k for k in keys if k.startswith("product_map:")]
            markets = [k for k in keys if k.startswith("marketplace_products:")]
            for market, map_key in itertools.product(markets, maps):
                sid = self.seller_for_listing.get(market)
                a, b = self.addresses[market], self.addresses[map_key]
                if (
                    sid
                    and sid == self.seller_for_listing.get(map_key)
                    and a["province_code"]
                    and a["province_code"] == b["province_code"]
                    and a["district_code"]
                    and a["district_code"] == b["district_code"]
                ):
                    candidates[market].add(map_key)
        reverse = defaultdict(set)
        for market, maps in candidates.items():
            for map_key in maps:
                reverse[map_key].add(market)
        for market, maps in sorted(candidates.items()):
            map_key = next(iter(maps)) if len(maps) == 1 else None
            unique = map_key and len(reverse[map_key]) == 1
            if unique and market not in held and map_key not in held:
                self.merge(
                    components,
                    market,
                    map_key,
                    "unique_title_named_seller_and_normalized_district",
                )
            elif not ({market} | maps) <= held:
                self.review(
                    "ambiguous_cross_table_product",
                    [market, *maps],
                    "Title/operator/location agree but variant assignment is not one-to-one",
                    "K07 provisional; all listings remain separate",
                )
        # Same seller/title repetitions with distinct image evidence remain reviewable.
        seller_titles = defaultdict(list)
        for key in sorted(eligible):
            sid = self.seller_for_listing.get(key)
            if sid:
                seller_titles[sid, matching_text(self.listings[key]["name"])].append(
                    key
                )
        for keys in seller_titles.values():
            if len({components.find(k) for k in keys}) > 1 and not set(keys) <= held:
                self.review(
                    "same_seller_title_multiple_offerings",
                    keys,
                    "Shared title/operator does not establish whether images represent variants or repeated listings",
                    "K07 provisional",
                )
        self.product_ids = {
            key: stable_id("atlocal_product", components.find(key)) for key in eligible
        }
        for root, members in sorted(components.members.items()):
            names = sorted(
                {
                    normalize(self.listings[k]["name"])
                    for k in members
                    if normalize(self.listings[k]["name"])
                }
            )
            self.add(
                "products",
                product_id=self.product_ids[root],
                name=names[0],
                aliases_json=names,
                source_keys_json=sorted(members),
                identity_status="provisional_source_local",
                name_quality="generic_source_title"
                if matching_text(names[0])
                in {"อาหาร", "ของใช้", "เสื้อผ้า", "เครื่องประดับ", "ความเชื่อ", "ที่พัก"}
                else "source_reported_title",
            )
        for key, row in self.listings.items():
            oid = self.observations[key]
            product = self.product_ids.get(key, "")
            seller = self.seller_for_listing.get(key, "")
            self.add(
                "listing_observations",
                listing_id=stable_id("atlocal_listing", key),
                observation_id=oid,
                source_key=key,
                product_id=product,
                seller_id=seller,
                name_raw=row.get("name"),
                name_normalized=normalize(row.get("name")),
                description=safe_text(readable(row.get("description_raw", ""))),
                category_raw=row.get(
                    "category", (row.get("product_type") or {}).get("name")
                ),
                active_raw=row.get("active"),
                stock_quantity_raw=row.get("stock_quantity"),
                exclusive_raw=row.get("exclusive"),
                tags_json=row.get("tags", []),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
                source_url=row.get("product_url") or row.get("map_url"),
                product_eligibility="source_reported_offering"
                if product
                else "unnamed_offering_not_identified",
                source_warnings_json=row.get("warnings", []),
            )
            if not product:
                self.review(
                    "unnamed_offering",
                    [key],
                    "Seller retained; no named offering or supported text link. Image references retained but image content unreviewed",
                    "Excluded from K07 until offering identity supported; K05 evidence retained",
                )
            self.add(
                "product_prices",
                observation_id=oid,
                product_id=product,
                source_key=key,
                amount_raw=row.get("price_thb"),
                amount_thb=str(Decimal(str(row["price_thb"])))
                if row.get("price_thb") is not None
                else None,
                currency="THB",
                interpretation="zero_meaning_unestablished"
                if row.get("price_thb") == 0
                else "source_reported_price",
            )
            self.add(
                "locations",
                location_id=stable_id("atlocal_location", key),
                observation_id=oid,
                entity_id=product or seller,
                source_key=key,
                location_role="source_listing_location",
                **self.addresses[key],
            )
            for index, url in enumerate(row.get("image_urls", [])):
                self.add(
                    "images",
                    image_id=stable_id("atlocal_image", key, index),
                    observation_id=oid,
                    product_id=product,
                    source_key=key,
                    image_url=url,
                    status="placeholder"
                    if "default.png" in url
                    else "reference_only_content_not_inspected",
                )
            self.add(
                "listing_channels",
                observation_id=oid,
                product_id=product,
                source_key=key,
                channel="marketplace"
                if key.startswith("marketplace")
                else "product_map",
                platform_shop_id=row.get("shop_id"),
                sale_channel_json=row.get("sale_channel"),
                fulfilment_json=row.get("fulfilment_status"),
            )
            if product:
                self.add(
                    "entity_observations",
                    entity_id=product,
                    entity_type="product",
                    observation_id=oid,
                    source_key=key,
                )
            if seller:
                self.add(
                    "entity_observations",
                    entity_id=seller,
                    entity_type="seller",
                    observation_id=oid,
                    source_key=key,
                )
            if product and seller:
                self.add(
                    "product_sellers",
                    product_id=product,
                    seller_id=seller,
                    observation_id=oid,
                    relationship="source_reported_operator",
                )
        for market, map_id in self.config["expected_supported_pairs"]:
            assert (
                self.product_ids["marketplace_products:" + market]
                == self.product_ids["product_map:" + map_id]
            )

    def merge(self, components, left, right, rule):
        outcome = components.merge(left, right)
        self.add(
            "identity_decisions",
            decision_id=stable_id("atlocal_decision", left, right, rule),
            left_source_key=left,
            right_source_key=right,
            rule=rule,
            outcome=outcome,
            evidence_observation_ids_json=[
                self.observations[left],
                self.observations[right],
            ],
        )

    def clean_page(self, html):
        lines = readable(html).splitlines()
        # Full-page captures contain a duplicated site navigation before the subject.
        nav = [i for i, line in enumerate(lines[:45]) if line == "บทความ"]
        start = nav[-1] + 1 if nav else 0
        ends = [
            i
            for i, line in enumerate(lines)
            if i >= start
            and line.startswith(
                (
                    "© At Local",
                    "เว็บไซต์นี้ใช้คุกกี้",
                    "ผู้สนับสนุนโครงการ",
                    "เกี่ยวกับเราเว็บไซต์",
                    "การให้ความยินยอมการใช้และเผยแพร่รูปภาพ",
                )
            )
        ]
        end = min(ends) if ends else len(lines)
        return safe_text("\n".join(lines[start:end]))

    def narratives(self):
        self.publication_ids = {}
        for dataset in ["festivals", "entrepreneurs", "cultures", "articles"]:
            for row in self.data[dataset]:
                key = dataset + ":" + str(row[ID_FIELDS[dataset]])
                oid = self.observations[key]
                pid = stable_id("atlocal_publication", key)
                self.publication_ids[key] = pid
                html = row.get("description_html") or row.get("summary_html") or ""
                text = self.clean_page(html)
                self.add(
                    "publications",
                    publication_id=pid,
                    observation_id=oid,
                    source_key=key,
                    title=normalize(row["title"]),
                    content=text,
                    published_at=row.get("published_date"),
                    source_url=row.get("source_url") or row.get("detail_api_url"),
                    classification_raw=row.get("type_raw"),
                    active_raw=row.get("active"),
                    status="title_body_mismatch"
                    if key == "articles:3"
                    else "source_publication",
                )
                if key == "articles:3":
                    self.review(
                        "title_body_mismatch",
                        [key],
                        "Title names weaving group; body has editorial placeholder and another cultural subject. No body-derived counted entities/links",
                        "Withhold unsupported product/person/event relationships",
                        "accepted_treatment",
                    )
                if dataset == "festivals":
                    self.festival(row, key, text)
        for row in self.data["areas"]:
            key = "areas_16:" + row["area_id"]
            aid = stable_id("atlocal_area", key)
            self.add(
                "areas",
                area_id=aid,
                observation_id=self.observations[key],
                name=normalize(row["name"]),
                description=safe_text(readable(row.get("description_raw", ""))),
                source_key=key,
                images_json=row.get("image_urls", []),
                identity_status="source_named_cultural_area",
            )
            address = self.geography.resolve(row.get("province"), row.get("district"))
            self.add(
                "locations",
                location_id=stable_id("atlocal_location", key),
                observation_id=self.observations[key],
                entity_id=aid,
                source_key=key,
                location_role="programme_cultural_area",
                **address,
            )
        self.people_from_narratives()
        for keys in [
            [
                "product_map:1552",
                "product_map:1689",
                "product_map:1690",
                "product_map:1691",
            ],
            ["product_map:1411", "product_map:1418"],
            ["product_map:1244", "product_map:1653"],
        ]:
            self.review(
                "seller_alias_unresolved",
                keys,
                "Similar/expanded operator names in the same locality; supported channel links do not establish an operator alias",
                "K05 may decrease if the operator identities are later confirmed equal",
            )
        self.review(
            "unnamed_map_possible_recovery",
            ["product_map:1274", "marketplace_products:390"],
            "Near-spelling noodle-shop name and locality agree, but map offering is unnamed. Keep possible recovery link for review",
            "Could recover a link to an existing offering, not automatically a new K07 product",
        )

    def festival(self, row, key, text):
        config = self.config["festivals"][row["festival_id"]]
        aid = stable_id("atlocal_activity", key)
        # The title establishes an edition for sparse pages; body dates are not fabricated.
        combined = normalize(row["title"] + " " + text)
        for evidence in config["date_evidence"]:
            assert normalize(evidence) in combined, (key, evidence)
        self.add(
            "activities",
            activity_id=aid,
            observation_id=self.observations[key],
            publication_id=self.publication_ids[key],
            name=config["name"],
            province=config["province"],
            start_date=config["start_date"],
            end_date=config["end_date"],
            status=config["status"],
            date_evidence_json=config["date_evidence"],
            identity_status="provisional_parent_occurrence",
        )
        foreign = False
        for index, line in enumerate(text.splitlines()):
            if config.get("foreign_section_start") and line.startswith(
                config["foreign_section_start"]
            ):
                foreign = True
            if foreign and line.startswith(config["foreign_section_end"]):
                foreign = False
            self.add(
                "activity_sections",
                section_id=stable_id("atlocal_section", key, index),
                publication_id=self.publication_ids[key],
                observation_id=self.observations[key],
                activity_id="" if foreign else aid,
                line_index=index,
                text=line,
                attribution="foreign_thungsong_section_not_kalasin"
                if foreign
                else "parent_page_detail_not_extra_occurrence",
            )
        if config["status"] in {
            "edition_title_only",
            "edition_title_only_possible_duplicate",
            "parent_competition_date_conflict",
        }:
            self.review(
                "activity_detail",
                [key],
                config["status"],
                "Retain parent occurrence; dates unknown/conflicting",
                "accepted_treatment",
            )
        if row["festival_id"] == "lampang/event2":
            self.review(
                "possible_event_duplicate",
                [key, "festivals:lampang/2568-Lampang-Festival"],
                "Accepted possible duplicate; city/year alone insufficient",
                "K03 provisional",
            )

    def people_from_narratives(self):
        # Explicit reviewed passages establish people; profile labels alone do not.
        cases = [
            {
                "name": "ปราโมช เชี่ยวชาญ",
                "alias": "ลุงแป๊ะ",
                "keys": ["articles:1", "entrepreneurs:2"],
                "required": ["ปราโมช เชี่ยวชาญ", "จำหน่าย"],
                "province": "ชลบุรี",
                "district": "พนัสนิคม",
                "seller": "เอ็งกอลุงแป๊ะ",
                "name_quality": "full_name_with_explicit_nickname",
            },
            {
                "name": "คุณป้าผลศรี",
                "alias": "คุณป้าผลศรี",
                "keys": ["articles:2", "cultures:15", "entrepreneurs:1"],
                "required": ["คุณป้าผลศรี", "เจ้าของร้านศรีบาติก"],
                "province": "พัทลุง",
                "district": "เมือง",
                "seller": "ห้องเสื้อศรีบาติกลำปำ",
                "name_quality": "identified_person_incomplete_name",
            },
        ]
        publications = {r["source_key"]: r for r in self.tables["publications"]}
        for case in cases:
            primary = publications[case["keys"][0]]
            assert all(word in primary["content"] for word in case["required"])
            person = stable_id("atlocal_person", case["keys"][0], case["name"])
            self.add(
                "people",
                person_id=person,
                display_name=case["name"],
                aliases_json=[case["alias"]],
                name_quality=case["name_quality"],
                identity_status="reviewed_narrative_person",
                eligibility="explicit_cultural_entrepreneur",
            )
            address = self.geography.resolve(case["province"], case["district"])
            sid = self.register_seller(
                case["seller"],
                address,
                case["keys"][0],
                primary["content"],
                "reviewed_narrative_operator",
            )
            for key in case["keys"]:
                publication = publications[key]
                self.add(
                    "person_evidence",
                    person_id=person,
                    publication_id=publication["publication_id"],
                    observation_id=self.observations[key],
                    source_key=key,
                    role="cultural_product_operator"
                    if key.startswith("articles") or key.startswith("cultures")
                    else "supported_related_profile",
                    evidence=publication["content"] or publication["title"],
                )
                self.add(
                    "entity_observations",
                    entity_id=person,
                    entity_type="person",
                    observation_id=self.observations[key],
                    source_key=key,
                )
            self.add(
                "person_sellers",
                person_id=person,
                seller_id=sid,
                observation_id=self.observations[case["keys"][0]],
                relationship="explicit_narrative_operator",
            )
        for key in ["entrepreneurs:3", "entrepreneurs:4"]:
            self.review(
                "non_person_or_unnamed_profile",
                [key],
                "Profile subject is a group or unnamed brand creator; no invented person count",
                "K06 coverage partial; profile preserved",
                "accepted_treatment",
            )

    def compare_prior_components(self):
        seen = set()
        for component in self.prior["components"]:
            if (
                not isinstance(component, dict)
                or not isinstance(component.get("source_keys"), list)
                or not component.get("prior_product_id")
            ):
                _fail("invalid prior product component")
            keys = component["source_keys"]
            if not all(key in self.listings and key not in seen for key in keys):
                _fail("prior product components repeat or reference an unknown listing")
            seen.update(keys)
            current = sorted(
                {self.product_ids[key] for key in keys if key in self.product_ids}
            )
            self.add(
                "prior_component_comparison",
                prior_product_id=component["prior_product_id"],
                source_keys_json=keys,
                current_product_ids_json=current,
                status="split_old_component"
                if len(current) > 1
                else "members_still_together",
                note="Comparison only; old component is not merge authority",
            )
        recovered_keys = {
            key
            for pair in self.config.get("recovered_offering_pairs", [])
            for key in pair
        }
        if seen != set(self.product_ids) - (recovered_keys - seen):
            _fail(
                "prior product component coverage differs from rebuilt eligible listings"
            )

    def merge_reviewed_operators(self):
        for case in self.config.get("reviewed_operator_merges", []):
            left = self.seller_for_listing[case["left"]]
            right = self.seller_for_listing[case["right"]]
            for field in ["province_code", "district_code"]:
                assert self.sellers[left][field] == self.sellers[right][field]
            if left == right:
                continue
            for key, sid in self.seller_for_listing.items():
                if sid == left:
                    self.seller_for_listing[key] = right
            for rows in self.tables.values():
                for row in rows:
                    if row.get("seller_id") == left:
                        row["seller_id"] = right
                    if row.get("entity_id") == left:
                        row["entity_id"] = right
            self.sellers.pop(left)
            left_key, right_key = case["left"], case["right"]
            if matching_text(self.listings[left_key].get("name")) == matching_text(
                self.listings[right_key].get("name")
            ) and self.product_ids.get(left_key) != self.product_ids.get(right_key):
                self.review(
                    "offering_after_operator_merge",
                    [left_key, right_key],
                    "Operator alias confirmed, but same-title product listings have distinct image evidence; offering identity remains unresolved",
                    "K07 provisional; operator merge alone does not merge offerings",
                )

    def finish(self):
        assert self.config.get("code_only_operators_eligible") is True, (
            "Review code-only operator eligibility before changing this policy"
        )
        self.compare_prior_components()
        self.tables["sellers"] = list(self.sellers.values())
        coded_keys = [
            key
            for key, sid in self.seller_for_listing.items()
            if self.sellers[sid]["name_quality"] == "code_only_operator_label"
        ]
        self.review(
            "code_only_operator_identity",
            coded_keys,
            "Source seller labels contain only codes. Distinct local seller/stall meaning is not established",
            "Keep source operator records; code-only contribution to K05 pending meaning",
        )
        measures = [
            ("cultural_products", "products", "product_id"),
            ("cultural_sellers", "sellers", "seller_id"),
            ("named_operator_records", "sellers", "seller_id"),
            ("source_reported_operator_records", "sellers", "seller_id"),
            ("code_only_operator_records", "sellers", "seller_id"),
            ("cultural_entrepreneurs", "people", "person_id"),
            ("reported_activities", "activities", "activity_id"),
            ("cultural_areas", "areas", "area_id"),
        ]
        for measure, table, id_field in measures:
            selected = self.tables[table]
            if measure == "named_operator_records":
                selected = [
                    r for r in selected if r["name_quality"] == "named_operator"
                ]
            elif measure == "code_only_operator_records":
                selected = [
                    r
                    for r in selected
                    if r["name_quality"] == "code_only_operator_label"
                ]
            ids = {r[id_field] for r in selected}
            self.add(
                "measure_results",
                measure=measure,
                value=len(ids),
                scope="atlocal_only",
                status="provisional_source_local",
                note=(
                    "Includes code-only operators accepted by user; name quality retained"
                    if measure == "cultural_sellers"
                    else "Companion breakdown of eligible operators; do not add to headline"
                    if measure
                    in {
                        "source_reported_operator_records",
                        "code_only_operator_records",
                        "named_operator_records",
                    }
                    else "Not final cross-source KPI; unresolved identities and partial operator/person extraction retained"
                ),
            )
            for eid in sorted(ids):
                self.add(
                    "measure_contributions",
                    measure=measure,
                    entity_id=eid,
                    scope="atlocal_only",
                    status="provisional_source_local",
                )
        source_names = {
            r["source_key"]: (
                r.get("name_normalized")
                or self.listings[r["source_key"]].get("shop_name", "")
            )
            for r in self.tables["listing_observations"]
        }
        source_names.update(
            {r["source_key"]: r["title"] for r in self.tables["publications"]}
        )
        for case in self.tables["review_cases"]:
            case["names_json"] = [
                source_names.get(k, k) for k in case["source_keys_json"]
            ]
        for name, rows in self.tables.items():
            unique = {}
            for row in rows:
                unique[dump(row)] = row
            self.tables[name] = list(unique.values())
        return self.tables

    def validate(self):
        for table, rows in self.tables.items():
            expected = set(TABLE_COLUMNS[table])
            for row in rows:
                if set(row) != expected:
                    _fail(f"{table} row columns differ from the legacy schema")
        observations = set(self.observations.values())
        for table_rows in self.tables.values():
            for row in table_rows:
                if (
                    row.get("observation_id")
                    and row["observation_id"] not in observations
                ):
                    _fail("derived row references an unknown observation")
        product_ids = set(self.product_ids.values())
        seller_ids = set(self.sellers)
        people = {row["person_id"] for row in self.tables["people"]}
        publications = {row["publication_id"] for row in self.tables["publications"]}
        activities = {row["activity_id"] for row in self.tables["activities"]}
        for table_rows in self.tables.values():
            for row in table_rows:
                for field, known in (
                    ("product_id", product_ids),
                    ("seller_id", seller_ids),
                    ("person_id", people),
                    ("publication_id", publications),
                    ("activity_id", activities),
                ):
                    if row.get(field) and row[field] not in known:
                        _fail(f"{field} references an unknown source-local entity")
        for left, right in self.config["cannot_link_products"]:
            if self.product_ids[left] == self.product_ids[right]:
                _fail("reviewed cannot-link products were merged")
        for group in self.config["unresolved_product_groups"]:
            if len({self.product_ids[key] for key in group}) != len(group):
                _fail("reviewed unresolved product group was merged")

    def run(self):
        self.ingest()
        self.prepare_listings()
        self.resolve_products()
        self.narratives()
        self.merge_reviewed_operators()
        tables = self.finish()
        self.validate()
        return tables


def build_tables(
    datasets: dict[str, dict],
    reviews: dict,
    geography: Any,
    input_metadata: dict[str, dict],
) -> dict[str, list[dict]]:
    return AtLocal(datasets, reviews, geography, input_metadata).run()

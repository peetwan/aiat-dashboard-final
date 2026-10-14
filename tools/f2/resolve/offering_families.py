"""Offering families (K07 counts families): ordinary variants of one product from one maker (colours,
sizes) and a catalogue family with its variants count once, while each offering stays its own entity.

The records of one offering are always one family. Reviewed family decisions (matching.json, entity
"offering_family") join offerings; no rule groups variants. Offerings are resolved first.
"""

from __future__ import annotations

from . import offerings

PREFIX, TABLE = "fam", "offerings"


def nodes(con) -> list[tuple[str, str]]:
    return offerings.nodes(con)


def pairs(con):
    first = {}
    for entity_id, source, record_id in con.execute(
            "SELECT entity_id, source, record_id FROM entity_members WHERE entity = 'offering' ORDER BY ALL").fetchall():
        if entity_id in first:
            yield first[entity_id], (source, record_id), "same", "same_offering"
        else:
            first[entity_id] = (source, record_id)

"""Source-specific connectors used by the central ingestion pipeline.

Each connector owns only the upstream request and completeness semantics.  The
orchestrator in :mod:`app.ingestion` remains responsible for evidence capture,
privacy projection, idempotent database writes, and run status.
"""

from app.connectors.base import ConnectorContext, DatasetRecord, nested_record_lists
from app.connectors.registry import ConnectorLoadError, load_connector

__all__ = [
    "ConnectorContext",
    "ConnectorLoadError",
    "DatasetRecord",
    "load_connector",
    "nested_record_lists",
]

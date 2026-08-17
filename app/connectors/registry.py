from __future__ import annotations

from importlib import import_module

from app.connectors.base import ConnectorProtocol


ENTRYPOINT_PREFIX = "app.connectors."


class ConnectorLoadError(RuntimeError):
    pass


def load_connector(entrypoint: str) -> ConnectorProtocol:
    """Load a reviewed connector from ``module:Class`` configuration.

    The allowlisted module prefix prevents ingestion configuration from turning
    into a generic import hook.  Entrypoints live in Git and are reviewed by CI.
    """

    if not isinstance(entrypoint, str) or ":" not in entrypoint:
        raise ConnectorLoadError("connector entrypoint must use app.connectors.module:Class")
    module_name, attribute = entrypoint.split(":", 1)
    if not module_name.startswith(ENTRYPOINT_PREFIX):
        raise ConnectorLoadError("connector entrypoint must live under app.connectors")
    if not attribute or not attribute.isidentifier():
        raise ConnectorLoadError("connector entrypoint class name is invalid")
    try:
        module = import_module(module_name)
        connector_type = getattr(module, attribute)
        connector = connector_type()
    except (ImportError, AttributeError, TypeError) as exc:
        raise ConnectorLoadError(f"cannot load connector {entrypoint}: {exc}") from exc
    if not isinstance(getattr(connector, "driver_name", None), str):
        raise ConnectorLoadError(f"connector {entrypoint} has no driver_name")
    if not callable(getattr(connector, "fetch", None)):
        raise ConnectorLoadError(f"connector {entrypoint} has no fetch(context) method")
    return connector

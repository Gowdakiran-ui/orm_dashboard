"""FastAPI constructor arguments that switch the interactive docs and the schema on or off (settings.ENABLE_API_DOCS)."""


def docs_kwargs(enabled: bool) -> dict:
    """Off: /docs, /redoc and /openapi.json answer 404. On: FastAPI's defaults."""
    if enabled:
        return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}
    return {"docs_url": None, "redoc_url": None, "openapi_url": None}

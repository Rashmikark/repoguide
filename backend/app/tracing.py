import logging

from langfuse import Langfuse, get_client

from backend.app.config import settings

log = logging.getLogger("uvicorn.error")

TRACING_ENABLED = bool(settings.langfuse_public_key and settings.langfuse_secret_key)

if TRACING_ENABLED:
    # Pass keys explicitly: they live in .env, which only our Settings reads,
    # so the SDK would not find them in the environment on its own.
    Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )

langfuse = get_client()   # the same client everywhere in the app

_warned: set[str] = set()


def _safe(method_name: str, **kwargs):
    """Tracing must never break a request.
    The method is looked up INSIDE the try, so even a method that does not
    exist in this SDK version cannot raise. Each failure is logged once."""
    try:
        return getattr(langfuse, method_name)(**kwargs)
    except Exception as e:
        if method_name not in _warned:
            _warned.add(method_name)
            log.warning("tracing call %s failed (ignored): %s", method_name, e)
        return None


def trace_generation(**kwargs) -> None:
    _safe("update_current_generation", **kwargs)


def trace_span(**kwargs) -> None:
    _safe("update_current_span", **kwargs)


def trace_request(**kwargs) -> None:
    """Input/output/metadata for the whole request. In current SDKs the trace
    shows its root observation's input/output, so we update the root span."""
    kwargs.pop("name", None)   # the root span already has its name from @observe
    kwargs.pop("tags", None)   # tags need a different API; the mode is in metadata
    _safe("update_current_span", **kwargs)


def current_trace_id() -> str | None:
    return _safe("get_current_trace_id")
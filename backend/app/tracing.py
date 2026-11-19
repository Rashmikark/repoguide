from langfuse import Langfuse, get_client

from backend.app.config import settings

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
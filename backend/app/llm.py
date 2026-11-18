import time

from google import genai
from google.genai import errors, types

from backend.app.config import settings

MAX_RETRIES = 4

_client = genai.Client(
    api_key=settings.gemini_api_key,
    http_options=types.HttpOptions(timeout=60_000),
)


def generate(prompt: str, *, json_schema=None, temperature: float = 0.0) -> tuple[str, dict]:
    """One Gemini call with retries. Returns (text, usage)."""
    cfg = {"temperature": temperature}
    if json_schema is not None:
        cfg["response_mime_type"] = "application/json"
        cfg["response_schema"] = json_schema

    for attempt in range(MAX_RETRIES):
        try:
            resp = _client.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(**cfg),
            )
            u = resp.usage_metadata
            usage = {
                "model": settings.gemini_model,
                "input_tokens": (u.prompt_token_count or 0) if u else 0,
                "output_tokens": (u.candidates_token_count or 0) if u else 0,
            }
            return resp.text or "", usage
        except Exception as e:
            is_api_error = isinstance(e, errors.APIError)
            retryable = (not is_api_error) or e.code in (429, 503)
            if retryable and attempt < MAX_RETRIES - 1:
                wait = 5 * 2 ** attempt
                reason = e.code if is_api_error else type(e).__name__
                print(f"  LLM call failed ({reason}), retrying in {wait}s")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("unreachable")
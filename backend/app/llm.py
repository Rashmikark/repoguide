import time

from google import genai
from google.genai import errors, types
from langfuse import observe

from backend.app.config import settings
from backend.app.tracing import trace_generation

MAX_RETRIES = 4

_client = genai.Client(
    api_key=settings.gemini_api_key,
    http_options=types.HttpOptions(timeout=60_000),
)


@observe(as_type="generation", name="gemini.generate", capture_input=False, capture_output=False)
def generate(prompt: str, *, json_schema=None, temperature: float = 0.0) -> tuple[str, dict]:
    """One Gemini call with retries. Returns (text, usage). Recorded in Langfuse."""
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
            text = resp.text or ""
            trace_generation(
                model=settings.gemini_model,
                input=prompt,
                output=text,
                usage_details={
                    "input_tokens": usage["input_tokens"],
                    "output_tokens": usage["output_tokens"],
                },
                metadata={"attempts": attempt + 1, "json_output": json_schema is not None},
            )
            return text, usage
        except Exception as e:
            is_api_error = isinstance(e, errors.APIError)
            retryable = (not is_api_error) or e.code in (429, 503)
            if retryable and attempt < MAX_RETRIES - 1:
                wait = 5 * 2 ** attempt
                reason = e.code if is_api_error else type(e).__name__
                print(f"  LLM call failed ({reason}), retrying in {wait}s")
                time.sleep(wait)
                continue
            trace_generation(
                model=settings.gemini_model,
                input=prompt,
                level="ERROR",
                status_message=f"{type(e).__name__}: {e}"[:500],
                metadata={"attempts": attempt + 1},
            )
            raise
    raise RuntimeError("unreachable")
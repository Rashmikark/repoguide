import time
from collections import deque

from google import genai
from google.genai import errors, types

from backend.app.config import settings

BATCH_SIZE = 50
MAX_CHARS = 6000          # stay well under the embedding model's input limit
MAX_RETRIES = 5

_client = genai.Client(
    api_key=settings.gemini_api_key,
    http_options=types.HttpOptions(timeout=60_000),   # milliseconds
)

_sent: deque[tuple[float, int]] = deque()   # (time sent, number of texts)
wait_seconds = 0.0                           # total time spent waiting on limits


def chunk_embedding_text(path: str, kind: str, symbol: str | None, content: str) -> str:
    header = f"File: {path}\nKind: {kind}"
    if symbol:
        header += f"\nSymbol: {symbol}"
    return f"{header}\n\n{content}"


def embed_texts(texts: list[str], task_type: str) -> list[list[float]]:
    size = min(BATCH_SIZE, settings.embed_texts_per_minute)
    vectors: list[list[float]] = []
    for i in range(0, len(texts), size):
        batch = [t[:MAX_CHARS] for t in texts[i:i + size]]
        _pace(len(batch))
        vectors.extend(_embed_batch(batch, task_type))
    return vectors


def _pace(n: int) -> None:
    """Block until sending n more texts keeps us under the per-minute limit."""
    global wait_seconds
    limit = settings.embed_texts_per_minute
    while True:
        now = time.monotonic()
        while _sent and now - _sent[0][0] >= 60:
            _sent.popleft()
        if sum(k for _, k in _sent) + n <= limit:
            _sent.append((now, n))
            return
        pause = 60 - (now - _sent[0][0]) + 0.5
        print(f"  pacing: waiting {pause:.0f}s to stay under {limit} texts/min")
        wait_seconds += pause
        time.sleep(pause)


def _embed_batch(batch: list[str], task_type: str) -> list[list[float]]:
    global wait_seconds
    for attempt in range(MAX_RETRIES):
        try:
            result = _client.models.embed_content(
                model=settings.embed_model,
                contents=batch,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=settings.embed_dim,
                ),
            )
            vectors = [e.values for e in result.embeddings]
            if len(vectors) != len(batch) or any(len(v) != settings.embed_dim for v in vectors):
                raise RuntimeError("Embedding count or dimension mismatch")
            return vectors
        except Exception as e:
            is_api_error = isinstance(e, errors.APIError)
            retryable = (not is_api_error) or e.code in (429, 503)
            if retryable and attempt < MAX_RETRIES - 1:
                wait = 5 * 2 ** attempt
                reason = e.code if is_api_error else type(e).__name__
                print(f"  embedding call failed ({reason}), retrying in {wait}s")
                wait_seconds += wait
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("unreachable")
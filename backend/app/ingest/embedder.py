import time

from google import genai
from google.genai import errors, types

from backend.app.config import settings

BATCH_SIZE = 50
MAX_CHARS = 6000          # stay well under the embedding model's input limit
MAX_RETRIES = 5

_client = genai.Client(api_key=settings.gemini_api_key)


def chunk_embedding_text(path: str, kind: str, symbol: str | None, content: str) -> str:
    header = f"File: {path}\nKind: {kind}"
    if symbol:
        header += f"\nSymbol: {symbol}"
    return f"{header}\n\n{content}"


def embed_texts(texts: list[str], task_type: str) -> list[list[float]]:
    vectors: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = [t[:MAX_CHARS] for t in texts[i:i + BATCH_SIZE]]
        vectors.extend(_embed_batch(batch, task_type))
    return vectors


def _embed_batch(batch: list[str], task_type: str) -> list[list[float]]:
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
        except errors.APIError as e:
            if e.code in (429, 503) and attempt < MAX_RETRIES - 1:
                wait = 5 * 2 ** attempt
                print(f"  embedding API returned {e.code}, retrying in {wait}s")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("unreachable")
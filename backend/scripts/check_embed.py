import sys

from google import genai
from google.genai import types

from backend.app.config import settings

model = sys.argv[1]
client = genai.Client(api_key=settings.gemini_api_key)

result = client.models.embed_content(
    model=model,
    contents="def retry(job): schedule the job again with backoff",
    config=types.EmbedContentConfig(output_dimensionality=768),
)
values = result.embeddings[0].values
print("model:", model)
print("dimension:", len(values))
print("first 5 numbers:", [round(v, 4) for v in values[:5]])
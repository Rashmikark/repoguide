from google import genai

from backend.app.config import settings

client = genai.Client(api_key=settings.gemini_api_key)

response = client.models.generate_content(
    model=settings.gemini_model,
    contents="In one sentence: what is retrieval-augmented generation?",
)
print(response.text)
"""
Generates text embeddings using OpenAI's embedding API.
Used to store semantic representations of review comments
and to find similar past issues via vector similarity search.
"""
import logging

from openai import AsyncOpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=settings.openai_api_key)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536


async def embed_text(text: str) -> list[float]:
    """Return a 1536-dimensional embedding vector for the given text."""
    response = await _client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding

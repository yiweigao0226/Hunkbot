"""
Provider-agnostic LLM interface.
Supports OpenAI and Anthropic. Controlled via LLM_PROVIDER env var.
"""
import json
import logging
from abc import ABC, abstractmethod

import anthropic
from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, system: str, user: str) -> str:
        """Return raw JSON string from LLM."""
        pass


class OpenAIProvider(LLMProvider):
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def complete(self, system: str, user: str) -> str:
        from app.core.models import PRReviewResult
        completion = await self.client.beta.chat.completions.parse(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format=PRReviewResult,
            temperature=0.2,
        )
        return completion.choices[0].message.content


class AnthropicProvider(LLMProvider):
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def complete(self, system: str, user: str) -> str:
        message = await self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text


def get_provider() -> LLMProvider:
    if settings.llm_provider == "anthropic":
        logger.info("Using Anthropic provider")
        return AnthropicProvider()
    logger.info("Using OpenAI provider")
    return OpenAIProvider()
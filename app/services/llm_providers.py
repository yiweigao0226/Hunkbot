"""
Provider-agnostic LLM interface.
Supports OpenAI and Anthropic. Controlled via LLM_PROVIDER env var.

Retry strategy:
- Transient errors (rate limit, timeout, connection): exponential backoff, 3 attempts
- Validation errors: one repair retry with strict correction prompt
- Fatal errors: raise immediately
"""
import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Union

import anthropic
from openai import AsyncOpenAI, RateLimitError, APITimeoutError, APIConnectionError

from app.core.config import settings
from app.core.models import PRReviewResult

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, system: str, user: str) -> Union["PRReviewResult", str]:
        """Return parsed PRReviewResult object or raw JSON string from LLM."""
        pass


class OpenAIProvider(LLMProvider):
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.max_retries = 3
        self.base_wait = 1  # seconds

    async def complete(self, system: str, user: str) -> PRReviewResult:
        """Call GPT-4o with structured outputs. Returns parsed object directly.
        
        Retries on transient errors (rate limit, timeout, connection) with exponential backoff.
        """
        for attempt in range(self.max_retries):
            try:
                completion = await self.client.beta.chat.completions.parse(
                    model=settings.openai_model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format=PRReviewResult,
                    temperature=0.2,
                )
                # OpenAI's structured output parsing validates during parse() call
                # .parsed gives us the validated object directly
                parsed = completion.choices[0].message.parsed
                if parsed is None:
                    raise ValueError("OpenAI returned None for parsed response")
                logger.info(f"OpenAI structured output parsed successfully (attempt {attempt + 1})")
                return parsed
            except (RateLimitError, APITimeoutError, APIConnectionError) as e:
                if attempt == self.max_retries - 1:
                    logger.error(f"OpenAI transient error after {self.max_retries} attempts: {e}")
                    raise
                wait_time = self.base_wait * (2 ** attempt)
                logger.warning(
                    f"OpenAI transient error (attempt {attempt + 1}/{self.max_retries}): {type(e).__name__}. "
                    f"Retrying in {wait_time}s..."
                )
                await asyncio.sleep(wait_time)
            except Exception as e:
                # Validation or other fatal errors — don't retry
                logger.error(f"OpenAI fatal error: {type(e).__name__}: {e}")
                raise


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
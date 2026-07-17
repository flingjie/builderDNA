"""LLM Client — a utility, not a layer.

Provides the LLMClient Protocol and an OpenAI implementation.
Called by insight/classifier and opportunity/detector only.
"""

import json
import time
from typing import Any, Protocol

from openai import APIError, OpenAI


class LLMError(Exception):
    """Raised when an LLM call fails after all retries."""


class LLMClient(Protocol):
    """Protocol for LLM interaction.

    The LLM is a utility — like a database or a math library.
    Any provider can implement this protocol.
    """

    def complete(self, prompt: str, response_format: type) -> Any:
        """Call the LLM and return a parsed response of the given type.

        Args:
            prompt: The prompt to send.
            response_format: A type to parse the response into (currently unused
                at the protocol level; implementations handle parsing).

        Returns:
            Parsed response object.

        Raises:
            LLMError: On failure after all retries.
        """
        ...


DEFAULT_RETRY_CONFIG = {
    "max_retries": 2,
    "base_delay": 1.0,
    "max_delay": 30.0,
}


class OpenAIClient:
    """OpenAI implementation of LLMClient.

    Handles API calls with exponential backoff retry for transient errors
    and response parsing with one retry on parse failure.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        retry_config: dict | None = None,
    ):
        """Initialize the OpenAI client.

        Args:
            api_key: OpenAI API key.
            model: Model ID to use.
            retry_config: Override default retry settings.
        """
        self._client = OpenAI(api_key=api_key)
        self.model = model
        self.retry = retry_config or DEFAULT_RETRY_CONFIG

    def complete(self, prompt: str, response_format: type) -> Any:
        """Call OpenAI chat completions and parse the structured response.

        The prompt should instruct the model to return JSON matching
        the expected schema. This method wraps the call with retry logic.

        Args:
            prompt: The full prompt text.
            response_format: Expected output type (used only in prompt; the
                actual response is parsed from JSON).

        Returns:
            Parsed JSON response as a dict or list.

        Raises:
            LLMError: If the call or parsing fails after all retries.
        """
        last_error = None
        for attempt in range(self.retry["max_retries"] + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an expert technical analyst. Always respond with valid JSON exactly matching the requested schema.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                )
                content = response.choices[0].message.content
                return self._parse_response(content, prompt, response_format)
            except APIError as e:
                last_error = e
                if attempt < self.retry["max_retries"]:
                    delay = min(
                        self.retry["base_delay"] * (2**attempt),
                        self.retry["max_delay"],
                    )
                    time.sleep(delay)
                else:
                    raise LLMError(
                        f"LLM call failed after {self.retry['max_retries'] + 1} attempts: {e}"
                    ) from e

        raise LLMError(f"LLM call failed: {last_error}")

    def _parse_response(
        self, raw: str, prompt: str, response_format: type
    ) -> Any:
        """Parse LLM JSON response, with one retry on failure.

        Args:
            raw: Raw response text from the LLM.
            prompt: Original prompt (for stricter retry).
            response_format: Expected output type.

        Returns:
            Parsed dict or list.

        Raises:
            LLMError: If parsing fails after retry.
        """
        for attempt in range(2):
            try:
                # Strip markdown code fences if present
                cleaned = raw.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1]
                    if cleaned.endswith("```"):
                        cleaned = cleaned[: cleaned.rfind("```")].strip()
                return json.loads(cleaned)
            except json.JSONDecodeError:
                if attempt == 0:
                    # Retry with stricter prompt
                    retry_response = self._client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": "You MUST respond with ONLY valid JSON. No markdown fences, no commentary, just the JSON object."},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.1,
                    )
                    raw = retry_response.choices[0].message.content
                else:
                    raise LLMError(
                        f"Failed to parse LLM response after retry. Raw: {raw[:200]}"
                    )
        return None  # unreachable

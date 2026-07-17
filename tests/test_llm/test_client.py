"""Tests for LLM client."""

import json

import httpx
import pytest
from openai import APIError

from llm.client import (
    LLMError,
    OpenAIClient,
    DEFAULT_RETRY_CONFIG,
)


class FakeResponse:
    """Simulates an OpenAI API response."""
    def __init__(self, content: str):
        self.choices = [
            type("Choice", (), {"message": type("Message", (), {"content": content})})()
        ]


def _api_error(msg="test error"):
    """Create an APIError for testing."""
    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return APIError(msg, request=req, body=None)


class TestOpenAIClient:
    def test_complete_success(self, mocker):
        mock_client_cls = mocker.patch("llm.client.OpenAI")
        mock_client = mock_client_cls.return_value
        mock_client.chat.completions.create.return_value = FakeResponse(
            json.dumps({"items": [{"name": "test", "score": 5}]})
        )

        client = OpenAIClient(api_key="sk-test", model="gpt-4o")
        result = client.complete("Test prompt", response_format=dict)

        assert result is not None
        mock_client.chat.completions.create.assert_called_once()

    def test_complete_retry_then_success(self, mocker):
        mock_client_cls = mocker.patch("llm.client.OpenAI")
        mock_client = mock_client_cls.return_value
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 2:
                raise _api_error("temporary error")
            return FakeResponse(json.dumps({"items": []}))

        mock_client.chat.completions.create.side_effect = side_effect

        client = OpenAIClient(
            api_key="sk-test",
            model="gpt-4o",
            retry_config={**DEFAULT_RETRY_CONFIG, "max_retries": 2, "base_delay": 0.01},
        )
        result = client.complete("prompt", response_format=dict)
        assert result is not None
        assert call_count[0] == 2

    def test_complete_max_retries_exceeded(self, mocker):
        mock_client_cls = mocker.patch("llm.client.OpenAI")
        mock_client = mock_client_cls.return_value
        mock_client.chat.completions.create.side_effect = _api_error("persistent error")

        client = OpenAIClient(
            api_key="sk-test",
            model="gpt-4o",
            retry_config={**DEFAULT_RETRY_CONFIG, "max_retries": 2, "base_delay": 0.01},
        )
        with pytest.raises(LLMError, match="LLM call failed after"):
            client.complete("prompt", response_format=dict)

    def test_parse_failure_retries(self, mocker):
        mock_client_cls = mocker.patch("llm.client.OpenAI")
        mock_client = mock_client_cls.return_value
        mock_client.chat.completions.create.return_value = FakeResponse(
            "not valid json {{{"
        )

        client = OpenAIClient(
            api_key="sk-test",
            model="gpt-4o",
            retry_config={**DEFAULT_RETRY_CONFIG, "max_retries": 1, "base_delay": 0.01},
        )
        with pytest.raises(LLMError, match="Failed to parse LLM response"):
            client.complete("prompt", response_format=dict)

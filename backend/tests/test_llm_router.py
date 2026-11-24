import unittest
import httpx
from openai import RateLimitError, APIStatusError
from types import SimpleNamespace
from unittest.mock import patch

from app.core.llm.claude_client import _call, _try_provider, chat


class _FakeCompletions:
    def __init__(self, response):
        self.response = response

    def create(self, **_kwargs):
        return self.response


def _fake_client(response):
    return SimpleNamespace(
        chat=SimpleNamespace(completions=_FakeCompletions(response))
    )


class LlmRouterTests(unittest.TestCase):
    def test_mixed_provider_errors_preserve_causes(self):
        quota = APIStatusError('monthly included credits depleted', response=httpx.Response(402, request=httpx.Request('POST', 'https://example.test')), body=None)
        missing = APIStatusError('model unavailable for free', response=httpx.Response(404, request=httpx.Request('POST', 'https://example.test')), body=None)
        with (
            patch('app.core.llm.claude_client.settings.configured_providers', return_value=['huggingface', 'openrouter']),
            patch('app.core.llm.claude_client._try_provider', side_effect=[quota, missing]),
        ):
            with self.assertRaises(RuntimeError) as caught:
                chat('system', [], agent_id='doc-controller')
        self.assertIn('huggingface:', str(caught.exception))
        self.assertIn('model unavailable for free', str(caught.exception))
        self.assertNotIn('Every configured', str(caught.exception))
        self.assertNotIn('Groq', str(caught.exception))

    def test_temporary_rate_limit_retries_but_hard_quota_does_not(self):
        for message, expected_calls in [('Too many requests', 2), ('quota exceeded', 1)]:
            error = RateLimitError(message, response=httpx.Response(429, request=httpx.Request('POST', 'https://example.test')), body=None)
            with (
                patch('app.core.llm.claude_client.model_for', return_value='model'),
                patch('app.core.llm.claude_client.settings.models_for', return_value={'general': 'model'}),
                patch('app.core.llm.claude_client._call', side_effect=[error, 'OK']) as call,
                patch('app.core.llm.claude_client.time.sleep'),
            ):
                if expected_calls == 1:
                    with self.assertRaises(RateLimitError):
                        _try_provider('test', 'system', [], 100, 'technical-writer')
                else:
                    self.assertEqual(_try_provider('test', 'system', [], 100, 'technical-writer'), 'OK')
                self.assertEqual(call.call_count, expected_calls)

    def test_missing_choices_becomes_provider_failure(self):
        response = SimpleNamespace(choices=None)
        with patch("app.core.llm.claude_client._client_for", return_value=_fake_client(response)):
            with self.assertRaisesRegex(RuntimeError, "provider returned no choices"):
                _call("test-provider", "test-model", "system", [{"role": "user", "content": "hi"}], 20)

    def test_empty_content_becomes_provider_failure(self):
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="  "))]
        )
        with patch("app.core.llm.claude_client._client_for", return_value=_fake_client(response)):
            with self.assertRaisesRegex(RuntimeError, "provider returned empty content"):
                _call("test-provider", "test-model", "system", [{"role": "user", "content": "hi"}], 20)

    def test_valid_content_is_returned(self):
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ACTIVE"))]
        )
        with patch("app.core.llm.claude_client._client_for", return_value=_fake_client(response)):
            self.assertEqual(
                _call("test-provider", "test-model", "system", [{"role": "user", "content": "hi"}], 20),
                "ACTIVE",
            )

    def test_empty_content_is_retried_on_same_provider(self):
        with (
            patch("app.core.llm.claude_client.model_for", return_value="test-model"),
            patch("app.core.llm.claude_client.settings.models_for", return_value={"general": "test-model"}),
            patch(
                "app.core.llm.claude_client._call",
                side_effect=[RuntimeError("[test-provider:test-model] provider returned empty content"), "ACTIVE"],
            ) as call,
            patch("app.core.llm.claude_client.time.sleep"),
        ):
            result = _try_provider(
                "test-provider", "system", [{"role": "user", "content": "hi"}], 20, "admin-hr"
            )

        self.assertEqual(result, "ACTIVE")
        self.assertEqual(call.call_count, 2)


if __name__ == "__main__":
    unittest.main()

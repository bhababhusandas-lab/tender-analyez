"""Stopping an analysis must stop the AI work, not just the job record."""
import asyncio
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from openai import APIConnectionError

from app.core.llm import claude_client
from app.core.llm.claude_client import (
    AI_UNAVAILABLE_MESSAGE, AICancelled, _try_provider, chat_async, user_facing_error,
)


class _SlowStream:
    """Mimics an OpenAI stream: one chunk every 50 ms until closed."""

    def __init__(self):
        self.closed = False
        self.chunks_sent = 0

    def __iter__(self):
        while not self.closed and self.chunks_sent < 200:
            time.sleep(0.05)
            self.chunks_sent += 1
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="word "))])

    def close(self):
        self.closed = True


def _client(stream):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: stream)))


class AICancellationTests(unittest.TestCase):
    def test_cancelling_the_task_closes_the_in_flight_stream(self):
        stream = _SlowStream()

        async def scenario():
            with (
                patch.object(claude_client.settings, "configured_providers", return_value=["ollama"]),
                patch.object(claude_client, "_client_for", return_value=_client(stream)),
            ):
                task = asyncio.create_task(chat_async("system", [{"role": "user", "content": "hi"}], agent_id="bid-manager"))
                await asyncio.sleep(0.2)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                await asyncio.sleep(0.2)  # let the worker thread observe the cancel

        asyncio.run(scenario())
        self.assertTrue(stream.closed, "stream should be closed so the server stops generating")
        self.assertLess(stream.chunks_sent, 20, "generation should stop soon after cancel, not run to the end")

    def test_cancel_skips_remaining_retries(self):
        calls = []
        cancel = threading.Event()

        def failing_call(*_args, **_kwargs):
            calls.append(1)
            cancel.set()  # user presses Stop while the first attempt is failing
            raise APIConnectionError(request=httpx.Request("POST", "http://ai.test"))

        with (
            patch.object(claude_client, "_call", side_effect=failing_call),
            patch.object(claude_client, "model_for", return_value="qwen3:8b"),
            patch.object(claude_client.settings, "models_for", return_value={"general": "qwen3:8b"}),
        ):
            started = time.monotonic()
            with self.assertRaises(AICancelled):
                _try_provider("ollama", "system", [], 100, "bid-manager", cancel)
        self.assertEqual(len(calls), 1, "no further attempts after Stop")
        self.assertLess(time.monotonic() - started, 0.5, "backoff sleep must end immediately on Stop")

    def test_customers_see_a_plain_message_for_provider_outages(self):
        raw = RuntimeError("All providers failed. ollama: [ollama:qwen3:8b] failed after 4 attempts: Connection error.")
        self.assertEqual(user_facing_error(raw), AI_UNAVAILABLE_MESSAGE)
        self.assertIn("took too long", user_facing_error(TimeoutError("Timed out after 600 seconds (attempt 2/2)")))
        self.assertEqual(user_facing_error(ValueError("Tender text is empty")), "Tender text is empty")


if __name__ == "__main__":
    unittest.main()

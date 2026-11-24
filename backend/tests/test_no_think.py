from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.core.llm import claude_client


def _reply(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def test_qwen3_on_ollama_turns_thinking_off():
    client = MagicMock()
    client.chat.completions.create.return_value = _reply("ok")
    with patch.object(claude_client, "_client_for", return_value=client):
        claude_client._call("ollama", "qwen3:8b", "sys", [{"role": "user", "content": "hi"}], 100)
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["extra_body"] == {"reasoning_effort": "none"}
    assert kwargs["messages"][-1]["content"].endswith("/no_think")


def test_other_providers_get_no_extra_body():
    client = MagicMock()
    client.chat.completions.create.return_value = _reply("ok")
    with patch.object(claude_client, "_client_for", return_value=client):
        claude_client._call("groq", "llama-3.3-70b", "sys", [{"role": "user", "content": "hi"}], 100)
    assert "extra_body" not in client.chat.completions.create.call_args.kwargs

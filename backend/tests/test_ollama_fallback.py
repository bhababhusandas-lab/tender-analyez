"""OLLAMA_BASE_URL may list a main and a backup GPU; the first that answers is used."""
from unittest.mock import patch

from app.core.llm import claude_client as cc

SG = "http://10.0.0.1:11434/v1"
MUM = "http://10.0.0.2:11434/v1"


def _reset():
    cc._ollama_pick = None


def test_single_url_is_used_without_probing():
    _reset()
    with patch.object(cc.settings, "ollama_base_url", SG), \
         patch.object(cc, "_ollama_reachable", side_effect=AssertionError("no probe")):
        assert cc._ollama_base_url() == SG


def test_backup_used_when_main_is_off():
    _reset()
    with patch.object(cc.settings, "ollama_base_url", f"{SG}, {MUM}"), \
         patch.object(cc, "_ollama_reachable", side_effect=lambda u: u == MUM):
        assert cc._ollama_base_url() == MUM


def test_main_preferred_when_both_answer():
    _reset()
    with patch.object(cc.settings, "ollama_base_url", f"{SG},{MUM}"), \
         patch.object(cc, "_ollama_reachable", return_value=True):
        assert cc._ollama_base_url() == SG


def test_main_used_when_none_answer():
    _reset()
    with patch.object(cc.settings, "ollama_base_url", f"{SG},{MUM}"), \
         patch.object(cc, "_ollama_reachable", return_value=False):
        assert cc._ollama_base_url() == SG


def test_choice_is_cached_then_rechecked():
    _reset()
    up = {SG: False, MUM: True}
    with patch.object(cc.settings, "ollama_base_url", f"{SG},{MUM}"), \
         patch.object(cc, "_ollama_reachable", side_effect=lambda u: up[u]):
        assert cc._ollama_base_url() == MUM
        up[SG] = True
        assert cc._ollama_base_url() == MUM          # cached
        cc._ollama_pick = (cc._ollama_pick[0] - 61, cc._ollama_pick[1])
        assert cc._ollama_base_url() == SG           # rechecked after a minute


def test_client_follows_the_chosen_server():
    _reset()
    with patch.object(cc.settings, "ollama_base_url", f"{SG},{MUM}"), \
         patch.object(cc, "_ollama_reachable", side_effect=lambda u: u == MUM):
        client = cc._client_for("ollama")
    assert str(client.base_url).rstrip("/") == MUM
    _reset()

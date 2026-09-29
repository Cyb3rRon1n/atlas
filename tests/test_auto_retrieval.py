from atlas.config.models import AtlasConfig
from atlas.intelligence.agent import AtlasAgent
from atlas.intelligence.providers import ChatReply
from atlas.knowledge.notes import search_notes


class _Capture:

    def __init__(self):
        self.seen = None

    def converse(self, messages, tools):
        self.seen = messages
        return ChatReply(text="ok")


def _setup(tmp_path, **knowledge):

    (tmp_path / "incidents").mkdir()
    (tmp_path / "incidents" / "torrents.md").write_text(
        "# Torrents stuck at downloading metadata\n\nCause: VPN server without P2P; check qBit firewalled.\n")
    (tmp_path / "vulcan-docs.md").write_text("# Torrents\n\nvulcan runs qbittorrent behind gluetun. torrents torrents.\n")
    (tmp_path / "HOSTS.md").write_text("cyberpac = 192.168.10.157\n")
    config = AtlasConfig()
    for key, value in knowledge.items():
        setattr(config.knowledge, key, value)
    provider = _Capture()
    return AtlasAgent(provider, config), provider


def test_notes_and_pinned_attached_to_latest_question_on_a_copy(tmp_path):

    agent, provider = _setup(tmp_path, notes_paths=[str(tmp_path)], pinned_paths=[str(tmp_path / "HOSTS.md")])
    messages = [{"role": "user", "content": "torrents stuck at downloading metadata - why?"}]

    agent.converse(messages)

    sent = provider.seen[-1]["content"]
    assert "cyberpac = 192.168.10.157" in sent
    assert "VPN server without P2P" in sent
    assert sent.endswith("Question: torrents stuck at downloading metadata - why?")
    assert messages[0]["content"] == "torrents stuck at downloading metadata - why?"


def test_nothing_configured_sends_messages_unchanged(tmp_path):

    agent, provider = _setup(tmp_path)
    messages = [{"role": "user", "content": "hi"}]

    agent.converse(messages)

    assert provider.seen is messages


def test_auto_context_zero_keeps_only_pinned(tmp_path):

    agent, provider = _setup(tmp_path, notes_paths=[str(tmp_path)], auto_context=0,
                             pinned_paths=[str(tmp_path / "HOSTS.md")])

    agent.converse([{"role": "user", "content": "torrents metadata"}])

    assert "VPN server" not in provider.seen[-1]["content"]
    assert "192.168.10.157" in provider.seen[-1]["content"]


def test_case_files_outrank_docs_and_stopwords_are_ignored(tmp_path):

    _setup(tmp_path)

    hits = search_notes([str(tmp_path)], "what should I check first for torrents metadata")["results"]

    assert hits[0]["file"].endswith("incidents/torrents.md")
    assert search_notes([str(tmp_path)], "what should I check")["results"] == []

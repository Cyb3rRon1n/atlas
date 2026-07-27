from atlas.config.loader import load_config
from atlas.config.models import AtlasConfig


def test_load_config_defaults_when_no_file(isolated_cwd):

    config = load_config()

    assert config == AtlasConfig()
    assert config.name == "atlas-node"
    assert config.intelligence.provider == "anthropic"
    assert config.intelligence.model == "claude-opus-5"


def test_load_config_reads_atlas_yaml(isolated_cwd):

    (isolated_cwd / "atlas.yaml").write_text(
        "name: sentinel\n"
        "discovery:\n"
        "  hardware: false\n"
        "intelligence:\n"
        "  provider: ollama\n"
        "  model: llama3.1\n"
    )

    config = load_config()

    assert config.name == "sentinel"
    assert config.discovery.hardware is False
    assert config.discovery.storage is True
    assert config.intelligence.provider == "ollama"
    assert config.intelligence.model == "llama3.1"

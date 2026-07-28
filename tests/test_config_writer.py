from atlas.config.loader import load_config
from atlas.config.models import AtlasConfig, ProxmoxConfig
from atlas.config.writer import write_config, write_setup_log


def test_write_config_round_trips_through_load_config(isolated_cwd):

    config = AtlasConfig(
        name="sentinel",
        proxmox=ProxmoxConfig(
            enabled=True,
            host="192.168.1.10",
            user="atlas@pve",
            token_name="atlas-token",
            token_value="secret-value"
        )
    )

    write_config(config)

    loaded = load_config()

    assert loaded.name == "sentinel"
    assert loaded.proxmox.enabled is True
    assert loaded.proxmox.host == "192.168.1.10"
    assert loaded.proxmox.token_value == "secret-value"


def test_write_setup_log_creates_directory_and_file(isolated_cwd):

    assert not (isolated_cwd / "logs").exists()

    log_path = write_setup_log(["line one", "line two"])

    assert log_path.parent.resolve() == isolated_cwd / "logs"
    assert log_path.name.startswith("atlas-init-")
    assert log_path.name.endswith(".log")
    assert log_path.read_text() == "line one\nline two\n"

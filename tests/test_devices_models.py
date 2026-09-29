from sqlalchemy import create_engine, inspect, text

from atlas.config.models import AtlasConfig
from atlas.database.engine import enable_wal
from atlas.database.models import Base
from atlas.devices import Sighting


def test_new_tables_exist(temp_db):

    tables = set(inspect(temp_db).get_table_names())

    assert {"devices", "sightings", "source_runs", "notifications"} <= tables


def test_enable_wal_sets_journal_mode_and_busy_timeout(tmp_path):

    engine = create_engine(f"sqlite:///{tmp_path / 'wal.db'}")
    enable_wal(engine)
    Base.metadata.create_all(engine)

    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert connection.execute(text("PRAGMA busy_timeout")).scalar() == 5000


def test_scan_and_notify_config_defaults():

    config = AtlasConfig()

    assert config.scan.enabled is True
    assert config.scan.subnets == []
    assert config.scan.interval_minutes == 15
    assert config.notify.signal.url == ""


def test_sighting_defaults_are_independent():

    first, second = Sighting("lan", "aa"), Sighting("lan", "bb")
    first.detail["x"] = 1

    assert second.detail == {}

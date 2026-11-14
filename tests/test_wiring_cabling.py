from atlas.wiring.cabling import load_cabling


def test_missing_file_is_empty(tmp_path):
    assert load_cabling(tmp_path / "nope.yaml") == {"panels": [], "ports": {}, "error": None}


def test_loads_panels_and_port_labels(tmp_path):
    path = tmp_path / "cabling.yaml"
    path.write_text("""
panels:
  - name: PP1
    ports:
      1: {switch: core-switch, port: gi1, label: "Office A", color: blue}
      2: {switch: core-switch, port: gi2}
ports:
  "gateway:Port 3": {label: "Wi-Fi bridge"}
""")
    result = load_cabling(path)
    assert result["error"] is None
    assert result["panels"][0] == {"panel": "PP1", "port": 1, "switch": "core-switch", "switch_port": "gi1",
                                   "label": "Office A", "color": "blue"}
    assert result["panels"][1]["label"] == "" and result["panels"][1]["color"] == ""
    assert result["ports"] == {"gateway:Port 3": {"label": "Wi-Fi bridge", "color": ""}}


def test_bad_yaml_reports_line(tmp_path):
    path = tmp_path / "cabling.yaml"
    path.write_text("panels:\n  - name: PP1\n    ports: {1: [\n")
    result = load_cabling(path)
    assert result["panels"] == [] and result["error"].startswith("cabling.yaml line ")


def test_bad_entry_skipped_with_error(tmp_path):
    path = tmp_path / "cabling.yaml"
    path.write_text("panels:\n  - name: PP1\n    ports:\n      1: {port: gi1}\n      2: {switch: s, port: gi2}\n")
    result = load_cabling(path)
    assert [e["port"] for e in result["panels"]] == [2]
    assert "PP1 port 1" in result["error"]
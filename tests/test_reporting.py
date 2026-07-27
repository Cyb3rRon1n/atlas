from atlas.reporting.generator import generate_report


SAMPLE_INVENTORY = {
    "system": {"hostname": "sentinel", "os": "Linux"},
    "hardware": {"cpu": {"physical_cores": 4}},
    "storage": [{"device": "/dev/sda1"}],
    "network": {"hostname": "sentinel"},
}


def test_generate_report_writes_expected_sections(isolated_cwd):

    output = generate_report(SAMPLE_INVENTORY)

    assert output.exists()
    assert output.resolve() == isolated_cwd / "reports" / "atlas-report.md"

    content = output.read_text()

    assert "# Atlas Infrastructure Report" in content
    assert "## System" in content
    assert "**hostname**: sentinel" in content
    assert "## Hardware" in content
    assert "## Storage" in content
    assert "## Network" in content

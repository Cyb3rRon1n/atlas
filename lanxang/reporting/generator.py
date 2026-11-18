from pathlib import Path
from datetime import datetime


REPORT_DIRECTORY = Path("reports")


def generate_report(inventory):

    REPORT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True
    )

    report = []

    report.append(
        "# Atlas Infrastructure Report\n"
    )

    report.append(
        f"Generated: {datetime.now()}\n"
    )

    report.append(
        "## System\n"
    )

    system = inventory.get(
        "system",
        {}
    )

    for key, value in system.items():
        report.append(
            f"- **{key}**: {value}"
        )

    report.append(
        "\n## Hardware\n"
    )

    hardware = inventory.get(
        "hardware",
        {}
    )

    report.append(
        str(hardware)
    )

    report.append(
        "\n## Storage\n"
    )

    report.append(
        str(
            inventory.get(
                "storage",
                []
            )
        )
    )

    report.append(
        "\n## Network\n"
    )

    report.append(
        str(
            inventory.get(
                "network",
                {}
            )
        )
    )

    output = (
        REPORT_DIRECTORY /
        "atlas-report.md"
    )

    output.write_text(
        "\n".join(report)
    )

    return output

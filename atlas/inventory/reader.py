from pathlib import Path
import yaml


def load_inventory():

    file = Path(
        "inventory/generated/system-inventory.yaml"
    )

    if not file.exists():
        return None

    with open(file) as f:
        data = yaml.safe_load(f)

    return data["data"]

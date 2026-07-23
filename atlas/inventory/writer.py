from pathlib import Path
import yaml

from atlas.inventory.models import Inventory


INVENTORY_PATH = Path(
    "inventory/generated"
)


def save_inventory(data: dict):

    INVENTORY_PATH.mkdir(
        parents=True,
        exist_ok=True
    )

    inventory = Inventory(
        created=str(
            __import__("datetime")
            .datetime.now()
        ),
        hostname=data["system"]["hostname"],
        data=data,
    )

    output = (
        INVENTORY_PATH /
        "system-inventory.yaml"
    )

    with open(output, "w") as file:
        yaml.dump(
            inventory.model_dump(),
            file,
            sort_keys=False
        )

    return output

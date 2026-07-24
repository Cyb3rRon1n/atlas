import importlib
import inspect
import pkgutil

from atlas.plugins.base import AtlasPlugin


def discover_plugins(package_name="atlas.plugins"):
    """
    Discover AtlasPlugin subclasses in the plugins package.
    """

    plugins = []

    package = importlib.import_module(package_name)

    for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
        if is_pkg:
            continue

        if module_name in {
            "base",
            "manager",
            "loader",
            "exceptions",
            "__init__",
        }:
            continue

        module = importlib.import_module(
            f"{package_name}.{module_name}"
        )

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, AtlasPlugin)
                and obj is not AtlasPlugin
            ):
                plugins.append(obj())

    return plugins

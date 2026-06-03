"""Auto-discover BaseFormatter subclasses in the formatter package."""

import importlib
import inspect
import pkgutil
import re
from pathlib import Path
from typing import Callable

from .core import BaseFormatter


def _class_name_to_mode(class_name: str) -> str:
    """Convert CamelCaseFormatter to kebab-case mode name.

    Examples:
        TextbookFormatter -> textbook
        RenjiaoHighschoolTextbookFormatter -> renjiao-highschool-textbook
        BeijingAlgebraFormatter -> beijing-algebra
    """
    name = class_name
    if name.endswith("Formatter"):
        name = name[: -len("Formatter")]
    name = re.sub(r"(?<=[a-z0-9])([A-Z])", r"-\1", name)
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", name)
    return name.lower()


def discover_formatters() -> dict[str, Callable[[], BaseFormatter]]:
    """Scan the formatter package for all BaseFormatter subclasses.

    Returns a dict mapping mode names (kebab-case) to factory callables.
    """
    formatters: dict[str, Callable[[], BaseFormatter]] = {}
    package_dir = Path(__file__).parent

    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(
                f".{module_info.name}", package=__package__
            )
        except Exception:
            continue

        for name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseFormatter)
                and obj is not BaseFormatter
                and not inspect.isabstract(obj)
            ):
                mode = _class_name_to_mode(name)
                formatters[mode] = lambda cls=obj: cls()

    return formatters

"""Expose the offline smoke test checks to pytest.

The checks themselves live in ``testing/offline_smoke.py`` so that they can also be
run without pytest (``python testing/offline_smoke.py``). This module only loads
them and parametrises them, which keeps both entry points in sync:

    pytest tests/test_offline_smoke.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
from typing import Any, Callable

import pytest

SMOKE_PATH = pathlib.Path(__file__).resolve().parents[1] / "testing" / "offline_smoke.py"


def _load_smoke() -> Any:
    """Import the smoke test module by path.

    The module must be registered in ``sys.modules`` before it is executed:
    ``dataclasses`` resolves the annotations of the test doubles through
    ``sys.modules[cls.__module__]`` (the module is ``__main__`` when the smoke test
    is run standalone, which is why this only matters under pytest).
    """
    spec = importlib.util.spec_from_file_location("offline_smoke", SMOKE_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - cannot happen
        raise RuntimeError(f"cannot load {SMOKE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


SMOKE = _load_smoke()


@pytest.mark.parametrize(
    ("title", "func"),
    SMOKE.CHECKS,
    ids=[title for title, _ in SMOKE.CHECKS],
)
def test_offline_smoke(title: str, func: Callable[[], Any]) -> None:
    """Run one offline smoke check (the id is the check title)."""
    result = func()
    if asyncio.iscoroutine(result):
        asyncio.run(result)

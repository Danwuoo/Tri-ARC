from __future__ import annotations

import logging
import pytest

from arc.core import ModuleLifecycleState
from arc.core.registry import ModuleRegistry, ModuleRegistryError


def build_logger() -> logging.Logger:
    logger = logging.getLogger("test.registry")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    return logger


def test_registry_bootstrap_success() -> None:
    config = {
        "global": {"device_map": {"dummy": "cpu:0"}},
        "modules": {
            "dummy": {
                "class": "tests.core.dummy_module.DummySolverModule",
            }
        },
    }
    registry = ModuleRegistry(config, logger=build_logger())
    registry.bootstrap()
    module = registry.get("dummy")
    assert module.state is ModuleLifecycleState.READY
    registry.shutdown()


def test_registry_respects_force_disable() -> None:
    config = {
        "modules": {
            "dummy": {
                "class": "tests.core.dummy_module.DummySolverModule",
                "enabled": True,
            }
        }
    }
    registry = ModuleRegistry(config, logger=build_logger(), force_disable=["dummy"])
    registry.bootstrap()
    assert "dummy" not in registry.active_modules()
    assert registry.disabled_modules()["dummy"] == "disabled_via_config"


def test_registry_requires_class_path() -> None:
    config = {"modules": {"broken": {}}}
    with pytest.raises(ModuleRegistryError):
        ModuleRegistry(config, logger=build_logger())

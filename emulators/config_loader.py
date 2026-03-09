"""Configuration loader for PulsarM emulators."""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config file. If None, uses config.yaml in same directory.

    Returns:
        Configuration dictionary.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        yaml.YAMLError: If config file is invalid YAML.
    """
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config


def get_device_config(config: dict[str, Any], device_type: str) -> dict[str, Any]:
    """Get configuration for a specific device type.

    Args:
        config: Full configuration dictionary.
        device_type: Device type key (e.g., 'water_meter_type_b', 'heat_meter').

    Returns:
        Device-specific configuration dictionary.

    Raises:
        KeyError: If device type not found in config.
    """
    if device_type not in config:
        raise KeyError(f"Device type '{device_type}' not found in configuration")

    return config[device_type]


def get_archive_config(config: dict[str, Any]) -> dict[str, Any]:
    """Get archive configuration.

    Args:
        config: Full configuration dictionary.

    Returns:
        Archive configuration dictionary.
    """
    return config.get("archives", {
        "hourly_records": 24,
        "daily_records": 7,
        "monthly_records": 3,
    })




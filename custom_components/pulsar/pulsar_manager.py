"""Represent manager of devices."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .connector import Connector
from .const import (
    CONF_DEVICE_CONFIG,
    CONF_DEVICE_OR_ADDRESS,
    CONF_NAME,
    CONF_SERIAL_ID,
    CONF_TYPE,
)
from .device_specs import DEVICE_TYPE_REGISTRY
from .exceptions import PulsarConnectionError, PulsarException
from .pulsardevice import PulsarDevice

_LOGGER = logging.getLogger(__name__)


class PulsarManager:
    """Manager for Pulsar devices."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize Pulsar manager."""
        self._hass = hass
        self.config_entry = config_entry
        self._devices: dict[str, PulsarDevice] = {}

        device_or_ipaddress: str = config_entry.data[CONF_DEVICE_OR_ADDRESS]

        self._connector = Connector(device_or_ipaddress, "connector")

        device_confs: dict[str, dict[str, Any]] = config_entry.data[CONF_DEVICE_CONFIG]

        for dev_id in device_confs:
            device_conf = device_confs[dev_id]
            device_type = device_conf[CONF_TYPE]

            if device_type not in DEVICE_TYPE_REGISTRY:
                _LOGGER.error("Unknown device type: %s", device_type)
                continue

            metadata = DEVICE_TYPE_REGISTRY[device_type]
            device = PulsarDevice(
                self._connector,
                metadata,
                device_conf[CONF_NAME],
                device_conf[CONF_SERIAL_ID],
            )
            self.add_device(dev_id, device)

    def get_device(self, device_id: str) -> PulsarDevice | None:
        """Get device by ID.

        Args:
            device_id: Device identifier.

        Returns:
            Device instance or None if not found.

        """
        return self._devices.get(device_id)

    def get_devices(self, device_ids: list[str] | None) -> dict[str, PulsarDevice]:
        """Get devices by IDs.

        Args:
            device_ids: List of device IDs, or None for all devices.

        Returns:
            Dictionary of device_id -> device.

        """
        if device_ids is None:
            return self._devices.copy()
        return {
            dev_id: self._devices[dev_id]
            for dev_id in device_ids
            if dev_id in self._devices
        }

    def add_device(self, dev_id: str, device: PulsarDevice) -> None:
        """Add device to manager.

        Args:
            dev_id: Device identifier.
            device: Device instance.

        Raises:
            PulsarException: If device already exists.

        """
        if dev_id in self._devices:
            raise PulsarException(f"Device {dev_id} already exists")

        self._devices[dev_id] = device

    def remove_device(self, device_id: str) -> None:
        """Remove device from manager.

        Args:
            device_id: Device identifier.

        Raises:
            PulsarException: If device does not exist.

        """
        if device_id not in self._devices:
            raise PulsarException(f"Device {device_id} does not exist")

        self._devices.pop(device_id)

    def test_connection(self) -> bool:
        """Test serial connection (blocking - call from executor).

        Returns:
            True if connection is successful.

        Raises:
            PulsarConnectionError: If connection cannot be established.

        """
        if self._connector is None:
            raise PulsarConnectionError("Connector not initialized")

        return self._connector.test_connection()

    def disconnect(self) -> None:
        """Disconnect from the serial port or TCP connection (blocking - call from executor)."""
        if self._connector is not None:
            self._connector.disconnect()

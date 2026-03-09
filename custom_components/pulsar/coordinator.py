"""DataUpdateCoordinator for Pulsar devices."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL
from .pulsardevice import PulsarDevice

_LOGGER = logging.getLogger(__name__)


class PulsarDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to fetch data from Pulsar device."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: PulsarDevice,
        device_id: str,
        scan_interval: timedelta = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"Pulsar {device.name}",
            update_interval=scan_interval,
        )
        self.device = device
        self._device_id = device_id
        self._property_cache: dict[str, Any] | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from device (in executor to avoid blocking)."""
        try:
            # Fetch properties once if not cached
            if self._property_cache is None:
                await self.hass.async_add_executor_job(self._fetch_properties)
            return await self.hass.async_add_executor_job(self._fetch_data)
        except Exception as err:
            raise UpdateFailed(f"Error communicating with device: {err}") from err

    def _fetch_properties(self) -> None:
        """Fetch device properties once and cache them (runs in thread pool)."""
        if self._property_cache is not None:
            return

        properties: dict[str, Any] = {}
        for property_spec in self.device.metadata.property_specs:
            if (value := self.device.read_data(property_spec)) is not None:
                properties[property_spec.key] = value

        if self.device.metadata.property_parser:
            parsed = self.device.metadata.property_parser(properties)
            properties.update(parsed)

        self._property_cache = properties

    def _fetch_data(self) -> dict[str, Any]:
        """Fetch all metrics for device (runs in thread pool)."""
        return {
            data_spec.key: value
            for data_spec in self.device.metadata.data_specs
            if (value := self.device.read_data(data_spec)) is not None
        }

    @property
    def sw_version(self) -> int | None:
        """Return software version from cached properties."""
        if self._property_cache is None:
            return None
        return self._property_cache.get("sw_version")

    @property
    def hw_version(self) -> int | None:
        """Return hardware version from cached properties."""
        if self._property_cache is None:
            return None
        return self._property_cache.get("hw_version")

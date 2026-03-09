"""Config flow for Pulsar."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any
import uuid

import serial.tools.list_ports
import voluptuous as vol

from homeassistant.helpers import selector
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowHandler, FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .connector import Connector
from .const import (
    CONF_DEVICE_CONFIG,
    CONF_DEVICE_OR_ADDRESS,
    CONF_MANUAL_PATH,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL_ID,
    CONF_TYPE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    STEP_ADD_MENU,
    STEP_CHANGE_PORT,
    STEP_CHOOSE_SERIAL_PORT,
    STEP_COMPLETE,
    STEP_CONFIGURE_DEVICE,
    STEP_CONFIGURE_MENU,
    STEP_EDIT_DEVICE,
    STEP_MANUAL_PORT_CONFIG,
    STEP_SCAN_INTERVAL,
)
from .device_specs import DEVICE_TYPE_REGISTRY, DeviceType
from .exceptions import PulsarConnectionError

_LOGGER = logging.getLogger(__name__)

SELECTED_DEVICE = "selected_device"

DeviceConfigDict = dict[str, str | int]

DEFAULT_SCAN_INTERVAL_SECONDS = int(DEFAULT_SCAN_INTERVAL.total_seconds())


@dataclass
class FlowState:
    """Flow state data model."""

    device_or_address: str | None = None
    device_data: dict[str, DeviceConfigDict] = field(default_factory=dict)
    title: str | None = None
    scan_interval: int | None = None
    selected_device_id: str | None = None
    editing_mode: bool = False


def get_device_type_options() -> list[selector.SelectOptionDict]:
    """Get device type options for dropdown with translation support."""
    options = []
    for device_type in DeviceType:
        options.append(
            selector.SelectOptionDict(
                value=device_type.value,
                label=device_type.value,
            )
        )
    return options


def get_default_device_config() -> DeviceConfigDict:
    """Get default device configuration."""
    return {
        CONF_NAME: "",
        CONF_SERIAL_ID: "",
        CONF_TYPE: next(iter(DeviceType)).value,
    }


def create_device_config_schema(
    defaults: DeviceConfigDict | None = None,
) -> vol.Schema:
    """Create device config schema with device type options."""
    if defaults is None:
        defaults = get_default_device_config()

    return vol.Schema(
        {
            vol.Optional(CONF_NAME, default=defaults[CONF_NAME]): cv.string,
            vol.Optional(
                CONF_SERIAL_ID, default=defaults[CONF_SERIAL_ID]
            ): cv.positive_int,
            vol.Optional(CONF_TYPE, default=defaults[CONF_TYPE]): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=get_device_type_options(),
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="device_type",
                )
            ),
        }
    )


def create_scan_interval_schema(
    default_interval: int = DEFAULT_SCAN_INTERVAL_SECONDS,
) -> vol.Schema:
    """Create scan interval schema."""
    return vol.Schema(
        {
            vol.Required(CONF_SCAN_INTERVAL, default=default_interval): vol.All(
                cv.positive_int, vol.Range(min=5, max=3600)
            ),
        }
    )


def test_connection(device_or_address: str) -> bool:
    """Test connection to device (blocking - call from executor).

    Args:
        device_or_address: Serial device path or IP address.

    Returns:
        True if connection successful.

    Raises:
        PulsarConnectionError: If connection fails.

    """
    connector = Connector(device_or_address, "test_connector")
    try:
        return connector.test_connection()
    finally:
        connector.disconnect()


class BaseFlow(FlowHandler):
    """Base flow handler for Pulsar config flow."""

    def __init__(self, config_entry: ConfigEntry | None = None) -> None:
        """Initialize flow instance."""
        super().__init__()
        self._config_entry = config_entry
        self._state = FlowState()

    def _find_device_by_name(self, name: str) -> tuple[str, DeviceConfigDict] | None:
        """Find device by name.

        Returns:
            Tuple of (device_id, device_config) or None if not found.

        """
        for dev_id, dev_conf in self._state.device_data.items():
            if dev_conf[CONF_NAME] == name:
                return (dev_id, dev_conf)
        return None

    def _validate_device_config(
        self, device_conf: DeviceConfigDict, exclude_device_id: str | None = None
    ) -> dict[str, str]:
        """Validate device configuration.

        Args:
            device_conf: Device configuration to validate.
            exclude_device_id: Device ID to exclude from duplicate checks.

        Returns:
            Dictionary of validation errors (empty if valid).

        """
        errors: dict[str, str] = {}

        for dev_id, existing_conf in self._state.device_data.items():
            if exclude_device_id and dev_id == exclude_device_id:
                continue

            if existing_conf[CONF_SERIAL_ID] == device_conf[CONF_SERIAL_ID]:
                errors["base"] = "address_already_configured"
                break

            if existing_conf[CONF_NAME] == device_conf[CONF_NAME]:
                errors["base"] = "name_already_exists"
                break

        return errors

    def _get_available_ports(self) -> list[Any]:
        """Get list of available serial ports."""
        return serial.tools.list_ports.comports()

    def _format_port_display(self, port: Any) -> str:
        """Format port for display in dropdown."""
        port_str = f"{port.device}, s/n: {port.serial_number or 'n/a'}"
        if port.manufacturer:
            port_str += f" - {port.manufacturer}"
        return port_str

    def _format_port_title(self, port: Any) -> str:
        """Format port for title display."""
        title = f"{port.description}, s/n: {port.serial_number or 'n/a'}"
        if port.manufacturer:
            title += f" - {port.manufacturer}"
        return title

    def _build_entry_data(self) -> dict[str, Any]:
        """Build config entry data from flow state.

        Returns:
            Dictionary containing device configuration data.

        """
        if self._state.title is None:
            raise ValueError("Title is not set")
        if self._state.device_or_address is None:
            raise ValueError("Device or address is not set")
        if len(self._state.device_data) == 0:
            raise ValueError("No device data configured")

        return {
            CONF_DEVICE_OR_ADDRESS: self._state.device_or_address,
            CONF_DEVICE_CONFIG: self._state.device_data,
        }

    def _get_scan_interval(self) -> int:
        """Get scan interval from state or defaults."""
        if self._state.scan_interval is not None:
            return self._state.scan_interval

        default = DEFAULT_SCAN_INTERVAL_SECONDS
        if self._config_entry:
            return int(self._config_entry.options.get(CONF_SCAN_INTERVAL, default))

        return default

    async def _async_create_or_update_entry(self) -> FlowResult:
        """Create or update a config entry with the current flow state."""
        data = self._build_entry_data()
        scan_interval = self._get_scan_interval()

        if self._config_entry is not None:
            options = {
                **self._config_entry.options,
                CONF_SCAN_INTERVAL: scan_interval,
                "CONF_UPD_DATE": dt_util.utcnow().isoformat(),
            }

            self.hass.config_entries.async_update_entry(
                self._config_entry,
                data=data,
                options=options,
                title=f"Pulsar ({self._state.device_or_address})",
            )

            return self.async_create_entry(title="", data={})

        result = self.async_create_entry(
            title=f"Pulsar ({self._state.device_or_address})", data=data
        )

        device_or_address = self._state.device_or_address

        async def _update_entry_options(_now):
            entries = self.hass.config_entries.async_entries(DOMAIN)
            for entry in entries:
                if entry.data.get(CONF_DEVICE_OR_ADDRESS) == device_or_address:
                    self.hass.config_entries.async_update_entry(
                        entry, options={CONF_SCAN_INTERVAL: scan_interval}
                    )
                    break

        async_call_later(self.hass, 0, _update_entry_options)

        return result

    async def async_step_choose_serial_port(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Choose a serial port."""
        ports = await self.hass.async_add_executor_job(self._get_available_ports)
        list_of_ports = [self._format_port_display(p) for p in ports]

        if not list_of_ports:
            return await self.async_step_manual_port_config()

        list_of_ports.append(CONF_MANUAL_PATH)

        if user_input is not None:
            user_selection = user_input[CONF_DEVICE_OR_ADDRESS]

            if user_selection == CONF_MANUAL_PATH:
                return await self.async_step_manual_port_config()

            port_index = list_of_ports.index(user_selection)
            port = ports[port_index]

            self._state.device_or_address = port.device
            self._state.title = self._format_port_title(port)

            return await self.async_step_configure_device()

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_OR_ADDRESS, default=CONF_MANUAL_PATH): vol.In(
                    list_of_ports
                )
            }
        )

        return self.async_show_form(step_id=STEP_CHOOSE_SERIAL_PORT, data_schema=schema)

    async def async_step_manual_port_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Enter port settings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            device_or_address = user_input[CONF_DEVICE_OR_ADDRESS]
            self._state.device_or_address = device_or_address
            self._state.title = device_or_address

            try:
                await self.hass.async_add_executor_job(
                    test_connection, device_or_address
                )
            except PulsarConnectionError:
                errors["base"] = "cannot_connect"
            else:
                self._state.scan_interval = user_input.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS
                )
                if len(self._state.device_data) > 0:
                    return await self.async_step_add_menu()
                return await self.async_step_configure_device()

        current_interval = self._get_scan_interval()

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_OR_ADDRESS): str,
                vol.Required(CONF_SCAN_INTERVAL, default=current_interval): vol.All(
                    cv.positive_int, vol.Range(min=5, max=3600)
                ),
            }
        )

        return self.async_show_form(
            step_id=STEP_MANUAL_PORT_CONFIG,
            data_schema=schema,
            errors=errors,
        )

    def _get_device_config_defaults(self) -> tuple[DeviceConfigDict, dict[str, str]]:
        """Get default device config and placeholders for form."""
        if self._state.editing_mode and self._state.selected_device_id:
            edit_dev_conf_id = self._state.selected_device_id
            if edit_dev_conf_id in self._state.device_data:
                defaults = self._state.device_data[edit_dev_conf_id].copy()
                return defaults, {"for_device": f" for device `{defaults[CONF_NAME]}`"}

        return get_default_device_config(), {"for_device": ""}

    async def async_step_configure_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add or edit device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            device_conf: DeviceConfigDict = {
                CONF_NAME: user_input[CONF_NAME],
                CONF_SERIAL_ID: user_input[CONF_SERIAL_ID],
                CONF_TYPE: user_input[CONF_TYPE],
            }

            edit_dev_conf_id = (
                self._state.selected_device_id
                if self._state.editing_mode and self._state.selected_device_id
                else None
            )

            if edit_dev_conf_id and edit_dev_conf_id not in self._state.device_data:
                return self.async_abort(reason="device_not_found")

            validation_errors = self._validate_device_config(
                device_conf, exclude_device_id=edit_dev_conf_id
            )
            if validation_errors:
                errors.update(validation_errors)
            else:
                if edit_dev_conf_id:
                    self._state.device_data[edit_dev_conf_id] = device_conf
                    self._state.editing_mode = False
                    self._state.selected_device_id = None
                else:
                    new_dev_conf_id = uuid.uuid4().hex
                    self._state.device_data[new_dev_conf_id] = device_conf
                return await self.async_step_add_menu()

        defaults, placeholders = self._get_device_config_defaults()
        schema = create_device_config_schema(defaults)

        return self.async_show_form(
            step_id=STEP_CONFIGURE_DEVICE,
            data_schema=schema,
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_complete(
        self, _user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Complete the configuration flow."""
        return await self._async_create_or_update_entry()

    async def async_step_add_menu(
        self, _user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add device menu."""
        options = [STEP_CONFIGURE_DEVICE, STEP_COMPLETE]

        return self.async_show_menu(step_id=STEP_ADD_MENU, menu_options=options)


class ConfigFlow(BaseFlow, config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[misc]
    """Handle a config flow for Pulsar."""

    VERSION = 1

    def is_matching(self, other_flow: config_entries.ConfigFlow) -> bool:
        """Check if this flow matches another flow."""
        return False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowHandler:
        """Return the options flow."""
        return OptionsFlowHandler(config_entry)

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()

    async def async_step_user(  # type: ignore[override]
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        return await self.async_step_choose_serial_port()


class OptionsFlowHandler(BaseFlow, config_entries.OptionsFlow):  # type: ignore[misc]
    """Handle an options flow for Pulsar."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        super().__init__(config_entry)
        self._initialize_state_from_entry()

    def _initialize_state_from_entry(self) -> None:
        """Initialize flow state from config entry."""
        if self._config_entry is None:
            return
        self._state.device_or_address = self._config_entry.data[CONF_DEVICE_OR_ADDRESS]
        self._state.device_data = self._config_entry.data[CONF_DEVICE_CONFIG].copy()
        self._state.title = self._config_entry.title
        self._state.scan_interval = int(
            self._config_entry.options.get(
                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS
            )
        )

    async def async_step_init(
        self, _user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        return await self.async_step_configure_menu()

    async def async_step_configure_menu(
        self, _user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure menu options."""
        options = [
            STEP_CONFIGURE_DEVICE,
            STEP_EDIT_DEVICE,
            STEP_CHANGE_PORT,
            STEP_SCAN_INTERVAL,
        ]

        return self.async_show_menu(step_id=STEP_CONFIGURE_MENU, menu_options=options)

    async def async_step_change_port(
        self, _user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle change port."""
        return await self.async_step_choose_serial_port()

    async def async_step_edit_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle editing a device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_device_name = user_input[SELECTED_DEVICE]
            device_match = self._find_device_by_name(selected_device_name)

            if device_match is None:
                errors["base"] = "device_not_found"
            else:
                device_id, _ = device_match
                self._state.selected_device_id = device_id
                self._state.editing_mode = True
                return await self.async_step_configure_device()

        device_names = [
            self._state.device_data[dev_id][CONF_NAME]
            for dev_id in self._state.device_data
        ]

        schema = vol.Schema({vol.Required(SELECTED_DEVICE): vol.In(device_names)})

        return self.async_show_form(
            step_id=STEP_EDIT_DEVICE, data_schema=schema, errors=errors
        )

    async def async_step_scan_interval(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle scan interval configuration."""
        if user_input is not None:
            return self.async_create_entry(
                title="", data={CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL]}
            )

        current_interval = self._get_scan_interval()
        schema = create_scan_interval_schema(current_interval)

        return self.async_show_form(step_id=STEP_SCAN_INTERVAL, data_schema=schema)

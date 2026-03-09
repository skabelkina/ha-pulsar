"""For communicate with devices with serial connection."""

from __future__ import annotations

import logging
import threading
from typing import Any

import serial

from .exceptions import PulsarConnectionError

DEFAULT_BAUDRATE = 9600
DEFAULT_BYTESIZE = serial.EIGHTBITS
DEFAULT_PARITY = serial.PARITY_NONE
DEFAULT_STOPBITS = serial.STOPBITS_ONE

logging.basicConfig(level=logging.ERROR)
_LOGGER = logging.getLogger(__name__)


class Connector:
    """Represent connector for serial communication."""

    def __init__(self, device_or_ipaddress: str, name: str) -> None:
        """Initialize connector.

        Args:
            device_or_ipaddress: Serial device path (e.g., /dev/ttyUSB0)
                or IP address with port (e.g., 127.0.0.1:1024).
            name: Connector name.

        Note:
            Serial port initialization is deferred until first use to avoid
            blocking the event loop. The port will be initialized when send()
            is called or when _init_serial() is explicitly called from an
            executor job.

        """
        self._device_or_ipaddress = device_or_ipaddress
        self._name = name
        self._serport: Any = None  # serial.Serial varies by platform
        self._lock = threading.Lock()

    def _init_serial(self) -> bool:
        """Initialize the serial port (or TCP connection) and try to open it.

        Returns:
            True if successful, False otherwise.

        """
        try:
            if self._serport is not None and self._serport.is_open:
                self._serport.close()
                self._serport = None

            if self._device_or_ipaddress.startswith(
                "/"
            ) or self._device_or_ipaddress.startswith("C"):
                # assume direct serial
                self._serport = serial.Serial(self._device_or_ipaddress)
            else:
                # assume serial over IP via socket
                self._serport = serial.serial_for_url(
                    f"socket://{self._device_or_ipaddress}"
                )
            # Ensures that the serial port has not
            # been left hanging around by a previous process.

            if self._serport.is_open:
                self._serport.close()
            self._serport.baudrate = DEFAULT_BAUDRATE
            self._serport.bytesize = DEFAULT_BYTESIZE
            self._serport.parity = DEFAULT_PARITY
            self._serport.stopbits = DEFAULT_STOPBITS
            self._serport.timeout = 3
            self._serport.open()
            _LOGGER.info("Serial device %s opened", self._device_or_ipaddress)
            return True

        except serial.SerialException:
            _LOGGER.exception(
                "Unable to initialise serial port on %s", self._device_or_ipaddress
            )
            self._serport = None
            return False

    def test_connection(self) -> bool:
        """Test if the connection can be established without sending data.

        Returns:
            True if connection successful, False otherwise.

        Raises:
            PulsarConnectionError: If connection fails.

        """
        try:
            # Try to initialize serial port if not already open
            if (
                self._serport is None or not self._serport.is_open
            ) and not self._init_serial():
                raise PulsarConnectionError(
                    f"Unable to initialize serial port: {self._device_or_ipaddress}"
                )
            return True
        except serial.SerialException as se:
            raise PulsarConnectionError(
                f"Unable to test connection to {self._device_or_ipaddress}: {se}"
            ) from se

    def send(self, message: bytes, response_size: int) -> bytes:
        """Send a message to the device.

        Attempts to reopen the serial port if it is not open.
        If there are any errors or no reply, an empty bytes object is returned.

        Args:
            message: The message to send.
            response_size: Expected size of the response.

        Returns:
            The response as bytes, empty bytes if no response or error.

        """
        datalist = b""

        if self._serport is None and not self._init_serial():
            raise PulsarConnectionError(
                f"Unable to initialize serial port: {self._device_or_ipaddress}"
            )

        if self._serport is not None:
            # port successfully opened
            if self._serport.is_open:
                # Use lock to ensure exclusive access to serial port
                with self._lock:
                    try:
                        _LOGGER.debug("Sending %s", message)
                        serial_message = bytes(message)
                        self._serport.write(serial_message)

                    except serial.SerialTimeoutException as e:
                        _LOGGER.error(  # noqa: TRY400
                            "Timeout writing to %s: %s", self._device_or_ipaddress, e
                        )
                        return datalist

                    except serial.SerialException as e:
                        _LOGGER.error(  # noqa: TRY400
                            "Error writing to %s: %s", self._device_or_ipaddress, e
                        )
                        self._serport.close()
                        self._serport = None
                        return datalist

                    try:
                        _LOGGER.debug(
                            "Reading serial port %s", self._device_or_ipaddress
                        )
                        byteread = self._serport.read(response_size)
                        datalist = byteread

                    except serial.SerialException as e:
                        _LOGGER.error(  # noqa: TRY400
                            "Unable to read serial port %s: %s",
                            self._device_or_ipaddress,
                            e,
                        )
                        self._serport.close()
                        self._serport = None
            else:
                _LOGGER.debug(
                    "Serial port %s has been created but is not open, resetting...",
                    self._device_or_ipaddress,
                )
                self._serport = None

        if len(datalist) < 1:
            _LOGGER.debug("No response from %s", self._device_or_ipaddress)
        else:
            _LOGGER.debug("Received from %s: %s", self._device_or_ipaddress, datalist)
        return datalist

    def name(self) -> str:
        """Return the name of serial device.

        Returns:
            Connector name.

        """
        return self._name

    def disconnect(self) -> None:
        """Disconnect from the serial port or TCP connection."""
        if self._serport is not None and self._serport.is_open:
            try:
                self._serport.close()
            except (OSError, serial.SerialException) as err:
                _LOGGER.debug(
                    "Error closing serial port %s during cleanup: %s",
                    self._device_or_ipaddress,
                    err,
                )
            finally:
                self._serport = None
                _LOGGER.info("Closed serial port %s", self._device_or_ipaddress)

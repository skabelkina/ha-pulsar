"""Represent Pulsar device."""

from __future__ import annotations

import datetime
import logging
import math
import struct

from .connector import Connector
from .const import (
    ADDR_SIZE,
    CRC_SIZE,
    FUNC_SIZE,
    ID_SIZE,
    LEN_SIZE,
    MAX_REQUEST_ID,
    SERVICE_SIZE,
    EPSILON,
    UNAVAILABLE_FLOAT_MARKER,
    FUNCTION_READ_CHANNELS,
    ERROR_MESSAGES,
    ERROR_RESPONSE_FUNC_CODE,
)
from .device_specs import DataSpec, DevicePropertySpec, DeviceTypeMetadata
from .exceptions import (
    PulsarAddressError,
    PulsarCRCError,
    PulsarDataError,
    PulsarFrameError,
    PulsarProtocolError,
    PulsarRequestIdError,
)

_LOGGER = logging.getLogger(__name__)


class PulsarDevice:
    """Base class for Pulsar devices."""

    def __init__(
        self,
        connector: Connector,
        metadata: DeviceTypeMetadata,
        name: str,
        serial_number: int,
    ) -> None:
        """Initialize Pulsar device.

        Args:
            connector: Serial connector instance.
            metadata: Device type metadata.
            name: Device name.
            serial_number: Device serial number (used as RS485 address).

        """
        self._connector = connector
        self._metadata = metadata
        self._name = name
        self._serial_number = serial_number
        self._request_id = 0

    def calculate_crc16(self, buf: bytearray | bytes, size: int, offset: int) -> int:
        """Calculate CRC-16-ModBus checksum.

        Args:
            buf: Buffer to calculate CRC for.
            size: Size of data to process.
            offset: Starting offset in buffer.

        Returns:
            CRC-16 value.

        """
        poly = 0xA001
        crc = 0xFFFF
        for i in range(size):
            crc ^= 0xFF & buf[i + offset]
            for _ in range(8):
                if crc & 0x0001:
                    crc = ((crc >> 1) & 0xFFFF) ^ poly
                else:
                    crc = (crc >> 1) & 0xFFFF
        return crc

    def write_bcd(
        self, val: int, buf: bytearray, size: int, offset: int, big_endian: bool
    ) -> bytearray:
        """Write integer as BCD to buffer.

        Args:
            val: Integer value to encode.
            buf: Target buffer.
            size: Number of bytes to write.
            offset: Starting offset in buffer.
            big_endian: True for big-endian, False for little-endian.

        Returns:
            Modified buffer.

        """
        for i in range(size):
            byte_val = int(val % 10)
            val = int(val / 10)
            byte_val |= int(val % 10) << 4
            val = int(val / 10)
            buf[size - i - 1 + offset if big_endian else i + offset] = byte_val
        return buf

    def write_hex(
        self, val: int, buf: bytearray, size: int, offset: int, big_endian: bool
    ) -> bytearray:
        """Write integer as hex to buffer.

        Args:
            val: Integer value to encode.
            buf: Target buffer.
            size: Number of bytes to write.
            offset: Starting offset in buffer.
            big_endian: True for big-endian, False for little-endian.

        Returns:
            Modified buffer.

        """
        for i in range(size):
            buf[size - i - 1 + offset if big_endian else i + offset] = val & 0xFF
            val >>= 8
        return buf

    def read_bcd(
        self, buf: bytearray | bytes, size: int, offset: int, big_endian: bool
    ) -> int:
        """Read BCD integer from buffer.

        Args:
            buf: Source buffer.
            size: Number of bytes to read.
            offset: Starting offset in buffer.
            big_endian: True for big-endian, False for little-endian.

        Returns:
            Decoded integer value.

        """
        res = 0
        for i in range(size):
            res *= 100
            bcd_byte = buf[i + offset if big_endian else size - i - 1 + offset]
            dec_byte = (bcd_byte & 0x0F) + 10 * ((bcd_byte >> 4) & 0x0F)
            res += dec_byte
        return res

    def read_int_from_hex(
        self, buf: bytearray | bytes, size: int, offset: int, big_endian: bool
    ) -> int:
        """Read integer from hex buffer.

        Args:
            buf: Source buffer.
            size: Number of bytes to read.
            offset: Starting offset in buffer.
            big_endian: True for big-endian, False for little-endian.

        Returns:
            Decoded integer value.

        """
        res = 0
        for i in range(size):
            res <<= 8
            res |= buf[i + offset if big_endian else size - i - 1 + offset]
        return res

    def read_float_from_hex(
        self, buf: bytearray | bytes, size: int, offset: int, big_endian: bool
    ) -> float | None:
        """Read float from hex buffer.

        Args:
            buf: Source buffer.
            size: Number of bytes to read.
            offset: Starting offset in buffer.
            big_endian: True for big-endian, False for little-endian.

        Returns:
            Decoded float value or None.

        Raises:
            PulsarDataError: If size is unsupported.

        """
        if big_endian:
            format_str = ">"
        else:
            format_str = "<"

        if size == 4:
            format_str += "f"
        elif size == 8:
            format_str += "d"
        elif size == 2:
            format_str += "e"
        else:
            raise PulsarDataError(f"Unsupported float size: {size}")

        val = struct.unpack(format_str, buf[offset : size + offset])
        return val[0] if val else None

    def send_request(self, message: bytes, response_size: int) -> bytes:
        """Send request and receive response.

        Args:
            message: Request message.
            response_size: Expected response size.

        Returns:
            Response bytes.

        Raises:
            PulsarFrameError: If response validation fails.

        """
        addr = self.read_bcd(message, ADDR_SIZE, 0, True)
        request_id = self.read_int_from_hex(
            message, ID_SIZE, len(message) - ID_SIZE - CRC_SIZE, False
        )
        expected_response_size = response_size

        response = self._connector.send(message, response_size)
        
        if len(response) >= 5 and response[4] == ERROR_RESPONSE_FUNC_CODE:
            return response
    
        self.check_response(response, expected_response_size, addr, request_id)

        return response


    def send_payload(
        self,
        payload: bytes,
        function: bytes,
        addr: int,
        request_id: int,
        expected_payload_size: int,
    ) -> bytes:
        """Send payload and receive response payload.

        Args:
            payload: Request payload.
            function: Function code.
            addr: Device address.
            request_id: Request ID.
            expected_payload_size: Expected payload size in response.

        Returns:
            Response payload bytes.

        Raises:
            PulsarProtocolError: If request preparation fails.
            PulsarFrameError: If response validation fails.

        """
        request = self.prepare_request(payload, function, addr, request_id)
        response = self.send_request(request, expected_payload_size + SERVICE_SIZE)
        
        if len(response) >= 5 and response[4] == ERROR_RESPONSE_FUNC_CODE:
            error_code = response[6] if len(response) > 6 else 0
            error_msg = ERROR_MESSAGES.get(error_code, f"Unknown error code: 0x{error_code:02X}")
            raise PulsarProtocolError(f"Device returned error: {error_msg}")
        
        start_ind = ADDR_SIZE + FUNC_SIZE + LEN_SIZE
        end_ind = 0 - ID_SIZE - CRC_SIZE
        return response[start_ind:end_ind]

    def check_response(
        self, response: bytes, expected_response_size: int, addr: int, request_id: int
    ) -> bool:
        """Validate response frame.

        Args:
            response: Response bytes from device.
            expected_response_size: Expected size of response.
            addr: Expected device address.
            request_id: Expected request ID.

        Returns:
            True if response is valid.

        Raises:
            PulsarFrameError: If frame is too short or wrong size.
            PulsarCRCError: If CRC check fails.
            PulsarAddressError: If address mismatch.
            PulsarRequestIdError: If request ID mismatch.

        """
        response_size = len(response)

        if response_size < SERVICE_SIZE:
            raise PulsarFrameError(f"Frame too short: {response_size} < {SERVICE_SIZE}")

        if response_size != expected_response_size:
            raise PulsarFrameError(
                f"Unexpected frame size: {response_size} != {expected_response_size}"
            )

        if expected_response_size != response[5]:
            raise PulsarFrameError(
                f"Frame length mismatch: {expected_response_size} != {response[5]}"
            )

        # check crc16
        response_crc = self.read_int_from_hex(
            response, CRC_SIZE, response_size - CRC_SIZE, False
        )
        calc_response_crc = self.calculate_crc16(response, response_size - CRC_SIZE, 0)
        if response_crc != calc_response_crc:
            raise PulsarCRCError(
                f"CRC mismatch: {response_crc:04X} != {calc_response_crc:04X}"
            )

        # check address
        response_addr = self.read_bcd(response, ADDR_SIZE, 0, True)
        if response_addr != addr:
            raise PulsarAddressError(f"Address mismatch: {response_addr} != {addr}")

        # check request id
        response_request_id = self.read_int_from_hex(
            response, ID_SIZE, response_size - ID_SIZE - CRC_SIZE, False
        )
        if response_request_id != request_id:
            raise PulsarRequestIdError(
                f"Request ID mismatch: {response_request_id} != {request_id}"
            )

        return True

    def prepare_request(
        self, payload: bytes, function: bytes, addr: int, request_id: int
    ) -> bytes:
        """Prepare request frame.

        Args:
            payload: Request payload.
            function: Function code (1 byte).
            addr: Device address.
            request_id: Request ID.

        Returns:
            Complete request frame.

        Raises:
            PulsarProtocolError: If function code is invalid.

        """
        if len(function) != 1:
            raise PulsarProtocolError(
                f"Function code must be 1 byte, got {len(function)}"
            )

        payload_size = len(payload)
        request_size = payload_size + SERVICE_SIZE

        request = bytearray(request_size)

        self.write_bcd(addr, request, 4, 0, True)

        # function and size
        request[4] = function[0]
        request[5] = request_size

        # payload
        offset = ADDR_SIZE + FUNC_SIZE + LEN_SIZE
        request[offset : offset + payload_size] = payload

        # request ID
        self.write_hex(request_id, request, 2, request_size - 4, False)

        # CRC16
        crc = self.calculate_crc16(request, request_size - 2, 0)
        self.write_hex(crc, request, 2, request_size - 2, False)

        return bytes(request)

    @property
    def name(self) -> str:
        """Return device name.

        Returns:
            Device name.

        """
        return self._name

    @property
    def metadata(self) -> DeviceTypeMetadata:
        """Return device metadata.

        Returns:
            Device type metadata.

        """
        return self._metadata

    @property
    def serial_number(self) -> int:
        """Return device serial number.

        Returns:
            Device serial number.

        """
        return self._serial_number

    def next_request_id(self) -> int:
        """Get next request ID with wraparound."""
        self._request_id += 1
        if self._request_id > MAX_REQUEST_ID:
            self._request_id = 0
        return self._request_id

    def read_data(
        self, spec: DataSpec | DevicePropertySpec
    ) -> int | float | str | datetime.datetime | None:
        """Read data value from channel, parameter, or device property.

        Args:
            spec: Data or property specification.

        Returns:
            Data value or None if unavailable.

        """
        if spec.payload_size == 0:
            payload = bytes(0)
        else:
            payload = bytearray(spec.payload_size)
            self.write_hex(spec.address, payload, spec.payload_size, 0, False)
            payload = bytes(payload)
        function = bytes([spec.function_code])

        try:
            response_payload = self.send_payload(
                payload,
                function,
                self._serial_number,
                self.next_request_id(),
                spec.response_size,
            )
            value = self._parse_response(response_payload, spec.data_type, spec)
            if spec.data_type == "datetime":
                return value

            scale_factor = getattr(spec, "scale_factor", 1.0)
            return self._apply_scale_factor(value, scale_factor)
        except PulsarProtocolError as err:
            if spec.function_code == FUNCTION_READ_CHANNELS:
                data_type = "channel"
            else:
                data_type = "parameter"
            _LOGGER.warning(
                "Device %s (%s) returned error for %s %s (0x%04X): %s",
                self._name,
                self._metadata.model_name,
                data_type,
                spec.key,
                spec.address,
                err,
            )
            return None
        except (
            ConnectionError,
            TimeoutError,
            OSError,
            PulsarFrameError,
        ) as err:
            if spec.function_code == FUNCTION_READ_CHANNELS:
                data_type = "channel"
            else:
                data_type = "parameter"
            _LOGGER.warning(
                "Device %s (%s) failed to read %s %s (addr: 0x%04X, func: 0x%02X): %s",
                self._name,
                self._metadata.model_name,
                data_type,
                spec.key,
                spec.address,
                spec.function_code,
                err,
            )
            return None

    def _is_unavailable_float(
        self, value: float, spec: DataSpec | DevicePropertySpec
    ) -> bool:
        """Check if float value indicates unavailable data"""
        
        if not math.isfinite(value):
            _LOGGER.warning(
                "Device %s (%s) sensor %s returned non-finite value (NaN/Inf), treating as unavailable",
                self._name,
                self._metadata.model_name,
                spec.key,
            )
            return True
        
        if abs(abs(value) - UNAVAILABLE_FLOAT_MARKER) < EPSILON:
            _LOGGER.warning(
                "Device %s (%s) sensor %s returned special float value %f indicating unavailable data",
                self._name,
                self._metadata.model_name,
                spec.key,
                value
            )
            return True
        return False
        
    def _parse_response(
        self, response_payload: bytes, data_type: str, spec: DataSpec | DevicePropertySpec
    ) -> int | float | str | datetime.datetime | None:
        """Parse response payload based on data type.

        Args:
            response_payload: Response payload bytes.
            data_type: Data type identifier.

        Returns:
            Parsed value or None if type is unsupported.
            
        Note:
            For float32, special values like -999.0 and 999.0
            are treated as "unavailable" and return None.
        """
        
        if data_type == "float32":
            value = self.read_float_from_hex(response_payload, 4, 0, False)
            if value is None or self._is_unavailable_float(value, spec):
                return None
            return value
        if data_type == "int32":
            value = self.read_int_from_hex(response_payload, 4, 0, False)
            return self._convert_to_signed(value, 32)    
        if data_type == "uint32":
            return self.read_int_from_hex(response_payload, 4, 0, False)
        if data_type == "uint64":
            return self.read_int_from_hex(response_payload, 8, 0, False)
        if data_type == "uint8":
            return response_payload[0]
        if data_type == "int8":
            value = response_payload[0]
            return self._convert_to_signed(value, 8)
        if data_type == "uint16":
            return self.read_int_from_hex(response_payload, 2, 0, False)
        if data_type == "string":
            return response_payload.decode("ascii", errors="ignore").rstrip("\x00")
        if data_type == "datetime":
            return self._parse_datetime(response_payload)
        return None
        
    def _parse_datetime(self, response_payload: bytes) -> datetime.datetime:
        """Parse datetime from response payload.

        Args:
            response_payload: 6 bytes representing datetime (YEAR, MONTH, DAY, HOUR, MINUTE, SECOND).

        Returns:
            Datetime object (timezone-naive, as device doesn't specify timezone).

        """
        year, month, day, hour, minute, seconds = struct.unpack("6B", response_payload)
        return datetime.datetime(  # noqa: DTZ001
            2000 + year,
            month,
            day,
            hour,
            minute,
            seconds,
        )

    def _convert_to_signed(self, value: int, bit_width: int) -> int:
        """Convert unsigned integer to signed.

        Args:
            value: Unsigned integer value.
            bit_width: Bit width (8, 16, 32, etc.).

        Returns:
            Signed integer value.

        """
        sign_bit = 1 << (bit_width - 1)
        if value & sign_bit:
            return value - (1 << bit_width)
        return value

    def _apply_scale_factor(
        self, value: int | float | str | None, scale_factor: float
    ) -> int | float | str | None:
        """Apply scale factor to numeric value.

        Args:
            value: Parsed value from device.
            scale_factor: Scale factor to apply.

        Returns:
            Scaled value or original value if scaling not applicable.

        """
        if (
            value is not None
            and scale_factor != 1.0
            and isinstance(value, (int, float))
        ):
            return value * scale_factor
        return value

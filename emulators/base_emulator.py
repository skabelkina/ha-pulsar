"""Base emulator implementing PulsarM protocol over TCP.

This module provides the core protocol implementation including:
- CRC-16-IBM calculation and validation
- Frame parsing and construction
- BCD address encoding/decoding
- Standard protocol function handlers
- TCP server infrastructure
"""

from __future__ import annotations

import logging
import socket
import struct
import threading
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Callable

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class BaseEmulator(ABC):
    """Base class for PulsarM protocol emulators."""

    # Frame structure constants
    ADDR_SIZE = 4
    FUNC_SIZE = 1
    LEN_SIZE = 1
    ID_SIZE = 2
    CRC_SIZE = 2
    SERVICE_SIZE = ADDR_SIZE + FUNC_SIZE + LEN_SIZE + ID_SIZE + CRC_SIZE

    # Function codes
    FN_ERROR = 0x00
    FN_READ_CHANNELS = 0x01
    FN_WRITE_CHANNELS = 0x02
    FN_READ_DATETIME = 0x04
    FN_WRITE_DATETIME = 0x05
    FN_READ_ARCHIVE = 0x06
    FN_READ_PARAMETER = 0x0A
    FN_WRITE_PARAMETER = 0x0B

    # Error codes
    ERR_FUNCTION_NOT_SUPPORTED = 0x01
    ERR_INVALID_CHANNEL_MASK = 0x02
    ERR_INVALID_LENGTH = 0x03
    ERR_PARAMETER_MISSING = 0x04

    def __init__(self, device_address: int, device_id: int, port: int):
        """Initialize base emulator.

        Args:
            device_address: Device address (BCD encoded, e.g., 12345678).
            device_id: Device identifier (UINT16).
            port: TCP port to listen on.
        """
        self.device_address = device_address
        self.device_id = device_id
        self.port = port
        self.running = False
        self.server_socket: socket.socket | None = None

        # Function handler registry
        self.function_handlers: Dict[int, Callable] = {
            self.FN_READ_CHANNELS: self._handle_read_channels,
            self.FN_WRITE_CHANNELS: self._handle_write_channels,
            self.FN_READ_DATETIME: self._handle_read_datetime,
            self.FN_WRITE_DATETIME: self._handle_write_datetime,
            self.FN_READ_ARCHIVE: self._handle_read_archive,
            self.FN_READ_PARAMETER: self._handle_read_parameter,
            self.FN_WRITE_PARAMETER: self._handle_write_parameter,
        }

    def calculate_crc16(self, data: bytes) -> int:
        """Calculate CRC-16-IBM checksum.

        Args:
            data: Data to calculate CRC for.

        Returns:
            CRC-16 value.
        """
        poly = 0xA001
        crc = 0xFFFF

        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = ((crc >> 1) & 0xFFFF) ^ poly
                else:
                    crc = (crc >> 1) & 0xFFFF

        return crc

    def encode_bcd(self, value: int, size: int) -> bytes:
        """Encode integer as BCD (big-endian/MSB).

        Args:
            value: Integer to encode.
            size: Number of bytes.

        Returns:
            BCD encoded bytes.
        """
        result = bytearray(size)
        for i in range(size - 1, -1, -1):
            low_digit = value % 10
            value //= 10
            high_digit = value % 10
            value //= 10
            result[i] = (high_digit << 4) | low_digit
        return bytes(result)

    def decode_bcd(self, data: bytes) -> int:
        """Decode BCD (big-endian/MSB) to integer.

        Args:
            data: BCD encoded bytes.

        Returns:
            Decoded integer.
        """
        result = 0
        for byte in data:
            high_digit = (byte >> 4) & 0x0F
            low_digit = byte & 0x0F
            result = result * 100 + high_digit * 10 + low_digit
        return result

    def encode_uint(self, value: int, size: int, big_endian: bool = False) -> bytes:
        """Encode integer as bytes.

        Args:
            value: Integer to encode.
            size: Number of bytes.
            big_endian: True for big-endian, False for little-endian.

        Returns:
            Encoded bytes.
        """
        byte_order = "big" if big_endian else "little"
        return value.to_bytes(size, byte_order)

    def decode_uint(self, data: bytes, big_endian: bool = False) -> int:
        """Decode bytes to integer.

        Args:
            data: Bytes to decode.
            big_endian: True for big-endian, False for little-endian.

        Returns:
            Decoded integer.
        """
        byte_order = "big" if big_endian else "little"
        return int.from_bytes(data, byte_order)

    def encode_float32(self, value: float) -> bytes:
        """Encode float as IEEE 754 single precision (little-endian).

        Args:
            value: Float value.

        Returns:
            4 bytes.
        """
        return struct.pack("<f", value)

    def encode_float64(self, value: float) -> bytes:
        """Encode float as IEEE 754 double precision (little-endian).

        Args:
            value: Float value.

        Returns:
            8 bytes.
        """
        return struct.pack("<d", value)

    def encode_int32(self, value: int) -> bytes:
        """Encode integer as signed 32-bit (little-endian).

        Args:
            value: Integer value (signed).

        Returns:
            4 bytes.
        """
        return struct.pack("<i", value)

    def encode_datetime(self, dt: datetime) -> bytes:
        """Encode datetime as DATETIME structure (6 bytes).

        Args:
            dt: Datetime object.

        Returns:
            6 bytes (YEAR, MONTH, DAY, HOUR, MINUTE, SECOND).
        """
        return bytes(
            [
                dt.year - 2000,
                dt.month,
                dt.day,
                dt.hour,
                dt.minute,
                dt.second,
            ]
        )

    def decode_datetime(self, data: bytes) -> datetime:
        """Decode DATETIME structure to datetime object.

        Args:
            data: 6 bytes (YEAR, MONTH, DAY, HOUR, MINUTE, SECOND).

        Returns:
            Datetime object.
        """
        return datetime(
            2000 + data[0],
            data[1],
            data[2],
            data[3],
            data[4],
            data[5],
        )

    def validate_frame(self, frame: bytes) -> tuple[bool, str]:
        """Validate incoming frame.

        Args:
            frame: Received frame data.

        Returns:
            Tuple of (is_valid, error_message).
        """
        # Check minimum length
        if len(frame) < self.SERVICE_SIZE:
            return False, f"Frame too short: {len(frame)} < {self.SERVICE_SIZE}"

        # Check address is valid BCD
        try:
            addr = self.decode_bcd(frame[0 : self.ADDR_SIZE])
        except Exception as e:
            return False, f"Invalid BCD address: {e}"

        # Check LEN field
        frame_len = frame[5]
        if len(frame) < frame_len:
            return False, f"Frame incomplete: {len(frame)} < {frame_len}"

        # Check CRC
        crc_received = self.decode_uint(frame[-self.CRC_SIZE :], big_endian=False)
        crc_calculated = self.calculate_crc16(frame[: -self.CRC_SIZE])
        if crc_received != crc_calculated:
            return False, f"CRC mismatch: {crc_received:04X} != {crc_calculated:04X}"

        # Check address matches (or broadcast)
        if addr != 0 and addr != self.device_address:
            return False, f"Address mismatch: {addr} != {self.device_address}"

        return True, ""

    def parse_frame(self, frame: bytes) -> dict:
        """Parse validated frame into components.

        Args:
            frame: Validated frame data.

        Returns:
            Dictionary with frame components.
        """
        addr = self.decode_bcd(frame[0 : self.ADDR_SIZE])
        function = frame[4]
        length = frame[5]
        payload = frame[6 : -self.ID_SIZE - self.CRC_SIZE]
        request_id = self.decode_uint(
            frame[-self.ID_SIZE - self.CRC_SIZE : -self.CRC_SIZE]
        )

        return {
            "address": addr,
            "function": function,
            "length": length,
            "payload": payload,
            "request_id": request_id,
        }

    def build_frame(self, function: int, payload: bytes, request_id: int) -> bytes:
        """Build response frame.

        Args:
            function: Function code.
            payload: Response payload.
            request_id: Request ID to echo.

        Returns:
            Complete frame with CRC.
        """
        frame_len = len(payload) + self.SERVICE_SIZE
        frame = bytearray()

        # Address (BCD, big-endian)
        frame.extend(self.encode_bcd(self.device_address, self.ADDR_SIZE))

        # Function code
        frame.append(function)

        # Length
        frame.append(frame_len)

        # Payload
        frame.extend(payload)

        # Request ID (little-endian)
        frame.extend(self.encode_uint(request_id, self.ID_SIZE, big_endian=False))

        # CRC (little-endian)
        crc = self.calculate_crc16(bytes(frame))
        frame.extend(self.encode_uint(crc, self.CRC_SIZE, big_endian=False))

        return bytes(frame)

    def build_error_response(self, error_code: int, request_id: int) -> bytes:
        """Build error response frame.

        Args:
            error_code: Error code (1 byte).
            request_id: Request ID to echo.

        Returns:
            Error response frame.
        """
        payload = bytes([error_code])
        return self.build_frame(self.FN_ERROR, payload, request_id)

    def _handle_read_channels(self, payload: bytes, request_id: int) -> bytes:
        """Handle Read Channels function (0x01).

        Args:
            payload: Request payload (4 bytes CHMASK).
            request_id: Request ID.

        Returns:
            Response frame.
        """
        if len(payload) < 4:
            return self.build_error_response(self.ERR_INVALID_LENGTH, request_id)

        channel_mask = self.decode_uint(payload[0:4])
        channel_data = self.get_channel_data(channel_mask)

        if channel_data is None:
            return self.build_error_response(self.ERR_INVALID_CHANNEL_MASK, request_id)

        return self.build_frame(self.FN_READ_CHANNELS, channel_data, request_id)

    def _handle_write_channels(self, payload: bytes, request_id: int) -> bytes:
        """Handle Write Channels function (0x02).

        Args:
            payload: Request payload (CHMASK + channel data).
            request_id: Request ID.

        Returns:
            Response frame with success mask.
        """
        if len(payload) < 4:
            return self.build_error_response(self.ERR_INVALID_LENGTH, request_id)

        channel_mask = self.decode_uint(payload[0:4])
        # Echo back the mask as "success"
        response_payload = self.encode_uint(channel_mask, 4)
        return self.build_frame(self.FN_WRITE_CHANNELS, response_payload, request_id)

    def _handle_read_datetime(self, payload: bytes, request_id: int) -> bytes:  # noqa: ARG002
        """Handle Read Date/Time function (0x04).

        Args:
            payload: Empty payload.
            request_id: Request ID.

        Returns:
            Response frame with current datetime.
        """
        now = datetime.now()
        datetime_bytes = self.encode_datetime(now)
        return self.build_frame(self.FN_READ_DATETIME, datetime_bytes, request_id)

    def _handle_write_datetime(self, payload: bytes, request_id: int) -> bytes:
        """Handle Write Date/Time function (0x05).

        Args:
            payload: DATETIME structure (6 bytes).
            request_id: Request ID.

        Returns:
            Response frame with status.
        """
        if len(payload) < 6:
            return self.build_error_response(self.ERR_INVALID_LENGTH, request_id)

        # Status: 0x01 = Success, followed by 3 padding bytes
        response_payload = bytes([0x01, 0x00, 0x00, 0x00])
        return self.build_frame(self.FN_WRITE_DATETIME, response_payload, request_id)

    def _handle_read_archive(self, payload: bytes, request_id: int) -> bytes:
        """Handle Read Archive function (0x06).

        Args:
            payload: MASK(4) + TYPE(2) + DATE_START(6) + DATE_END(6).
            request_id: Request ID.

        Returns:
            Response frame with archive data.
        """
        if len(payload) < 18:
            return self.build_error_response(self.ERR_INVALID_LENGTH, request_id)

        channel_mask = self.decode_uint(payload[0:4])
        archive_type = self.decode_uint(payload[4:6])
        date_start = self.decode_datetime(payload[6:12])
        date_end = self.decode_datetime(payload[12:18])

        archive_data = self.get_archive_data(
            channel_mask, archive_type, date_start, date_end
        )

        if archive_data is None:
            return self.build_error_response(self.ERR_PARAMETER_MISSING, request_id)

        return self.build_frame(self.FN_READ_ARCHIVE, archive_data, request_id)

    def _handle_read_parameter(self, payload: bytes, request_id: int) -> bytes:
        """Handle Read Parameter function (0x0A).

        Args:
            payload: INDEX (2 bytes, little-endian).
            request_id: Request ID.

        Returns:
            Response frame with parameter value (8 bytes).
        """
        if len(payload) < 2:
            return self.build_error_response(self.ERR_INVALID_LENGTH, request_id)

        param_index = self.decode_uint(payload[0:2])
        param_value = self.get_parameter(param_index)

        if param_value is None:
            return self.build_error_response(self.ERR_PARAMETER_MISSING, request_id)

        # Pad to 8 bytes if needed
        if len(param_value) < 8:
            param_value = param_value + bytes(8 - len(param_value))

        return self.build_frame(self.FN_READ_PARAMETER, param_value, request_id)

    def _handle_write_parameter(self, payload: bytes, request_id: int) -> bytes:
        """Handle Write Parameter function (0x0B).

        Args:
            payload: INDEX (2 bytes) + VALUE (8 bytes).
            request_id: Request ID.

        Returns:
            Response frame with status (0x0000 = success).
        """
        if len(payload) < 10:
            return self.build_error_response(self.ERR_INVALID_LENGTH, request_id)

        # Always return success
        response_payload = self.encode_uint(0x0000, 2)
        return self.build_frame(self.FN_WRITE_PARAMETER, response_payload, request_id)

    def process_request(self, frame: bytes) -> bytes | None:
        """Process incoming request frame.

        Args:
            frame: Complete request frame.

        Returns:
            Response frame or None if invalid.
        """
        # Validate frame
        is_valid, error_msg = self.validate_frame(frame)
        if not is_valid:
            logger.warning("Invalid frame: %s", error_msg)
            return None

        # Parse frame
        parsed = self.parse_frame(frame)
        function = parsed["function"]
        payload = parsed["payload"]
        request_id = parsed["request_id"]

        logger.info("Received function 0x%02X, payload size %d", function, len(payload))

        # Dispatch to handler
        handler = self.function_handlers.get(function)
        if handler is None:
            logger.warning("Unsupported function: 0x%02X", function)
            return self.build_error_response(
                self.ERR_FUNCTION_NOT_SUPPORTED, request_id
            )

        return handler(payload, request_id)

    def handle_client(self, client_socket: socket.socket, client_address: tuple):
        """Handle individual client connection.

        Args:
            client_socket: Client socket.
            client_address: Client address tuple.
        """
        logger.info("Client connected from %s", client_address)

        try:
            while self.running:
                # Read frame (with timeout)
                client_socket.settimeout(1.0)
                try:
                    # Read minimum frame size first
                    data = client_socket.recv(self.SERVICE_SIZE)
                    if not data:
                        break

                    # Check if more data is expected
                    if len(data) >= 6:
                        frame_len = data[5]
                        if frame_len > len(data):
                            # Read remaining bytes
                            remaining = frame_len - len(data)
                            data += client_socket.recv(remaining)

                    # Process request
                    response = self.process_request(data)
                    if response:
                        client_socket.sendall(response)
                        logger.debug("Sent response: %s", response.hex())

                except socket.timeout:
                    continue
                except (OSError, ValueError, ConnectionError) as e:
                    logger.error("Error processing request: %s", e)
                    break

        finally:
            client_socket.close()
            logger.info("Client disconnected from %s", client_address)

    def start(self):
        """Start the TCP server."""
        self.running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(("0.0.0.0", self.port))
        self.server_socket.listen(5)

        logger.info(
            "Emulator started on port %d, address %d", self.port, self.device_address
        )

        try:
            while self.running:
                self.server_socket.settimeout(1.0)
                try:
                    client_socket, client_address = self.server_socket.accept()
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, client_address),
                        daemon=True,
                    )
                    client_thread.start()
                except socket.timeout:
                    continue
        except KeyboardInterrupt:
            logger.info("Server interrupted by user")
        finally:
            self.stop()

    def stop(self):
        """Stop the TCP server."""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        logger.info("Emulator stopped")

    # Abstract methods to be implemented by subclasses

    @abstractmethod
    def get_channel_data(self, channel_mask: int) -> bytes | None:
        """Get channel data for the specified mask.

        Args:
            channel_mask: Bitmask of channels to read.

        Returns:
            Channel data bytes or None if invalid.
        """
        raise NotImplementedError

    @abstractmethod
    def get_parameter(self, param_index: int) -> bytes | None:
        """Get parameter value.

        Args:
            param_index: Parameter index.

        Returns:
            Parameter value (up to 8 bytes) or None if not found.
        """
        raise NotImplementedError

    @abstractmethod
    def get_archive_data(
        self,
        channel_mask: int,
        archive_type: int,
        date_start: datetime,
        date_end: datetime,
    ) -> bytes | None:
        """Get archive data.

        Args:
            channel_mask: Single channel mask.
            archive_type: Archive type (1=hourly, 2=daily, 3=monthly).
            date_start: Start datetime.
            date_end: End datetime.

        Returns:
            Archive data or None if invalid.
        """
        raise NotImplementedError

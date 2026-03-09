"""Custom exceptions for Pulsar integration."""

from __future__ import annotations


class PulsarException(Exception):
    """Base exception for Pulsar integration."""


class PulsarConnectionError(PulsarException):
    """Exception raised when connection to device fails."""


class PulsarProtocolError(PulsarException):
    """Exception raised when protocol errors occur."""


class PulsarFrameError(PulsarProtocolError):
    """Exception raised when frame validation fails."""


class PulsarCRCError(PulsarFrameError):
    """Exception raised when CRC check fails."""


class PulsarAddressError(PulsarFrameError):
    """Exception raised when address mismatch occurs."""


class PulsarRequestIdError(PulsarFrameError):
    """Exception raised when request ID mismatch occurs."""


class PulsarDataError(PulsarException):
    """Exception raised when data parsing fails."""

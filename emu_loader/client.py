"""EmuLoaderClient - high-level drop-in client for emulator memory access."""

import asyncio
from typing import Callable, Optional

from .emulatorinfo import EmulatorInfo, connect_to_emulator

try:
    from CommonClient import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class EmuLoaderClient:
    """Drop-in replacement client for PJ64Client using direct memory access."""

    def __init__(self):
        """Initialize the EmuLoaderClient."""
        self.emulator_info: Optional[EmulatorInfo] = None
        self.connected = False

    def connect(self, pull_from_web: bool = True) -> bool:
        """Connect to an available emulator.

        Args:
            pull_from_web: If True (default), fetch the latest emulator config from GitHub Pages
                           before connecting. If False, use the local emulators.json.
        """
        self.emulator_info = connect_to_emulator(pull_from_web=pull_from_web)
        self.connected = self.emulator_info is not None
        return self.connected

    def disconnect(self):
        """Disconnect from the emulator."""
        if self.emulator_info:
            self.emulator_info.disconnect()
        self.connected = False
        self.emulator_info = None

    def is_connected(self) -> bool:
        """Check if connected to an emulator.

        This serves as a safety check for the memory access methods below, so pyright ignore
        annotations have been added to them. Be careful if editing this method!
        """
        return self.connected and self.emulator_info is not None

    # Direct memory access methods
    def read_u8(self, address: int) -> int:
        """Read an 8-bit unsigned integer from memory."""
        if not self.is_connected():
            raise Exception("Not connected to emulator")
        return self.emulator_info.read_u8(address)  # pyright: ignore[reportOptionalMemberAccess]

    def read_u16(self, address: int) -> int:
        """Read a 16-bit unsigned integer from memory."""
        if not self.is_connected():
            raise Exception("Not connected to emulator")
        return self.emulator_info.read_u16(address)  # pyright: ignore[reportOptionalMemberAccess]

    def read_u32(self, address: int) -> int:
        """Read a 32-bit unsigned integer from memory."""
        if not self.is_connected():
            raise Exception("Not connected to emulator")
        return self.emulator_info.read_u32(address)  # pyright: ignore[reportOptionalMemberAccess]

    def write_u8(self, address: int, value: int):
        """Write an 8-bit unsigned integer to memory."""
        if not self.is_connected():
            raise Exception("Not connected to emulator")
        self.emulator_info.write_u8(address, value)  # pyright: ignore[reportOptionalMemberAccess]

    def write_u16(self, address: int, value: int):
        """Write a 16-bit unsigned integer to memory."""
        if not self.is_connected():
            raise Exception("Not connected to emulator")
        self.emulator_info.write_u16(address, value)  # pyright: ignore[reportOptionalMemberAccess]

    def write_u32(self, address: int, value: int):
        """Write a 32-bit unsigned integer to memory."""
        if not self.is_connected():
            raise Exception("Not connected to emulator")
        self.emulator_info.write_u32(address, value)  # pyright: ignore[reportOptionalMemberAccess]

    def read_bytestring(self, address: int, length: int) -> str:
        """Read a bytestring from memory."""
        if not self.is_connected():
            raise Exception("Not connected to emulator")
        return self.emulator_info.read_bytestring(address, length)  # pyright: ignore[reportOptionalMemberAccess]

    def write_bytestring(self, address: int, data: str):
        """Write a bytestring to memory."""
        if not self.is_connected():
            raise Exception("Not connected to emulator")
        self.emulator_info.write_bytestring(address, data)  # pyright: ignore[reportOptionalMemberAccess]

    async def wait_for_emulator(self, validate: Optional[Callable[["EmuLoaderClient"], bool]] = None):
        """Wait for emulator to connect and optionally validate a condition (e.g. ROM loaded).

        Args:
            validate: An optional callable that receives this client instance and returns True
                      when the emulator state is considered valid (e.g. the correct ROM is loaded).
                      If None, only the emulator connection is required.
        """
        stop_spam = False
        clear_waiting_message = True

        if not stop_spam:
            logger.info("Waiting on connection to emulator...")
            stop_spam = True

        while True:
            try:
                emulator_connected = False

                if not self.is_connected():
                    emulator_connected = self.connect()
                else:
                    emulator_connected = True

                valid = False
                if emulator_connected:
                    if validate is not None:
                        valid = validate(self)
                        logger.info("Emulator connected, validating...")
                    else:
                        valid = True

                while not valid:
                    if not self.is_connected():
                        emulator_connected = self.connect()
                    if clear_waiting_message:
                        logger.info("Waiting on valid state...")
                        clear_waiting_message = False
                    await asyncio.sleep(1.0)
                    if self.is_connected() and validate is not None:
                        valid = validate(self)
                    elif self.is_connected():
                        valid = True

                stop_spam = False
                logger.info("Emulator connected and ready!")
                return
            except Exception as e:
                await asyncio.sleep(1.0)
                logger.error(f"Error connecting to emulator, retrying... {str(e)}")
                self.disconnect()

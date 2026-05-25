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
        self._poll_task: Optional[asyncio.Task] = None
        self._not_connected_logged = False

    def connect(self) -> bool:
        """Connect to an available emulator."""
        self.emulator_info = connect_to_emulator()
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

    def _check_not_connected(self) -> bool:
        """Log a not-connected warning once. Returns True if NOT connected (caller should return early)."""
        if not self.is_connected():
            if not self._not_connected_logged:
                logger.warning("Not connected to emulator.")
                self._not_connected_logged = True
            return True
        return False

    # Direct memory access methods
    def read_u8(self, address: int) -> int:
        """Read an 8-bit unsigned integer from memory."""
        if self._check_not_connected():
            return 0
        return self.emulator_info.read_u8(address)  # pyright: ignore[reportOptionalMemberAccess]

    def read_u16(self, address: int) -> int:
        """Read a 16-bit unsigned integer from memory."""
        if self._check_not_connected():
            return 0
        return self.emulator_info.read_u16(address)  # pyright: ignore[reportOptionalMemberAccess]

    def read_u32(self, address: int) -> int:
        """Read a 32-bit unsigned integer from memory."""
        if self._check_not_connected():
            return 0
        return self.emulator_info.read_u32(address)  # pyright: ignore[reportOptionalMemberAccess]

    def write_u8(self, address: int, value: int):
        """Write an 8-bit unsigned integer to memory."""
        if self._check_not_connected():
            return
        self.emulator_info.write_u8(address, value)  # pyright: ignore[reportOptionalMemberAccess]

    def write_u16(self, address: int, value: int):
        """Write a 16-bit unsigned integer to memory."""
        if self._check_not_connected():
            return
        self.emulator_info.write_u16(address, value)  # pyright: ignore[reportOptionalMemberAccess]

    def write_u32(self, address: int, value: int):
        """Write a 32-bit unsigned integer to memory."""
        if self._check_not_connected():
            return
        self.emulator_info.write_u32(address, value)  # pyright: ignore[reportOptionalMemberAccess]

    def read_bytestring(self, address: int, length: int) -> str:
        """Read a bytestring from memory."""
        if self._check_not_connected():
            return ""
        return self.emulator_info.read_bytestring(address, length)  # pyright: ignore[reportOptionalMemberAccess]

    def write_bytestring(self, address: int, data: str):
        """Write a bytestring to memory."""
        if self._check_not_connected():
            return
        self.emulator_info.write_bytestring(address, data)  # pyright: ignore[reportOptionalMemberAccess]

    async def wait_for_emulator(self, validate: Optional[Callable[["EmuLoaderClient"], bool]] = None):
        """Wait for emulator to connect and optionally validate a condition (e.g. ROM loaded).

        Runs as a background task, polling every second without blocking the UI.

        Args:
            validate: An optional callable that receives this client instance and returns True
                      when the emulator state is considered valid (e.g. the correct ROM is loaded).
                      If None, only the emulator connection is required.
        """
        logged_waiting_connection = False
        logged_waiting_valid = False

        if self._poll_task is not None and not self._poll_task.done():
            return

        loop = asyncio.get_event_loop()

        async def _poll():
            nonlocal logged_waiting_connection, logged_waiting_valid
            while True:
                try:
                    if not self.is_connected():
                        if not logged_waiting_connection:
                            logger.info("Waiting on connection to emulator...")
                            logged_waiting_connection = True
                        await loop.run_in_executor(None, self.connect)
                        await asyncio.sleep(1.0)
                        continue

                    logged_waiting_connection = False

                    if validate is not None:
                        valid = await loop.run_in_executor(None, validate, self)
                        if not valid:
                            if not logged_waiting_valid:
                                logger.info("Waiting on valid state...")
                                logged_waiting_valid = True
                            await asyncio.sleep(1.0)
                            continue

                    logged_waiting_valid = False
                    self._not_connected_logged = False
                    logger.info("Emulator connected and ready!")
                    return
                except Exception as e:
                    logger.error(f"Error connecting to emulator, retrying... {str(e)}")
                    self.disconnect()
                    await asyncio.sleep(1.0)

        self._poll_task = asyncio.ensure_future(_poll())

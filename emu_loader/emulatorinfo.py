"""Emulator configuration and attachment logic for EmuLoader."""

import json
import os
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from .process import IS_LINUX, ProcessMemory, get_running_processes
from .utils import sanitize_and_trim

try:
    from CommonClient import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


EMULATOR_CONFIGS_URL = "https://killklli.github.io/EmuLoader/emulators.json"
EMULATOR_CONFIGS_LOCAL = os.path.join(os.path.dirname(__file__), "emulators.json")


class EmulatorInfo:
    """Class to store emulator information."""

    def __init__(
        self,
        id: str,
        readable_emulator_name: str,
        process_name: str,
        find_dll: bool,
        dll_name: Optional[str],
        additional_lookup: bool,
        lower_offset_range: int,
        upper_offset_range: int,
        range_step: int = 16,
        extra_offset: int = 0,
        linux_dll_name: Optional[str] = None,
        scan_memory_for_signature: bool = False,
        signature_alignment: int = 0,
    ):
        """Initialize with given parameters."""
        self.id = id
        self.readable_emulator_name = readable_emulator_name
        self.process_name = process_name
        self.find_dll = find_dll
        self.dll_name = dll_name
        self.linux_dll_name = linux_dll_name
        self.additional_lookup = additional_lookup
        self.lower_offset_range = lower_offset_range
        self.upper_offset_range = upper_offset_range
        self.range_step = range_step
        self.extra_offset = extra_offset
        self.scan_memory_for_signature = scan_memory_for_signature
        self.signature_alignment = signature_alignment
        self.connected_process: Optional[ProcessMemory] = None
        self.connected_offset: Optional[int] = None
        self.connection_error: Optional[str] = None
        self.runtime_error: Optional[str] = None

    def get_library_name(self) -> Optional[str]:
        """Get the appropriate library name for the current platform."""
        if IS_LINUX and self.linux_dll_name:
            return self.linux_dll_name
        return self.dll_name

    def get_possible_library_names(self) -> List[str]:
        """Get a list of possible library names to search for."""
        names: List[str] = []
        primary_name = self.get_library_name()
        if primary_name:
            names.append(primary_name)

        if IS_LINUX and self.dll_name:
            if self.dll_name.endswith(".dll"):
                so_name = self.dll_name[:-4] + ".so"
                if so_name not in names:
                    names.append(so_name)

            if not self.dll_name.startswith("lib"):
                lib_name = "lib" + self.dll_name
                if lib_name not in names:
                    names.append(lib_name)
                if lib_name.endswith(".dll"):
                    lib_so_name = lib_name[:-4] + ".so"
                    if lib_so_name not in names:
                        names.append(lib_so_name)

        return [name for name in names if name]

    def disconnect(self):
        """Disconnect emulator from process management."""
        if self.connected_process:
            self.connected_process.close()
        self.connected_offset = None
        self.connected_process = None

    def raiseError(self, msg: str):
        """Raise an error and log it."""
        print(msg)
        self.connection_error = msg

    def attach_to_emulator(self) -> Optional[Tuple[ProcessMemory, int]]:
        """Grab memory addresses of where emulated RDRAM is."""
        self.connected_process = None
        self.connected_offset = None

        target_proc = None
        processes = get_running_processes()

        for proc in processes:
            if proc["name"] and proc["name"].lower().startswith(self.process_name.lower()):
                target_proc = proc
                break
        if not target_proc:
            self.raiseError(f"Could not find process '{self.process_name}'")
            return None

        try:
            pm = ProcessMemory(target_proc["name"])
        except Exception as e:
            self.raiseError(f"Failed to attach to process: {str(e)}")
            return None

        address_dll = 0
        if self.find_dll:
            possible_names = self.get_possible_library_names()
            for module in pm.list_modules():
                for lib_name in possible_names:
                    if module.name.lower() == lib_name.lower() and module.lpBaseOfDll:
                        address_dll = module.lpBaseOfDll
                        break
                if address_dll != 0:
                    break

            if address_dll == 0 and self.id == "BizHawk":
                address_dll = 2024407040  # fallback guess
            elif address_dll == 0:
                searched_names = ", ".join(possible_names)
                self.raiseError(f"Could not find any of [{searched_names}] in {self.readable_emulator_name}")
                return None

        has_seen_nonzero = False
        for pot_off in range(self.lower_offset_range, self.upper_offset_range, self.range_step):
            if self.additional_lookup:
                rom_addr_start = address_dll + pot_off
                try:
                    read_address = pm.read_longlong(rom_addr_start)
                except Exception:
                    continue
                if read_address != 0:
                    has_seen_nonzero = True
            else:
                read_address = address_dll + pot_off

            addr = read_address + self.extra_offset + 0x759290

            try:
                test_value = pm.read_int(addr)
            except Exception:
                continue
            if test_value != 0:
                has_seen_nonzero = True
            if test_value == 0x52414D42:
                self.connected_process = pm
                self.connected_offset = read_address + self.extra_offset
                self.writeBytes(0x807ED6A0, 4, 1)  # Connection validation
                return (pm, read_address + self.extra_offset)

        if not has_seen_nonzero:
            self.raiseError(f"Could not read any data from {self.readable_emulator_name}")

        return None

    def readBytes(self, address: int, size: int) -> int:
        """Read a series of bytes and cast to an int with N64 address fixing."""
        if self.connected_process is None or self.connected_offset is None:
            self.runtime_error = "Not connected to a process, exiting"
            raise Exception(self.runtime_error)
        if address & 0x80000000:
            address &= 0x7FFFFFFF

        if size == 1:
            remainder = address % 4
            if remainder == 0:
                address += 3
            elif remainder == 1:
                address += 1
            elif remainder == 2:
                address -= 1
            elif remainder == 3:
                address -= 3
        elif size == 2:
            remainder = address % 4
            if remainder in (2, 3):
                address -= 2
            elif remainder in (0, 1):
                address += 2

        mem_address = self.connected_offset + address
        data = self.connected_process.read_bytes(mem_address, size)
        return int.from_bytes(data, "little")

    def writeBytes(self, address: int, size: int, value: int):
        """Write a series of bytes to memory with N64 address fixing."""
        if self.connected_process is None or self.connected_offset is None:
            self.runtime_error = "Not connected to a process, exiting"
            raise Exception(self.runtime_error)
        if address & 0x80000000:
            address &= 0x7FFFFFFF

        if size == 1:
            remainder = address % 4
            if remainder == 0:
                address += 3
            elif remainder == 1:
                address += 1
            elif remainder == 2:
                address -= 1
            elif remainder == 3:
                address -= 3
        elif size == 2:
            remainder = address % 4
            if remainder in (2, 3):
                address -= 2
            elif remainder in (0, 1):
                address += 2

        mem_address = self.connected_offset + address
        data = value.to_bytes(size, byteorder="little")
        self.connected_process.write_bytes(mem_address, data, size)

    def read_u8(self, address: int) -> int:
        """Read an 8-bit unsigned integer from memory."""
        return self.readBytes(address, 1)

    def read_u16(self, address: int) -> int:
        """Read a 16-bit unsigned integer from memory."""
        return self.readBytes(address, 2)

    def read_u32(self, address: int) -> int:
        """Read a 32-bit unsigned integer from memory."""
        return self.readBytes(address, 4)

    def write_u8(self, address: int, value: int):
        """Write an 8-bit unsigned integer to memory."""
        self.writeBytes(address, 1, value)

    def write_u16(self, address: int, value: int):
        """Write a 16-bit unsigned integer to memory."""
        self.writeBytes(address, 2, value)

    def write_u32(self, address: int, value: int):
        """Write a 32-bit unsigned integer to memory."""
        self.writeBytes(address, 4, value)

    def read_bytestring(self, address: int, length: int) -> str:
        """Read a bytestring from memory."""
        result = ""
        for i in range(length):
            byte_val = self.read_u8(address + i)
            if byte_val == 0:
                break
            result += chr(byte_val)
        return result

    def write_bytestring(self, address: int, data: str):
        """Write a bytestring to memory."""
        sanitized_data = sanitize_and_trim(data)
        for i, char in enumerate(sanitized_data):
            self.write_u8(address + i, ord(char))
        self.write_u8(address + len(sanitized_data), 0)


def _parse_emulator_configs(data: List[Dict[str, Any]]) -> Dict[str, EmulatorInfo]:
    """Parse a list of emulator config dicts into an EMULATOR_CONFIGS mapping."""
    configs: Dict[str, EmulatorInfo] = {}
    for entry in data:
        emu_id = entry["id"]
        configs[emu_id] = EmulatorInfo(
            id=emu_id,
            readable_emulator_name=entry["readable_emulator_name"],
            process_name=entry["process_name"],
            find_dll=entry["find_dll"],
            dll_name=entry.get("dll_name"),
            additional_lookup=entry["additional_lookup"],
            lower_offset_range=int(entry["lower_offset_range"], 16),
            upper_offset_range=int(entry["upper_offset_range"], 16),
            range_step=int(entry.get("range_step", "0x10"), 16),
            extra_offset=int(entry.get("extra_offset", "0x0"), 16),
            linux_dll_name=entry.get("linux_dll_name"),
            scan_memory_for_signature=entry.get("scan_memory_for_signature", False),
            signature_alignment=int(entry.get("signature_alignment", "0x0"), 16),
        )
    return configs


def load_emulator_configs(pull_from_web: bool = True) -> Dict[str, EmulatorInfo]:
    """Load emulator configs from GitHub Pages (if pull_from_web=True) or the local JSON file."""
    if pull_from_web:
        try:
            with urllib.request.urlopen(EMULATOR_CONFIGS_URL, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
            logger.info("Loaded emulator configs from web.")
            return _parse_emulator_configs(data)
        except Exception as e:
            logger.warning(f"Failed to fetch emulator configs from web ({e}), falling back to local file.")

    # try:
    #     with open(EMULATOR_CONFIGS_LOCAL, "r", encoding="utf-8") as f:
    #         data = json.load(f)
    #     logger.info("Loaded emulator configs from local file.")
    #     return _parse_emulator_configs(data)
    # except Exception as e:
    #     logger.error(f"Failed to load local emulator configs: {e}")
    #     return {}


def attachWrapper(emu: str, configs: Dict[str, EmulatorInfo]) -> EmulatorInfo:
    """Wrap function for attaching to an emulator."""
    configs[emu].attach_to_emulator()
    return configs[emu]


def connect_to_emulator(configs: Dict[str, EmulatorInfo]) -> Optional[EmulatorInfo]:
    """Try to connect to any available emulator and return the connected instance."""
    for emulator_info in configs.values():
        try:
            if emulator_info.attach_to_emulator():
                logger.info(f"Connected to {emulator_info.readable_emulator_name}")
                print(f"Connected to {emulator_info.readable_emulator_name}")
                return emulator_info
        except Exception as e:
            logger.info(f"Failed to connect to {emulator_info.readable_emulator_name}: {str(e)}")
            continue
    return None

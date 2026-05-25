"""EmuLoader - Cross-platform emulator memory access library."""

from .client import EmuLoaderClient
from .emulatorinfo import EMULATOR_CONFIGS, EmulatorInfo, attachWrapper, connect_to_emulator
from .process import ProcessMemory
from .ptrace import check_and_fix_ptrace_scope

__all__ = [
    "EmuLoaderClient",
    "EmulatorInfo",
    "EMULATOR_CONFIGS",
    "ProcessMemory",
    "connect_to_emulator",
    "attachWrapper",
    "check_and_fix_ptrace_scope",
]

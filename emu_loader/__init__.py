"""EmuLoader - Cross-platform emulator memory access library."""

from .emu_loader import (
    EmuLoaderClient,
    EmulatorInfo,
    EMULATOR_CONFIGS,
    ProcessMemory,
    connect_to_emulator,
    attachWrapper,
)
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

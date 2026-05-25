# EmuLoader

Cross-platform emulator memory access library for N64 emulators. Supports Windows and Linux, with built-in detection for common emulators including Project64, BizHawk, Rosalie's Mupen GUI, simple64, Parallel Launcher, RetroArch, Gopher64, and ares.

## Installation

```bash
pip install emu-loader
```

Or install from source:

```bash
pip install .
```

## Supported Emulators

| Emulator | Key |
|---|---|
| Project64 | `"Project64"` |
| Project64 4.0+ | `"Project64_v4"` |
| BizHawk | `"BizHawk"` |
| Rosalie's Mupen GUI | `"RMG"` |
| Rosalie's Mupen GUI (Flatpak) | `"RMG_Flatpak"` |
| simple64 | `"Simple64"` |
| Parallel Launcher | `"ParallelLauncher"` |
| Parallel Launcher 9.0.3+ | `"ParallelLauncher903"` |
| RetroArch (mupen64plus_next) | `"RetroArch"` |
| Gopher64 | `"Gopher64"` |
| ares | `"Ares"` |

Emulator configs are loaded from `emulators.json` (or fetched from the web at runtime) and are no longer tied to a hardcoded enum — new emulators can be added simply by updating the JSON.

## Usage

```python
from emu_loader import EmuLoaderClient

client = EmuLoaderClient()

if client.connect():
    print("Connected to emulator!")

    value = client.read_u32(0x807ED000)
    client.write_u8(0x807ED100, 0x01)

    client.disconnect()
```

## ROM Validation

**EmuLoader does not perform any ROM validation itself.** Before reading or writing game memory, you are responsible for verifying that the correct ROM is loaded in the emulator. Skipping this step may cause incorrect reads/writes against an unintended game.

A typical validation pattern is to check a known magic value or game-specific flag at a fixed memory address:

```python
from emu_loader import EmuLoaderClient

MY_ROM_MAGIC_ADDRESS = 0x80123456
MY_ROM_MAGIC_VALUE   = 0xDEADBEEF

client = EmuLoaderClient()

if client.connect():
    value = client.read_u32(MY_ROM_MAGIC_ADDRESS)
    if value != MY_ROM_MAGIC_VALUE:
        print("Wrong ROM loaded — disconnecting.")
        client.disconnect()
    else:
        print("ROM validated, proceeding.")
        # ... your game logic here
```

Adapt the address and expected value to whatever sentinel your ROM exposes (e.g. a header checksum, a version flag, or an AP-status byte).

## Memory Access

All addresses should be N64 virtual addresses (e.g. `0x80xxxxxx`). The library strips the high bit and applies byte-swap corrections automatically.

| Method | Description |
|---|---|
| `read_u8(address)` | Read 8-bit unsigned int |
| `read_u16(address)` | Read 16-bit unsigned int |
| `read_u32(address)` | Read 32-bit unsigned int |
| `write_u8(address, value)` | Write 8-bit unsigned int |
| `write_u16(address, value)` | Write 16-bit unsigned int |
| `write_u32(address, value)` | Write 32-bit unsigned int |
| `read_bytestring(address, length)` | Read a string from memory |
| `write_bytestring(address, data)` | Write a sanitized string to memory |

## Linux Notes

On Linux, memory access uses `/proc/<pid>/mem`. If ptrace restrictions are enabled (`/proc/sys/kernel/yama/ptrace_scope` > 0), the library will attempt to relax them automatically using `sudo`. You may be prompted for your password.

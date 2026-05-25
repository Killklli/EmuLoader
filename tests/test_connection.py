"""Simple test script to verify emulator connection."""

from emu_loader import EmuLoaderClient

client = EmuLoaderClient()

print("Attempting to connect to emulator...")
if client.connect():
    print(f"✓ Connected successfully!")

    try:
        # Read the start of N64 RDRAM (within the 8MB range)
        val = client.read_u32(0x80000300)
        print(f"✓ Memory read OK - 0x80000300 = 0x{val:08X}")
    except Exception as e:
        print(f"✗ Memory read failed: {e}")

    client.disconnect()
    print("✓ Disconnected cleanly.")
else:
    print("✗ Could not connect to any emulator. Make sure one is running with a ROM loaded.")

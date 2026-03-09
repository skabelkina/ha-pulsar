#!/usr/bin/env python3
"""Launch all 6 water meter type emulators (A-F) and heat meter emulator simultaneously."""

import sys
import threading
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from water_meter_type_a_emulator import WaterMeterTypeAEmulator
from water_meter_type_b_emulator import WaterMeterTypeBEmulator
from water_meter_type_c_emulator import WaterMeterTypeCEmulator
from water_meter_type_d_emulator import WaterMeterTypeDEmulator
from water_meter_type_e_emulator import WaterMeterTypeEEmulator
from water_meter_type_f_emulator import WaterMeterTypeFEmulator
from heat_meter_emulator import HeatMeterEmulator


def main():
    """Start all emulators in separate threads."""
    print("=" * 70)
    print("PulsarM Emulator Suite - All Types")
    print("=" * 70)
    print()
    print("Starting emulators...")
    print()

    # Create emulators
    type_a = WaterMeterTypeAEmulator(port=9601)
    type_b = WaterMeterTypeBEmulator(port=9602)
    type_c = WaterMeterTypeCEmulator(port=9603)
    type_d = WaterMeterTypeDEmulator(port=9604)
    type_e = WaterMeterTypeEEmulator(port=9605)
    type_f = WaterMeterTypeFEmulator(port=9606)
    heat = HeatMeterEmulator(port=9607)

    # Start all emulators in threads
    threads = []
    emulators = [type_a, type_b, type_c, type_d, type_e, type_f, heat]

    for emulator in emulators:
        thread = threading.Thread(target=emulator.start, daemon=False)
        thread.start()
        threads.append(thread)

    print("✓ Type A (Pulse Modules)     - Port 9601 - Address: 12345678 - ID: 260")
    print("✓ Type B (Mechanical)       - Port 9602 - Address: 12345678 - ID: 260")
    print("✓ Type C (RS485)             - Port 9603 - Address: 12345678 - ID: 98")
    print("✓ Type D (Two-Tariff)        - Port 9604 - Address: 12345678 - ID: 370")
    print("✓ Type E (Electronic Gen 1)  - Port 9605 - Address: 12345678 - ID: 439")
    print("✓ Type F (Electronic Gen 2)  - Port 9606 - Address: 12345678 - ID: 439")
    print("✓ Heat Meter                 - Port 9607 - Address: 87654321 - ID: 0x0043")
    print()
    print("Connect using:")
    print("  Type A: 127.0.0.1:9601")
    print("  Type B: 127.0.0.1:9602")
    print("  Type C: 127.0.0.1:9603")
    print("  Type D: 127.0.0.1:9604")
    print("  Type E: 127.0.0.1:9605")
    print("  Type F: 127.0.0.1:9606")
    print("  Heat:   127.0.0.1:9607")
    print()
    print("Press Ctrl+C to stop...")
    print()

    try:
        # Keep main thread alive
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        print("\n")
        print("Shutting down emulators...")
        for emulator in emulators:
            emulator.stop()
        print("✓ Emulators stopped")
        sys.exit(0)


if __name__ == "__main__":
    main()

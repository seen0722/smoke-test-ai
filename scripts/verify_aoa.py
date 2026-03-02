#!/usr/bin/env python3
"""
AOA2 HID 功能驗證腳本。
在沒有 ADB 的 DUT 上驗證 AOA HID 鍵盤/觸控功能。

Usage: .venv/bin/python scripts/verify_aoa.py [--vid 0x099E] [--pid 0x02B1]
"""
import sys
import time
import argparse
import usb.core
import usb.util
from smoke_test_ai.drivers.aoa_hid import (
    AoaHidDriver, HID_KEYBOARD_DESCRIPTOR, HID_TOUCH_DESCRIPTOR,
)

KEYBOARD_HID_ID = 1
TOUCH_HID_ID = 2

# Screen resolution (T70 default)
SCREEN_W = 1080
SCREEN_H = 2400


def list_usb_devices():
    """List all connected USB devices."""
    print("=== Connected USB Devices ===")
    found = False
    for dev in usb.core.find(find_all=True):
        mfr = ""
        prod = ""
        try:
            mfr = usb.util.get_string(dev, dev.iManufacturer) if dev.iManufacturer else "?"
        except Exception:
            mfr = "?"
        try:
            prod = usb.util.get_string(dev, dev.iProduct) if dev.iProduct else "?"
        except Exception:
            prod = "?"
        print(f"  VID=0x{dev.idVendor:04X}  PID=0x{dev.idProduct:04X}  {mfr} / {prod}")
        found = True
    if not found:
        print("  (no USB devices found)")
    print()


def test_find_device(hid: AoaHidDriver) -> bool:
    """Step 1: Find the Android device via USB."""
    print("[1/7] Finding USB device...")
    try:
        hid.find_device()
        if hid._in_accessory_mode:
            print(f"  PASS: Device found (already in Accessory mode)")
        else:
            print(f"  PASS: Device found (VID=0x{hid.vendor_id:04X}, PID=0x{hid.product_id:04X})")
        return True
    except RuntimeError as e:
        print(f"  FAIL: {e}")
        return False


def test_start_accessory(hid: AoaHidDriver) -> bool:
    """Step 2: Switch to AOA2 Accessory mode."""
    print("[2/7] Switching to Accessory mode...")
    try:
        hid.start_accessory()
        print(f"  PASS: Device in Accessory mode")
        return True
    except RuntimeError as e:
        print(f"  FAIL: {e}")
        return False


def test_register_keyboard(hid: AoaHidDriver) -> bool:
    """Step 3: Register keyboard HID."""
    print("[3/7] Registering keyboard HID...")
    try:
        hid.register_hid(KEYBOARD_HID_ID, HID_KEYBOARD_DESCRIPTOR)
        print(f"  PASS: Keyboard HID registered (id={KEYBOARD_HID_ID}, desc={len(HID_KEYBOARD_DESCRIPTOR)} bytes)")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def test_register_touch(hid: AoaHidDriver) -> bool:
    """Step 4: Register touch/mouse HID."""
    print("[4/7] Registering touch HID...")
    try:
        hid.register_touch(TOUCH_HID_ID)
        print(f"  PASS: Touch HID registered (id={TOUCH_HID_ID}, desc={len(HID_TOUCH_DESCRIPTOR)} bytes)")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def test_wake_screen(hid: AoaHidDriver) -> bool:
    """Step 5: Wake screen using HID mouse movement."""
    print("[5/7] Waking screen (HID mouse movement)...")
    try:
        hid.wake_screen(TOUCH_HID_ID)
        time.sleep(1)
        print("  PASS: Wake screen command sent (check DUT screen)")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def test_tap_center(hid: AoaHidDriver) -> bool:
    """Step 6: Tap center of screen."""
    print(f"[6/7] Tapping screen center ({SCREEN_W // 2}, {SCREEN_H // 2})...")
    try:
        hid.tap(TOUCH_HID_ID, SCREEN_W // 2, SCREEN_H // 2, SCREEN_W, SCREEN_H)
        time.sleep(0.5)
        print("  PASS: Tap sent (check DUT for touch response)")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def test_swipe_up(hid: AoaHidDriver) -> bool:
    """Step 7: Swipe up on screen (simulate unlock gesture)."""
    print(f"[7/7] Swiping up ({SCREEN_W // 2}, 1800 -> {SCREEN_W // 2}, 600)...")
    try:
        hid.swipe(TOUCH_HID_ID, SCREEN_W // 2, 1800, SCREEN_W // 2, 600,
                  SCREEN_W, SCREEN_H, steps=15, duration=0.4)
        time.sleep(0.5)
        print("  PASS: Swipe sent (check DUT for swipe response)")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def cleanup(hid: AoaHidDriver):
    """Unregister HID devices."""
    print("\nCleaning up HID devices...")
    try:
        hid.unregister_hid(KEYBOARD_HID_ID)
        hid.unregister_hid(TOUCH_HID_ID)
        print("  HID devices unregistered")
    except Exception as e:
        print(f"  Cleanup warning: {e}")
    hid.close()


def main():
    parser = argparse.ArgumentParser(description="AOA2 HID verification on DUT")
    parser.add_argument("--vid", default="0x099E", help="USB Vendor ID (hex, default: 0x099E)")
    parser.add_argument("--pid", default="0x02B1", help="USB Product ID (hex, default: 0x02B1)")
    parser.add_argument("--list", action="store_true", help="List USB devices and exit")
    parser.add_argument("--screen-w", type=int, default=1080, help="Screen width (default: 1080)")
    parser.add_argument("--screen-h", type=int, default=2400, help="Screen height (default: 2400)")
    args = parser.parse_args()

    global SCREEN_W, SCREEN_H
    SCREEN_W = args.screen_w
    SCREEN_H = args.screen_h

    list_usb_devices()

    if args.list:
        return

    vid = int(args.vid, 16)
    pid = int(args.pid, 16)
    print(f"=== AOA2 HID Verification ===")
    print(f"Target: VID=0x{vid:04X} PID=0x{pid:04X}")
    print(f"Screen: {SCREEN_W}x{SCREEN_H}")
    print()

    hid = AoaHidDriver(vendor_id=vid, product_id=pid)
    results = []

    try:
        # Step 1: Find device
        ok = test_find_device(hid)
        results.append(("Find Device", ok))
        if not ok:
            print("\nDevice not found. Cannot proceed.")
            return

        # Step 2: Switch to Accessory mode
        ok = test_start_accessory(hid)
        results.append(("Start Accessory", ok))
        if not ok:
            print("\nFailed to switch to Accessory mode. Cannot proceed.")
            return

        # Step 3: Register keyboard
        ok = test_register_keyboard(hid)
        results.append(("Register Keyboard", ok))

        # Step 4: Register touch
        ok = test_register_touch(hid)
        results.append(("Register Touch", ok))
        if not ok:
            print("\nTouch registration failed. Cannot test touch features.")
            cleanup(hid)
            return

        time.sleep(1)  # Allow device to recognize HID

        # Step 5: Wake screen
        ok = test_wake_screen(hid)
        results.append(("Wake Screen", ok))

        time.sleep(2)  # Wait for screen to wake

        # Step 6: Tap center
        ok = test_tap_center(hid)
        results.append(("Tap Center", ok))

        time.sleep(1)

        # Step 7: Swipe up
        ok = test_swipe_up(hid)
        results.append(("Swipe Up", ok))

    finally:
        cleanup(hid)

    # Summary
    print("\n=== Results ===")
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
    print(f"\n{passed}/{total} passed")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()

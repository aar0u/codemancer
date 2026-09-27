#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["evdev"]
# ///
"""Key sniffer: press any key to see its evdev code and device."""
import asyncio
from evdev import InputDevice, ecodes, list_devices


async def print_events(device: InputDevice) -> None:
    try:
        async for event in device.async_read_loop():
            if event.type == ecodes.EV_KEY:
                action = (
                    "按下 (DOWN)"
                    if event.value == 1
                    else ("松开 (UP)" if event.value == 0 else "长按 (HOLD)")
                )
                name = ecodes.KEY.get(
                    event.code, ecodes.BTN.get(event.code, f"CODE_{event.code}")
                )
                print(f"[{device.name}] -> {name} ({action})")
    except OSError:
        pass


async def main() -> None:
    devices = []
    for path in list_devices():
        try:
            d = InputDevice(path)
            if "ydotool" in d.name.lower() or "virtual" in d.name.lower():
                d.close()
                continue
            devices.append(d)
        except OSError:
            pass

    if not devices:
        print("未找到输入设备。请确认是否有权限读取 /dev/input (是否在 input 组或加 sudo)。")
        return

    print("已监听以下设备：")
    for d in devices:
        print(f"  - {d.path}: {d.name}")
    print("\n👉 请按一下 Keychron C1 上的麦克风键（Ctrl+C 退出）：\n")

    try:
        await asyncio.gather(*(print_events(d) for d in devices))
    finally:
        for d in devices:
            d.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n已退出。")

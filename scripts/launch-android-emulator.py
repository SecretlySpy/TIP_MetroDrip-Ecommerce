#!/usr/bin/env python3
"""Launch MetroDrip's named Android emulator and wait for a complete boot."""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--avd", default="MetroDrip_Pixel_API36", help="exact AVD name")
    parser.add_argument("--port", type=int, default=5554, help="even emulator console port")
    parser.add_argument("--timeout", type=float, default=240, help="maximum boot wait in seconds")
    return parser.parse_args()


def _android_sdk_root():
    candidates = [
        os.environ.get("ANDROID_HOME"),
        os.environ.get("ANDROID_SDK_ROOT"),
    ]
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(str(Path(local_app_data) / "Android" / "Sdk"))
    elif sys.platform == "darwin":
        candidates.append(str(Path.home() / "Library" / "Android" / "sdk"))
    else:
        candidates.append(str(Path.home() / "Android" / "Sdk"))

    for candidate in candidates:
        if candidate and Path(candidate).is_dir():
            return Path(candidate)
    raise RuntimeError(
        "Android SDK not found. Set ANDROID_HOME or run the platform setup guide first."
    )


def _executable(sdk_root, relative_path):
    suffix = ".exe" if os.name == "nt" else ""
    executable = sdk_root / f"{relative_path}{suffix}"
    if not executable.is_file():
        raise RuntimeError(f"Required Android SDK executable not found: {executable}")
    return str(executable)


def _run(command, *, timeout=10):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _device_state(adb, serial):
    result = _run([adb, "devices"])
    for line in result.stdout.splitlines()[1:]:
        fields = line.split()
        if fields and fields[0] == serial:
            return fields[1] if len(fields) > 1 else "unknown"
    return None


def _running_avd_name(adb, serial):
    result = _run([adb, "-s", serial, "emu", "avd", "name"])
    if result.returncode != 0:
        return None
    names = [line.strip() for line in result.stdout.splitlines() if line.strip() != "OK"]
    return names[0] if names else None


def _start_detached(command):
    options = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        options["start_new_session"] = True
    return subprocess.Popen(command, **options)


def ensure_emulator_ready(*, avd, port, timeout):
    """Start only *avd* on *port*, then validate identity and boot completion."""
    if port < 5554 or port > 5682 or port % 2:
        raise ValueError("port must be an even emulator port from 5554 through 5682")
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")

    sdk_root = _android_sdk_root()
    adb = _executable(sdk_root, "platform-tools/adb")
    emulator = _executable(sdk_root, "emulator/emulator")
    serial = f"emulator-{port}"

    available = _run([emulator, "-list-avds"]).stdout.splitlines()
    if avd not in {name.strip() for name in available}:
        raise RuntimeError(
            f"AVD '{avd}' is not installed. Run scripts/setup-android-emulator.ps1 first."
        )

    _run([adb, "start-server"])
    state = _device_state(adb, serial)
    process = None
    if state is None:
        print(f"Launching AVD '{avd}' as {serial}...")
        process = _start_detached(
            [emulator, "-avd", avd, "-port", str(port), "-netdelay", "none", "-netspeed", "full"]
        )
    else:
        print(f"Found {serial} in state '{state}'; waiting for it to become ready...")

    deadline = time.monotonic() + timeout
    identity_checked = False
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"Emulator process exited early with status {process.returncode}.")

        if _device_state(adb, serial) == "device":
            running_avd = _running_avd_name(adb, serial)
            if running_avd:
                identity_checked = True
                if running_avd != avd:
                    raise RuntimeError(
                        f"{serial} is running AVD '{running_avd}', not required AVD '{avd}'."
                    )

                boot_complete = _run(
                    [adb, "-s", serial, "shell", "getprop", "sys.boot_completed"]
                ).stdout.strip()
                boot_animation = _run(
                    [adb, "-s", serial, "shell", "getprop", "init.svc.bootanim"]
                ).stdout.strip()
                if boot_complete == "1" and boot_animation == "stopped":
                    print(f"Ready: AVD '{avd}' is fully booted as {serial}.")
                    return serial

        time.sleep(1)

    identity_note = "identity verified" if identity_checked else "identity not yet available"
    raise TimeoutError(
        f"Timed out after {timeout:g}s waiting for AVD '{avd}' on {serial} ({identity_note})."
    )


def main():
    args = parse_args()
    try:
        ensure_emulator_ready(avd=args.avd, port=args.port, timeout=args.timeout)
    except (RuntimeError, TimeoutError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()

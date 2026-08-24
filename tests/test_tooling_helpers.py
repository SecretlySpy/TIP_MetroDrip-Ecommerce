"""Unit contracts for local-development readiness helpers."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _load_script(filename):
    path = REPOSITORY_ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _completed(stdout=""):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def test_android_emulator_helper_rejects_unsafe_console_ports():
    helper = _load_script("launch-android-emulator.py")

    with pytest.raises(ValueError, match="even emulator port"):
        helper.ensure_emulator_ready(avd="MetroDrip_Pixel_API36", port=5555, timeout=1)


def test_android_emulator_helper_requires_the_exact_named_avd(monkeypatch):
    helper = _load_script("launch-android-emulator.py")
    monkeypatch.setattr(helper, "_android_sdk_root", lambda: Path("/test-sdk"))
    monkeypatch.setattr(helper, "_executable", lambda _root, path: path)
    monkeypatch.setattr(helper, "_run", lambda _command, **_kwargs: _completed("Other_AVD\n"))

    with pytest.raises(RuntimeError, match="is not installed"):
        helper.ensure_emulator_ready(avd="MetroDrip_Pixel_API36", port=5554, timeout=1)


def test_android_emulator_helper_refuses_a_different_avd_on_the_reserved_port(monkeypatch):
    helper = _load_script("launch-android-emulator.py")
    monkeypatch.setattr(helper, "_android_sdk_root", lambda: Path("/test-sdk"))
    monkeypatch.setattr(helper, "_executable", lambda _root, path: path)
    monkeypatch.setattr(
        helper,
        "_run",
        lambda command, **_kwargs: (
            _completed("MetroDrip_Pixel_API36\n") if command[1:] == ["-list-avds"] else _completed()
        ),
    )
    monkeypatch.setattr(helper, "_device_state", lambda _adb, _serial: "device")
    monkeypatch.setattr(helper, "_running_avd_name", lambda _adb, _serial: "Personal_AVD")

    with pytest.raises(RuntimeError, match="not required AVD"):
        helper.ensure_emulator_ready(avd="MetroDrip_Pixel_API36", port=5554, timeout=1)


def test_android_emulator_helper_reports_only_a_fully_booted_named_avd(monkeypatch):
    helper = _load_script("launch-android-emulator.py")
    monkeypatch.setattr(helper, "_android_sdk_root", lambda: Path("/test-sdk"))
    monkeypatch.setattr(helper, "_executable", lambda _root, path: path)

    def fake_run(command, **_kwargs):
        if command[1:] == ["-list-avds"]:
            return _completed("MetroDrip_Pixel_API36\n")
        if command[-2:] == ["getprop", "sys.boot_completed"]:
            return _completed("1\n")
        if command[-2:] == ["getprop", "init.svc.bootanim"]:
            return _completed("stopped\n")
        return _completed()

    monkeypatch.setattr(helper, "_run", fake_run)
    monkeypatch.setattr(helper, "_device_state", lambda _adb, _serial: "device")
    monkeypatch.setattr(
        helper,
        "_running_avd_name",
        lambda _adb, _serial: "MetroDrip_Pixel_API36",
    )

    serial = helper.ensure_emulator_ready(
        avd="MetroDrip_Pixel_API36",
        port=5554,
        timeout=1,
    )

    assert serial == "emulator-5554"

"""Regression tests for the minimal GitHub Pages publication artifact."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build-pages-site.py"
SPEC = importlib.util.spec_from_file_location("build_pages_site", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
BUILD_PAGES_SITE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD_PAGES_SITE)


def test_builder_publishes_only_the_guide_and_its_referenced_images(tmp_path: Path) -> None:
    output = tmp_path / "site"

    deployed = BUILD_PAGES_SITE.build(output)

    disk_files = sorted(path.relative_to(output) for path in output.rglob("*") if path.is_file())
    assert sorted(deployed) == disk_files
    assert deployed[0] == Path("index.html")
    assert Path("docs/images/favicon.svg") in deployed
    assert Path("docs/images/step-12-app-launched.png") in deployed
    assert all(
        path == Path("index.html") or path.is_relative_to("docs/images") for path in deployed
    )
    assert Path("README.md") not in deployed
    assert Path("backend.log") not in deployed


def test_builder_refuses_to_overlay_an_existing_directory(tmp_path: Path) -> None:
    output = tmp_path / "site"
    output.mkdir()

    with pytest.raises(FileExistsError, match="Output already exists"):
        BUILD_PAGES_SITE.build(output)


@pytest.mark.parametrize("path", ["../outside.png", "README.md", "docs/images/README.md"])
def test_builder_rejects_non_public_asset_paths(path: str) -> None:
    with pytest.raises((FileNotFoundError, ValueError)):
        BUILD_PAGES_SITE._safe_source(path)

#!/usr/bin/env python3
"""Build the smallest complete artifact for the MetroDrip GitHub Pages guide."""

from __future__ import annotations

import argparse
import shutil
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "index.html"
PUBLIC_ASSET_ROOT = (ROOT / "docs" / "images").resolve()
PUBLIC_ASSET_SUFFIXES = {".png", ".svg"}


class LocalAssetParser(HTMLParser):
    """Collect local image, script, and stylesheet references from the guide."""

    def __init__(self) -> None:
        super().__init__()
        self.references: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        attribute = "src" if tag in {"img", "script"} else "href"
        if tag not in {"a", "img", "link", "script"}:
            return
        value = attributes.get(attribute)
        if not value or value.startswith("#"):
            return
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc or not parsed.path:
            return
        self.references.add(unquote(parsed.path))


def _safe_source(relative_path: str) -> tuple[Path, Path]:
    relative = Path(relative_path)
    if relative.is_absolute():
        raise ValueError(f"Guide asset must use a relative path: {relative_path}")

    unresolved_source = ROOT / relative
    if unresolved_source.is_symlink():
        raise ValueError(f"Guide asset must not be a symbolic link: {relative_path}")
    source = unresolved_source.resolve()
    try:
        source.relative_to(ROOT)
    except ValueError as error:
        raise ValueError(f"Guide asset escapes the repository: {relative_path}") from error
    try:
        source.relative_to(PUBLIC_ASSET_ROOT)
    except ValueError as error:
        raise ValueError(
            f"Guide asset is outside the public image directory: {relative_path}"
        ) from error
    if source.suffix.lower() not in PUBLIC_ASSET_SUFFIXES:
        raise ValueError(f"Guide asset type is not public: {relative_path}")
    if not source.is_file():
        raise FileNotFoundError(f"Guide asset does not exist: {relative_path}")
    return relative, source


def build(output: Path) -> list[Path]:
    """Copy the guide and every referenced local asset into a new directory."""

    output = output.resolve()
    if output == ROOT:
        raise ValueError("Output must be a dedicated directory, not the repository root")
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")

    parser = LocalAssetParser()
    parser.feed(GUIDE.read_text(encoding="utf-8"))
    assets = [_safe_source(reference) for reference in sorted(parser.references)]

    output.mkdir(parents=True)
    shutil.copy2(GUIDE, output / "index.html")
    deployed = [Path("index.html")]
    for relative, source in assets:
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        deployed.append(relative)

    print(f"Built {output} with {len(deployed)} files.")
    for path in deployed:
        print(path.as_posix())
    return deployed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    build(arguments.output)


if __name__ == "__main__":
    main()

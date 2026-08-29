"""Structural regression checks for the published GitHub Pages setup guide."""

from __future__ import annotations

import struct
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDE_PATH = ROOT / "index.html"

STEP_IMAGES = {
    "install": ["step-01-tools-verified.png"],
    "clone": ["step-02-code-cloned.png"],
    "venv": ["step-03-python-ready.png"],
    "config": ["step-04-env-created-and-ignored.png"],
    "database": ["step-05-data-services-healthy.png"],
    "migrate": ["step-06-demo-seed-complete.png"],
    "run": ["step-07-storefront-home.png", "step-07-category-menu.png"],
    "admin": ["step-08-merchant-console.png", "step-08-admin-console.png"],
    "verify": [
        "step-09-category-filter.png",
        "step-09-cart.png",
        "step-09-checkout.png",
    ],
    "tests": ["step-10-tests-passed.png"],
    "mobile-setup": [
        "step-11-mobile-dependencies-ready.png",
        "step-11-android-avd-ready.png",
    ],
    "mobile-run": [
        "step-12-app-launched.png",
        "step-12-mobile-home.png",
        "step-12-mobile-product-detail.png",
        "step-12-mobile-cart.png",
        "step-12-mobile-checkout.png",
        "step-12-mobile-order-tracking.png",
        "step-12-mobile-notifications.png",
        "step-12-order-in-merchant-console.png",
    ],
    "stop": ["step-13-safe-stop.png"],
}


class GuideParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.internal_links: list[str] = []
        self.images: list[dict[str, str]] = []
        self.image_links: dict[str, str] = {}
        self.svg_count = 0
        self.svgs: list[dict[str, str]] = []
        self.svg_title_ids: set[str] = set()
        self.svg_desc_ids: set[str] = set()
        self.figures: list[dict[str, object]] = []
        self._active_link: str | None = None
        self._active_figure: dict[str, object] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        if element_id := attributes.get("id"):
            self.ids.append(element_id)
        if tag == "a":
            self._active_link = attributes.get("href")
            if self._active_link and self._active_link.startswith("#"):
                self.internal_links.append(self._active_link[1:])
        elif tag == "img":
            self.images.append(attributes)
            if self._active_figure is not None:
                self._active_figure["images"].append(attributes.get("src", ""))
            if self._active_link:
                self.image_links[attributes.get("src", "")] = self._active_link
        elif tag == "figure":
            assert self._active_figure is None, "Nested figures are not supported"
            self._active_figure = {"images": [], "has_caption": False}
        elif tag == "figcaption" and self._active_figure is not None:
            self._active_figure["has_caption"] = True
        elif tag == "svg":
            self.svg_count += 1
            self.svgs.append(attributes)
        elif tag == "title" and attributes.get("id"):
            self.svg_title_ids.add(attributes["id"])
        elif tag == "desc" and attributes.get("id"):
            self.svg_desc_ids.add(attributes["id"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._active_link = None
        elif tag == "figure" and self._active_figure is not None:
            self.figures.append(self._active_figure)
            self._active_figure = None


def _parse_guide() -> tuple[str, GuideParser]:
    source = GUIDE_PATH.read_text(encoding="utf-8")
    parser = GuideParser()
    parser.feed(source)
    return source, parser


def _png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as image:
        header = image.read(24)
    assert header[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    return struct.unpack(">II", header[16:24])


def _png_chunk_types(path: Path) -> list[bytes]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    chunks: list[bytes] = []
    offset = 8
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunks.append(chunk_type)
        offset += length + 12
        if chunk_type == b"IEND":
            break
    return chunks


def test_guide_ids_and_internal_links_are_valid() -> None:
    _, parser = _parse_guide()
    duplicates = sorted(
        element_id for element_id, count in Counter(parser.ids).items() if count > 1
    )
    assert duplicates == []
    assert sorted(set(parser.internal_links) - set(parser.ids)) == []


def test_every_numbered_step_has_its_expected_screenshots() -> None:
    source, _ = _parse_guide()
    for section_id, filenames in STEP_IMAGES.items():
        section_start = source.index(f'<section id="{section_id}">')
        section_end = source.index("</section>", section_start)
        section = source[section_start:section_end]
        for filename in filenames:
            assert f"docs/images/{filename}" in section, f"{filename} is missing from #{section_id}"


def test_guide_images_are_accessible_linked_and_match_their_png_dimensions() -> None:
    _, parser = _parse_guide()
    expected_sources = {
        f"docs/images/{filename}" for filenames in STEP_IMAGES.values() for filename in filenames
    } | {"docs/images/09-troubleshooting-flowchart.png"}
    assert len(parser.images) == len(expected_sources), "Guide images must not be duplicated"
    assert {image["src"] for image in parser.images} == expected_sources

    alts = [image["alt"].strip() for image in parser.images]
    assert all(alts)
    assert len(alts) == len(set(alts)), "Each guide image needs unique alternative text"

    for image in parser.images:
        src = image["src"]
        path = ROOT / src
        assert path.is_file(), f"Missing guide image: {src}"
        assert image.get("loading") == "lazy"
        assert image.get("decoding") == "async"
        assert parser.image_links.get(src) == src, (
            f"{src} is not linked to its full-resolution file"
        )
        assert (int(image["width"]), int(image["height"])) == _png_dimensions(path)
        forbidden_metadata = {b"tEXt", b"zTXt", b"iTXt", b"eXIf"}
        assert forbidden_metadata.isdisjoint(_png_chunk_types(path)), (
            f"Guide PNG contains textual or EXIF metadata: {src}"
        )

        matching_figures = [figure for figure in parser.figures if src in figure["images"]]
        assert len(matching_figures) == 1, f"{src} must appear in exactly one figure"
        assert matching_figures[0]["has_caption"], f"{src} needs a figcaption"


def test_existing_diagrams_remain_in_the_guide() -> None:
    source, parser = _parse_guide()
    assert parser.svg_count == 4
    for title_id in ("archtitle", "toolchaintitle", "nettitle", "runtitle"):
        assert f'<title id="{title_id}">' in source
    assert source.count("docs/images/09-troubleshooting-flowchart.png") >= 2
    for svg in parser.svgs:
        assert svg.get("role") == "img"
        labelled_by = svg.get("aria-labelledby", "").split()
        assert len(labelled_by) == 2
        assert labelled_by[0] in parser.svg_title_ids
        assert labelled_by[1] in parser.svg_desc_ids
    assert '<link rel="icon" href="docs/images/favicon.svg" type="image/svg+xml">' in source
    assert (ROOT / "docs/images/favicon.svg").is_file()


def test_android_emulator_guide_uses_the_deterministic_transport_commands() -> None:
    source, _ = _parse_guide()
    assert "npm run android:emulator" in source
    assert "npm run start:android:emulator" in source
    assert "adb reverse tcp:8081 tcp:8081" in source
    assert "http://10.0.2.2:8080/api/mobile/v1" in source
    assert "Failed to connect to /192.168…:8081" in source

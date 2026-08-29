"""Contrast contracts for both MetroDrip console palettes (ADR-P5-005)."""

import re
from pathlib import Path

import pytest

CSS = (Path(__file__).resolve().parents[1] / "static/css/console.css").read_text()


def _tokens(selector_pattern: str) -> dict[str, str]:
    match = re.search(rf"{selector_pattern}\s*\{{(?P<body>.*?)\n\}}", CSS, re.DOTALL)
    assert match, f"Missing theme block: {selector_pattern}"
    return dict(re.findall(r"--c-([\w-]+):\s*(#[0-9A-Fa-f]{6})\s*;", match.group("body")))


THEMES = {
    "dark": _tokens(r":root,\s*html\[data-theme=\"dark\"\]"),
    "light": _tokens(r"html\[data-theme=\"light\"\]"),
}


def _relative_luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


BODY_TEXT_PAIRS = [
    ("ink", "base"),
    ("ink", "surface"),
    ("ink", "elevated"),
    ("muted", "base"),
    ("muted", "surface"),
    ("muted", "elevated"),
    ("accent-text", "base"),
    ("accent-text", "surface"),
    ("accent-text", "elevated"),
    ("accent-text", "selected"),
    ("danger-text", "error-bg"),
    ("warning-text", "warning-bg"),
    ("success-text", "success-bg"),
    ("on-volt", "volt"),
    ("on-danger", "danger"),
    ("on-warning", "warning"),
    ("on-success", "success"),
    ("brand-ink", "brand-panel"),
    ("brand-muted", "brand-panel"),
]


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize(("foreground", "background"), BODY_TEXT_PAIRS)
def test_console_text_tokens_meet_wcag_aa(theme, foreground, background):
    palette = THEMES[theme]
    ratio = _contrast(palette[foreground], palette[background])
    assert ratio >= 4.5, f"{theme} {foreground}/{background} is only {ratio:.2f}:1"


@pytest.mark.parametrize("theme", THEMES)
def test_console_control_boundaries_and_focus_meet_non_text_contrast(theme):
    palette = THEMES[theme]

    assert _contrast(palette["control-border"], palette["elevated"]) >= 3
    for surface in ("base", "surface", "elevated"):
        assert _contrast(palette["focus"], palette[surface]) >= 3

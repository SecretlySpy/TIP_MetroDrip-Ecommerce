/**
 * MetroDrip design tokens — the ONLY colours permitted in the app.
 *
 * Ported verbatim from the execution brief §2 (identical to the web `:root`).
 * Every component resolves colours through `useTheme()`; a hardcoded hex
 * anywhere else in src/ is a bug by definition (Definition of Done: zero
 * hardcoded hex values).
 */

export type ColorScheme = 'light' | 'dark';

export interface ThemeColors {
  /** Screen background */
  paper: string;
  /** Primary text, dark section fills */
  ink: string;
  /** Cards, thumbnails, inputs */
  surface: string;
  /** Panels that are ink-backed in light mode */
  elevated: string;
  /** Primary CTA fill, accents, badges */
  volt: string;
  /** Text on any volt fill — dark in BOTH modes (§2.1 rule 2) */
  onVolt: string;
  /** Volt-family colour when used as text on light (§2.1 rule 1) */
  accentText: string;
  /** Secondary text */
  muted: string;
  /** Secondary text on ink/elevated surfaces */
  mutedOnDark: string;
  /** Hairlines, outlines — never a text colour (§2.1 rule 3) */
  border: string;
  /** Errors, low stock, destructive */
  danger: string;
}

export const lightColors: ThemeColors = {
  paper: '#FFFFFF',
  ink: '#141414',
  surface: '#F4F4F2',
  elevated: '#F4F4F2',
  volt: '#C8F031',
  onVolt: '#141414',
  accentText: '#5C6B12',
  muted: '#63635C',
  mutedOnDark: '#A8A8A0',
  border: '#E4E4DF',
  danger: '#C2282D',
};

export const darkColors: ThemeColors = {
  paper: '#0F0F0F',
  ink: '#F2F2EF',
  surface: '#1A1A1A',
  elevated: '#252524',
  volt: '#D4FF3F',
  onVolt: '#141414',
  accentText: '#D4FF3F',
  muted: '#A3A39A',
  mutedOnDark: '#A3A39A',
  border: '#2E2E2C',
  danger: '#FF7B7E',
};

/**
 * §2.1 dark-mode nuance: sections that are ink-FILLED in light mode (hero,
 * tracking header, splash) must not invert to near-white. They keep a dark
 * fill in both modes — `inkSurface` is that fill, `onInkSurface`/`onInkMuted`
 * the text on it.
 */
export interface InkSurfaceColors {
  inkSurface: string;
  onInkSurface: string;
  onInkMuted: string;
}

export const surfaceOnInk: Record<ColorScheme, InkSurfaceColors> = {
  light: { inkSurface: '#141414', onInkSurface: '#FFFFFF', onInkMuted: '#A8A8A0' },
  dark: { inkSurface: '#252524', onInkSurface: '#F2F2EF', onInkMuted: '#A3A39A' },
};

/** §2.2 — the only corner radii in the design. */
export const radius = {
  tag: 4,
  chip: 8,
  input: 10,
  card: 12,
  thumb: 14,
  pill: 9999,
} as const;

/** §2.3 — the spacing scale; screen horizontal padding is 16. */
export const space = {
  xs: 4,
  s6: 6,
  s8: 8,
  s10: 10,
  s12: 12,
  s14: 14,
  screenX: 16,
  s18: 18,
  s20: 20,
  s24: 24,
  s28: 28,
} as const;

/** §4 fixed native metrics from the design. */
export const metrics = {
  navBarHeight: 52,
  tabBarHeight: 82,
  homeIndicatorPad: 30,
  minTouchTarget: 44,
} as const;

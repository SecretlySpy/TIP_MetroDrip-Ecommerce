/**
 * Typography roles (§3). Anton = display, Inter = body, IBM Plex Mono = every
 * SKU / price / order number / waybill / uppercase micro-label — a signature
 * element, never substituted.
 */

import { PixelRatio } from 'react-native';

export const fonts = {
  display: 'Anton_400Regular',
  body: 'Inter_400Regular',
  bodyMedium: 'Inter_500Medium',
  bodySemiBold: 'Inter_600SemiBold',
  bodyBold: 'Inter_700Bold',
  mono: 'IBMPlexMono_400Regular',
  monoMedium: 'IBMPlexMono_500Medium',
  monoSemiBold: 'IBMPlexMono_600SemiBold',
} as const;

/**
 * Line height must be scaled by hand (NFR-20).
 *
 * React Native multiplies `fontSize` by the OS text-size setting, but a literal
 * `lineHeight` in a style object is a raw dp value it leaves alone. Every preset
 * below used to pair the two — `fontSize: 38, lineHeight: 42` — so at 200% the
 * glyphs rendered at 76dp inside a 42dp line box: lines overlapped and
 * descenders were cut off. Expressing line height as a *ratio* and multiplying
 * by the same scale keeps the box proportional to the text at any setting.
 *
 * `getFontScale()` is read at module load. That is correct for this app: both
 * platforms restart or recreate the activity when the system text size changes,
 * so the value cannot go stale while a screen is mounted.
 */
const fontScale = PixelRatio.getFontScale();

/** Scaled line height for a given size and ratio. */
export const lineHeightFor = (fontSize: number, ratio: number): number =>
  Math.round(fontSize * ratio * fontScale);

/** Reusable text presets matching §3's roles. */
export const type = {
  // Display faces are set tight (1.1) and body copy looser (1.4), the same
  // relationship the original fixed values encoded — now scale-aware.
  displayHero: {
    fontFamily: fonts.display,
    fontSize: 38,
    lineHeight: lineHeightFor(38, 1.1),
  },
  displayTitle: {
    fontFamily: fonts.display,
    fontSize: 28,
    lineHeight: lineHeightFor(28, 1.18),
  },
  sectionHeading: {
    fontFamily: fonts.display,
    fontSize: 20,
    lineHeight: lineHeightFor(20, 1.25),
  },
  screenTitle: { fontFamily: fonts.bodyBold, fontSize: 17 },
  body: { fontFamily: fonts.body, fontSize: 14, lineHeight: lineHeightFor(14, 1.43) },
  bodySmall: { fontFamily: fonts.body, fontSize: 13, lineHeight: lineHeightFor(13, 1.38) },
  emphasis: { fontFamily: fonts.bodySemiBold, fontSize: 14 },
  microLabel: {
    fontFamily: fonts.monoMedium,
    fontSize: 10,
    letterSpacing: 1.2,
    textTransform: 'uppercase' as const,
  },
  monoBody: { fontFamily: fonts.mono, fontSize: 13 },
  monoPrice: { fontFamily: fonts.monoSemiBold, fontSize: 14 },
} as const;

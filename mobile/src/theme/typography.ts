/**
 * Typography roles (§3). Anton = display, Inter = body, IBM Plex Mono = every
 * SKU / price / order number / waybill / uppercase micro-label. Platform
 * fallbacks preserve those roles only when a bundled font cannot load.
 */

import { Platform } from 'react-native';

export const fonts = {
  display: 'Anton_400Regular',
  body: 'Inter_400Regular',
  bodyMedium: 'Inter_500Medium',
  bodySemiBold: 'Inter_600SemiBold',
  bodyBold: 'Inter_700Bold',
  mono: 'IBMPlexMono_400Regular',
  monoMedium: 'IBMPlexMono_500Medium',
  monoSemiBold: 'IBMPlexMono_600SemiBold',
};

const systemFonts = {
  display: Platform.select({ ios: 'System', android: 'sans-serif-condensed', default: 'System' }),
  body: Platform.select({ ios: 'System', android: 'sans-serif', default: 'System' }),
  bodyMedium: Platform.select({ ios: 'System', android: 'sans-serif-medium', default: 'System' }),
  bodySemiBold: Platform.select({ ios: 'System', android: 'sans-serif-medium', default: 'System' }),
  bodyBold: Platform.select({ ios: 'System', android: 'sans-serif-medium', default: 'System' }),
  mono: Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' }),
  monoMedium: Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' }),
  monoSemiBold: Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' }),
};

/**
 * React Native applies the OS font scale to both `fontSize` and `lineHeight`.
 * Keep each line height proportional to its unscaled font size and let the
 * native text renderer scale both values once. Multiplying by
 * `PixelRatio.getFontScale()` here would scale line height twice.
 */
export const lineHeightFor = (fontSize: number, ratio: number): number =>
  Math.round(fontSize * ratio);

/** Reusable text presets matching §3's roles. */
export const type = {
  // Display faces are set tight (1.1) and body copy looser (1.4), the same
  // relationship the original fixed values encoded.
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
};

/**
 * Switch every typography role to a platform font if bundled font loading
 * fails. The app calls this once, before mounting its component tree.
 */
export function enableSystemFontFallback(): void {
  Object.assign(fonts, systemFonts);
  type.displayHero.fontFamily = fonts.display;
  type.displayTitle.fontFamily = fonts.display;
  type.sectionHeading.fontFamily = fonts.display;
  type.screenTitle.fontFamily = fonts.bodyBold;
  type.body.fontFamily = fonts.body;
  type.bodySmall.fontFamily = fonts.body;
  type.emphasis.fontFamily = fonts.bodySemiBold;
  type.microLabel.fontFamily = fonts.monoMedium;
  type.monoBody.fontFamily = fonts.mono;
  type.monoPrice.fontFamily = fonts.monoSemiBold;
}

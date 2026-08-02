/**
 * Typography roles (§3). Anton = display, Inter = body, IBM Plex Mono = every
 * SKU / price / order number / waybill / uppercase micro-label — a signature
 * element, never substituted.
 */

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

/** Reusable text presets matching §3's roles. */
export const type = {
  displayHero: { fontFamily: fonts.display, fontSize: 38, lineHeight: 42 },
  displayTitle: { fontFamily: fonts.display, fontSize: 28, lineHeight: 33 },
  sectionHeading: { fontFamily: fonts.display, fontSize: 20, lineHeight: 25 },
  screenTitle: { fontFamily: fonts.bodyBold, fontSize: 17 },
  body: { fontFamily: fonts.body, fontSize: 14, lineHeight: 20 },
  bodySmall: { fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
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

/**
 * Shared design-system primitives used by all 11 screens.
 *
 * Every colour resolves through useTheme(); §2.1 rules are enforced here once:
 *  1. volt is a background colour — text on light uses accentText
 *  2. text on a volt fill is ALWAYS onVolt
 *  3. border is never a text colour
 */

import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleProp,
  Text,
  TextStyle,
  View,
  ViewStyle,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useTheme } from '@/theme/ThemeProvider';
import { metrics, radius, space } from '@/theme/theme';
import { fonts, type } from '@/theme/typography';

/** Nav bar (§4): 52pt, back chevron ‹ at 26pt, Inter Bold 17 title. */
export function NavBar({
  title,
  onBack,
  right,
}: {
  title: string;
  onBack?: () => void;
  right?: React.ReactNode;
}) {
  const { colors } = useTheme();
  return (
    <View
      style={{
        height: metrics.navBarHeight,
        flexDirection: 'row',
        alignItems: 'center',
        paddingHorizontal: space.screenX,
        backgroundColor: colors.paper,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
      }}
    >
      <View style={{ width: metrics.minTouchTarget, alignItems: 'flex-start' }}>
        {onBack ? (
          <Pressable
            onPress={onBack}
            accessibilityRole="button"
            accessibilityLabel="Go back"
            hitSlop={10}
            style={{ minWidth: metrics.minTouchTarget, minHeight: metrics.minTouchTarget, justifyContent: 'center' }}
          >
            <Text style={{ fontSize: 26, color: colors.ink, fontFamily: fonts.body }}>‹</Text>
          </Pressable>
        ) : null}
      </View>
      <Text
        numberOfLines={1}
        style={{ ...type.screenTitle, color: colors.ink, flex: 1, textAlign: 'center' }}
      >
        {title}
      </Text>
      <View style={{ width: metrics.minTouchTarget, alignItems: 'flex-end' }}>{right}</View>
    </View>
  );
}

/** Sticky action bar (§4): outside the scroll view, home-indicator padded. */
export function StickyBar({ children }: { children: React.ReactNode }) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <View
      style={{
        paddingHorizontal: space.screenX,
        paddingTop: space.s12,
        paddingBottom: Math.max(insets.bottom, metrics.homeIndicatorPad),
        backgroundColor: colors.paper,
        borderTopWidth: 1,
        borderTopColor: colors.border,
      }}
    >
      {children}
    </View>
  );
}

type ButtonVariant = 'volt' | 'ink' | 'outline' | 'surface' | 'plain';

/** Pill button per the design; §2.1 rule 2 (onVolt) is enforced here. */
export function PillButton({
  label,
  onPress,
  variant = 'volt',
  disabled,
  loading,
  style,
  textStyle,
}: {
  label: string;
  onPress?: () => void;
  variant?: ButtonVariant;
  disabled?: boolean;
  loading?: boolean;
  style?: StyleProp<ViewStyle>;
  textStyle?: StyleProp<TextStyle>;
}) {
  const { colors } = useTheme();
  const backgrounds: Record<ButtonVariant, string> = {
    volt: colors.volt,
    ink: colors.ink,
    outline: 'transparent',
    surface: colors.surface,
    plain: 'transparent',
  };
  const textColors: Record<ButtonVariant, string> = {
    volt: colors.onVolt,
    ink: colors.paper,
    outline: colors.ink,
    surface: colors.ink,
    plain: colors.ink,
  };
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: !!disabled }}
      onPress={onPress}
      disabled={disabled || loading}
      style={[
        {
          minHeight: metrics.minTouchTarget + 8,
          borderRadius: radius.pill,
          backgroundColor: backgrounds[variant],
          borderWidth: variant === 'outline' ? 1.5 : 0,
          borderColor: colors.ink,
          alignItems: 'center',
          justifyContent: 'center',
          paddingHorizontal: space.s24,
          opacity: disabled ? 0.5 : 1,
        },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={textColors[variant]} />
      ) : (
        <Text
          style={[
            { fontFamily: fonts.bodySemiBold, fontSize: 15, color: textColors[variant] },
            textStyle,
          ]}
        >
          {label}
        </Text>
      )}
    </Pressable>
  );
}

/** IBM Plex Mono uppercase micro-label (§3 signature element). */
export function MicroLabel({
  children,
  color,
  style,
}: {
  children: React.ReactNode;
  color?: string;
  style?: StyleProp<TextStyle>;
}) {
  const { colors } = useTheme();
  return (
    <Text style={[{ ...type.microLabel, color: color ?? colors.muted }, style]}>{children}</Text>
  );
}

/** Mono price/SKU text (§3). */
export function Mono({
  children,
  size = 13,
  weight = 'regular',
  color,
  style,
}: {
  children: React.ReactNode;
  size?: number;
  weight?: 'regular' | 'medium' | 'semibold';
  color?: string;
  style?: StyleProp<TextStyle>;
}) {
  const { colors } = useTheme();
  const family =
    weight === 'semibold' ? fonts.monoSemiBold : weight === 'medium' ? fonts.monoMedium : fonts.mono;
  return (
    <Text style={[{ fontFamily: family, fontSize: size, color: color ?? colors.ink }, style]}>
      {children}
    </Text>
  );
}

/** FR-30: explicit offline state with a retry affordance. */
export function OfflineBanner({ onRetry }: { onRetry?: () => void }) {
  const { colors } = useTheme();
  return (
    <View
      style={{
        backgroundColor: colors.surface,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
        paddingVertical: space.s8,
        paddingHorizontal: space.screenX,
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}
    >
      <MicroLabel>You're offline — showing saved items</MicroLabel>
      {onRetry ? (
        <Pressable onPress={onRetry} hitSlop={12} accessibilityRole="button" accessibilityLabel="Retry">
          <MicroLabel color={colors.accentText}>Retry</MicroLabel>
        </Pressable>
      ) : null}
    </View>
  );
}

/** Empty / error states — every list has one (H-12). */
export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body?: string;
  action?: React.ReactNode;
}) {
  const { colors } = useTheme();
  return (
    <View style={{ alignItems: 'center', paddingVertical: space.s28 * 2, paddingHorizontal: space.s24 }}>
      <Text style={{ ...type.sectionHeading, color: colors.ink, textAlign: 'center' }}>{title}</Text>
      {body ? (
        <Text style={{ ...type.body, color: colors.muted, textAlign: 'center', marginTop: space.s8 }}>
          {body}
        </Text>
      ) : null}
      {action ? <View style={{ marginTop: space.s20, alignSelf: 'stretch' }}>{action}</View> : null}
    </View>
  );
}

/** Full-screen / section loading shell (H-12). */
export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  const { colors } = useTheme();
  return (
    <View
      style={{
        flex: 1,
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: space.s28 * 2,
        gap: space.s12,
      }}
      accessibilityRole="progressbar"
      accessibilityLabel={label}
    >
      <ActivityIndicator color={colors.ink} />
      <Text style={{ ...type.body, color: colors.muted }}>{label}</Text>
    </View>
  );
}

/** Quantity stepper (M04/M05) — 44pt targets. */
export function QtyStepper({
  qty,
  onChange,
  max,
}: {
  qty: number;
  onChange: (delta: number) => void;
  max?: number;
}) {
  const { colors } = useTheme();
  const buttonStyle: ViewStyle = {
    width: metrics.minTouchTarget,
    height: metrics.minTouchTarget,
    alignItems: 'center',
    justifyContent: 'center',
  };
  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: radius.chip,
        alignSelf: 'flex-start',
      }}
    >
      <Pressable accessibilityRole="button" accessibilityLabel="Decrease quantity" style={buttonStyle} onPress={() => onChange(-1)}>
        <Text style={{ fontSize: 18, color: colors.ink, fontFamily: fonts.body }}>−</Text>
      </Pressable>
      <Mono size={14} weight="semibold" style={{ minWidth: 28, textAlign: 'center' }}>
        {qty}
      </Mono>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Increase quantity"
        style={buttonStyle}
        onPress={() => onChange(1)}
        disabled={max !== undefined && qty >= max}
      >
        <Text style={{ fontSize: 18, color: max !== undefined && qty >= max ? colors.muted : colors.ink, fontFamily: fonts.body }}>
          +
        </Text>
      </Pressable>
    </View>
  );
}

/** Barcode strip motif (M01/M07): alternating bars, decorative only. */
export function BarcodeStrip({ bars = 44, color, height = 36 }: { bars?: number; color?: string; height?: number }) {
  const { onInk } = useTheme();
  const barColor = color ?? onInk.onInkSurface;
  return (
    <View accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={{ flexDirection: 'row', height, alignItems: 'stretch' }}>
      {Array.from({ length: bars }, (_, index) => (
        <View
          key={index}
          style={{
            width: index % 3 === 0 ? 3 : index % 2 === 0 ? 2 : 1,
            marginRight: index % 4 === 0 ? 4 : 2,
            backgroundColor: barColor,
            opacity: index % 5 === 0 ? 1 : 0.85,
          }}
        />
      ))}
    </View>
  );
}

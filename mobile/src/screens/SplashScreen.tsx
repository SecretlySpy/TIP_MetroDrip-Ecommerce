/**
 * M01 · Splash & Onboarding — Figma node 63:3.
 *
 * Full-bleed ink. Centered: Anton 44 lockup ("Metro" paper / "Drip" volt),
 * volt mono tagline (tracking 2), barcode strip, two-line muted copy. Bottom:
 * volt "Create account", outlined "Sign in", plain "Continue as guest".
 */

import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import React, { useEffect } from 'react';
import { Pressable, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Mono, PillButton } from '@/components/primitives';
import type { RootStackParamList } from '@/navigation';
import { useAuth } from '@/store/AuthContext';
import { useTheme } from '@/theme/ThemeProvider';
import { radius, space } from '@/theme/theme';
import { fonts } from '@/theme/typography';

/** Exact bar rhythm from the design (node 63:15): [width, isBright] pairs. */
const BARS: Array<[number, boolean]> = [
  [4, true], [2, false], [2, false], [2, true], [2, false], [4, false], [2, true],
  [2, false], [2, false], [2, true], [4, false], [2, false], [2, true], [2, false],
  [2, false], [4, true], [2, false], [2, false], [2, true], [2, false], [4, false],
  [2, true], [2, false], [2, false], [2, true], [4, false], [2, false], [2, true],
  [2, false], [2, false], [4, true], [2, false], [2, false], [2, true], [2, false],
  [4, false], [2, true], [2, false], [2, false], [2, true], [4, false], [2, false],
  [2, true], [2, false],
];

export default function SplashScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { colors, onInk } = useTheme();
  const { customer, restoring, locked, unlockWithBiometrics } = useAuth();

  useEffect(() => {
    // Signed-in sessions skip onboarding entirely once restored.
    if (!restoring && customer) {
      navigation.reset({ index: 0, routes: [{ name: 'Tabs' }] });
    }
  }, [restoring, customer, navigation]);

  useEffect(() => {
    if (!restoring && locked) {
      // FR-23: stored session behind the biometric gate.
      unlockWithBiometrics().catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restoring, locked]);

  const enterAsGuest = () => navigation.reset({ index: 0, routes: [{ name: 'Tabs' }] });

  return (
    <View style={{ flex: 1, backgroundColor: onInk.inkSurface }}>
      <SafeAreaView style={{ flex: 1 }}>
        <View
          style={{
            flex: 1,
            alignItems: 'center',
            justifyContent: 'center',
            paddingHorizontal: space.s28,
            gap: space.s18,
          }}
        >
          <View style={{ flexDirection: 'row' }}>
            <Text style={{ fontFamily: fonts.display, fontSize: 44, color: onInk.onInkSurface }}>
              Metro
            </Text>
            <Text style={{ fontFamily: fonts.display, fontSize: 44, color: colors.volt }}>
              Drip
            </Text>
          </View>

          <Mono
            size={11}
            weight="semibold"
            color={colors.volt}
            style={{ letterSpacing: 2, textAlign: 'center', width: 320 }}
          >
            METRO MANILA STREETWEAR
          </Mono>

          {/* Barcode strip motif — exact bar rhythm from the frame. */}
          <View
            accessibilityElementsHidden
            importantForAccessibility="no-hide-descendants"
            style={{ flexDirection: 'row', height: 34, justifyContent: 'center' }}
          >
            {BARS.map(([width, bright], index) => (
              <View
                key={index}
                style={{
                  width,
                  height: 34,
                  backgroundColor: bright ? onInk.onInkSurface : colors.muted,
                }}
              />
            ))}
          </View>

          <Text
            style={{
              fontFamily: fonts.body,
              fontSize: 15,
              lineHeight: 24,
              color: colors.mutedOnDark,
              textAlign: 'center',
              width: 300,
            }}
          >
            Shop the drop from your phone.{'\n'}Track every order to your door.
          </Text>
        </View>

        <View style={{ paddingHorizontal: space.s24, paddingBottom: 44, gap: space.s12 }}>
          {locked ? (
            <PillButton
              label="Unlock"
              variant="volt"
              style={{ height: 54, borderRadius: radius.pill }}
              textStyle={{ fontFamily: fonts.bodyBold, fontSize: 16 }}
              onPress={() => unlockWithBiometrics().catch(() => undefined)}
            />
          ) : null}
          <PillButton
            label="Create account"
            variant="volt"
            style={{ height: 54, borderRadius: radius.pill }}
            textStyle={{ fontFamily: fonts.bodyBold, fontSize: 16 }}
            onPress={() => navigation.navigate('Auth', { mode: 'register' })}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Sign in"
            onPress={() => navigation.navigate('Auth', { mode: 'signin' })}
            style={{
              height: 54,
              borderRadius: radius.pill,
              borderWidth: 1,
              borderColor: colors.muted,
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Text style={{ fontFamily: fonts.bodyBold, fontSize: 16, color: onInk.onInkSurface }}>
              Sign in
            </Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Continue as guest"
            onPress={enterAsGuest}
            style={{ minHeight: 44, alignItems: 'center', justifyContent: 'center' }}
          >
            <Text
              style={{
                fontFamily: fonts.bodyMedium,
                fontSize: 14,
                color: colors.mutedOnDark,
                textAlign: 'center',
              }}
            >
              Continue as guest
            </Text>
          </Pressable>
        </View>
      </SafeAreaView>
    </View>
  );
}

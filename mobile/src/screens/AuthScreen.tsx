/**
 * M10 · Sign In / Register — Figma node 67:2.
 *
 * Anton 34 "Welcome" → segmented Sign in / Register control (surface track,
 * paper active segment) → labelled fields (password with 👁 toggle) →
 * accent-text "Forgot password?" → volt primary → outlined "Sign in with
 * Face ID" (hidden when unenrolled, §4) → "or" divider → surface guest
 * button → guest-order-claim note.
 */

import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import React, { useState } from 'react';
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '@/api/client';
import { auth as authApi } from '@/api/endpoints';
import { Mono, NavBar, PillButton } from '@/components/primitives';
import type { RootStackParamList } from '@/navigation';
import { useAuth } from '@/store/AuthContext';
import { useTheme } from '@/theme/ThemeProvider';
import { radius, space } from '@/theme/theme';
import { fonts } from '@/theme/typography';

function LabelledInput({
  label,
  value,
  onChange,
  secure,
  keyboardType,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  secure?: boolean;
  keyboardType?: 'default' | 'email-address';
}) {
  const { colors } = useTheme();
  const [hidden, setHidden] = useState(!!secure);
  return (
    <View
      style={{
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: radius.input,
        paddingHorizontal: space.s14,
        paddingVertical: 11,
        gap: 3,
        width: '100%',
      }}
    >
      <Mono size={9} color={colors.muted} style={{ letterSpacing: 0.8 }}>
        {label}
      </Mono>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <TextInput
          value={value}
          onChangeText={onChange}
          secureTextEntry={hidden}
          keyboardType={keyboardType}
          autoCapitalize={keyboardType === 'email-address' ? 'none' : label === 'FULL NAME' ? 'words' : 'none'}
          accessibilityLabel={label}
          style={{ flex: 1, fontFamily: fonts.body, fontSize: 14, color: colors.ink, padding: 0 }}
        />
        {secure ? (
          <Pressable onPress={() => setHidden(!hidden)} hitSlop={12} accessibilityRole="button" accessibilityLabel={hidden ? 'Show password' : 'Hide password'}>
            <Text style={{ fontSize: 14, color: colors.muted }}>👁</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

export default function AuthScreen() {
  const { colors } = useTheme();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'Auth'>>();
  const auth = useAuth();

  const [mode, setMode] = useState<'signin' | 'register'>(route.params?.mode ?? 'signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const finish = () => navigation.reset({ index: 0, routes: [{ name: 'Tabs' }] });

  const submit = async () => {
    setBusy(true);
    setError('');
    try {
      if (mode === 'signin') {
        await auth.signIn(email.trim(), password);
      } else {
        await auth.register({ email: email.trim(), password, name: name.trim(), phone: phone.trim() });
      }
      finish();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Network error — please try again.');
      setBusy(false);
    }
  };

  const forgot = () => {
    if (!email.trim()) {
      Alert.alert('Forgot password', 'Enter your email above first, then tap again.');
      return;
    }
    authApi.requestPasswordReset(email.trim()).catch(() => undefined);
    Alert.alert('Check your email', 'If that address has an account, a reset link is on its way.');
  };

  const faceId = async () => {
    const unlocked = await auth.unlockWithBiometrics();
    if (unlocked) finish();
  };

  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: colors.paper }}>
      <NavBar title="" onBack={() => navigation.goBack()} />

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          contentContainerStyle={{ paddingHorizontal: space.s24, paddingTop: space.s10, gap: space.screenX }}
          keyboardShouldPersistTaps="handled"
        >
          <Text style={{ fontFamily: fonts.display, fontSize: 34, color: colors.ink }}>Welcome</Text>
          <Text style={{ fontFamily: fonts.body, fontSize: 14, color: colors.muted }}>
            Sign in to track orders, save your fits, and check out faster.
          </Text>

          {/* Segmented control. */}
          <View
            style={{
              height: 46,
              flexDirection: 'row',
              backgroundColor: colors.surface,
              borderRadius: radius.card,
              padding: 4,
            }}
          >
            {(['signin', 'register'] as const).map((candidate) => (
              <Pressable
                key={candidate}
                onPress={() => setMode(candidate)}
                accessibilityRole="tab"
                accessibilityState={{ selected: mode === candidate }}
                accessibilityLabel={candidate === 'signin' ? 'Sign in' : 'Register'}
                style={{
                  flex: 1,
                  borderRadius: 9,
                  backgroundColor: mode === candidate ? colors.paper : 'transparent',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Text
                  style={{
                    fontFamily: fonts.bodySemiBold,
                    fontSize: 14,
                    color: mode === candidate ? colors.ink : colors.muted,
                  }}
                >
                  {candidate === 'signin' ? 'Sign in' : 'Register'}
                </Text>
              </Pressable>
            ))}
          </View>

          {mode === 'register' ? (
            <>
              <LabelledInput label="FULL NAME" value={name} onChange={setName} />
              <LabelledInput label="MOBILE (OPTIONAL)" value={phone} onChange={setPhone} />
            </>
          ) : null}
          <LabelledInput label="EMAIL" value={email} onChange={setEmail} keyboardType="email-address" />
          <LabelledInput label="PASSWORD" value={password} onChange={setPassword} secure />

          {mode === 'signin' ? (
            <Pressable onPress={forgot} style={{ alignSelf: 'flex-end' }} accessibilityRole="button" accessibilityLabel="Forgot password">
              <Text style={{ fontFamily: fonts.bodyMedium, fontSize: 13, color: colors.accentText }}>
                Forgot password?
              </Text>
            </Pressable>
          ) : null}

          {error ? (
            <Mono size={11} weight="medium" color={colors.danger}>
              {error}
            </Mono>
          ) : null}

          <PillButton
            label={mode === 'signin' ? 'Sign in' : 'Create account'}
            variant="volt"
            loading={busy}
            style={{ height: 54 }}
            textStyle={{ fontFamily: fonts.bodyBold, fontSize: 16 }}
            onPress={submit}
          />

          {/* Biometric unlock — only when a SecureStore session still exists (H-11). */}
          {mode === 'signin' &&
          auth.biometricsEnrolled &&
          auth.biometricPref &&
          (auth.locked || auth.hasSession) ? (
            <Pressable
              onPress={faceId}
              accessibilityRole="button"
              accessibilityLabel={`Sign in with ${auth.biometricLabel}`}
              style={{
                height: 52,
                borderRadius: radius.pill,
                borderWidth: 1,
                borderColor: colors.ink,
                flexDirection: 'row',
                gap: space.s10,
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Text style={{ fontSize: 18, color: colors.ink }}>☉</Text>
              <Text style={{ fontFamily: fonts.bodyBold, fontSize: 15, color: colors.ink }}>
                Sign in with {auth.biometricLabel}
              </Text>
            </Pressable>
          ) : null}

          <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.s12 }}>
            <View style={{ flex: 1, height: 1, backgroundColor: colors.border }} />
            <Text style={{ fontFamily: fonts.body, fontSize: 12, color: colors.muted }}>or</Text>
            <View style={{ flex: 1, height: 1, backgroundColor: colors.border }} />
          </View>

          <PillButton
            label="Continue as guest"
            variant="surface"
            style={{ height: 52 }}
            textStyle={{ fontFamily: fonts.bodySemiBold, fontSize: 15 }}
            onPress={finish}
          />

          <Text style={{ fontFamily: fonts.body, fontSize: 12, color: colors.muted }}>
            Bought as a guest before? Register with the same email and your past orders come with
            you.
          </Text>
          <View style={{ height: space.s24 }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

/**
 * Session state (FR-22/FR-23): JWT pair in the secure enclave, profile in
 * memory, optional biometric unlock gate on cold start.
 */

import * as LocalAuthentication from 'expo-local-authentication';
import AsyncStorage from '@react-native-async-storage/async-storage';
import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

import { clearTokens, getRefreshToken, hasStoredSession, saveTokens } from '@/api/client';
import { account, auth } from '@/api/endpoints';
import type { Customer } from '@/api/types';

const BIOMETRIC_PREF_KEY = 'metrodrip.biometricUnlock';

interface AuthContextValue {
  customer: Customer | null;
  /** true while the stored session (if any) is being restored on cold start */
  restoring: boolean;
  /** true when a stored session exists but biometric unlock hasn't passed yet */
  locked: boolean;
  /** refresh token still in SecureStore — required before offering biometric unlock */
  hasSession: boolean;
  biometricsEnrolled: boolean;
  biometricPref: boolean;
  /** OS-aware label: Face ID / Touch ID / Biometrics */
  biometricLabel: string;
  signIn: (email: string, password: string) => Promise<void>;
  register: (body: { email: string; password: string; name: string; phone?: string }) => Promise<void>;
  signOut: () => Promise<void>;
  unlockWithBiometrics: () => Promise<boolean>;
  setBiometricPref: (enabled: boolean) => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [restoring, setRestoring] = useState(true);
  const [locked, setLocked] = useState(false);
  const [hasSession, setHasSession] = useState(false);
  const [biometricsEnrolled, setBiometricsEnrolled] = useState(false);
  const [biometricPref, setBiometricPrefState] = useState(false);
  const [biometricLabel, setBiometricLabel] = useState('Biometrics');

  useEffect(() => {
    (async () => {
      const [hasHardware, enrolled, types] = await Promise.all([
        LocalAuthentication.hasHardwareAsync(),
        LocalAuthentication.isEnrolledAsync(),
        LocalAuthentication.supportedAuthenticationTypesAsync(),
      ]);
      setBiometricsEnrolled(hasHardware && enrolled);
      if (types.includes(LocalAuthentication.AuthenticationType.FACIAL_RECOGNITION)) {
        setBiometricLabel('Face ID');
      } else if (types.includes(LocalAuthentication.AuthenticationType.FINGERPRINT)) {
        setBiometricLabel('Touch ID');
      } else {
        setBiometricLabel('Biometrics');
      }

      const pref = (await AsyncStorage.getItem(BIOMETRIC_PREF_KEY)) === '1';
      setBiometricPrefState(pref);

      const session = await hasStoredSession();
      setHasSession(session);
      if (session) {
        if (pref && hasHardware && enrolled) {
          // FR-23: opt-in biometric gate before the session becomes usable.
          setLocked(true);
        } else {
          await restoreProfile();
        }
      }
      setRestoring(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function restoreProfile() {
    try {
      setCustomer(await account.profile());
    } catch {
      // Token pair unusable and unrefreshable — fall back to signed out.
      await clearTokens();
      setCustomer(null);
    }
  }

  const value = useMemo<AuthContextValue>(
    () => ({
      customer,
      restoring,
      locked,
      hasSession,
      biometricsEnrolled,
      biometricPref,
      biometricLabel,
      async signIn(email, password) {
        const payload = await auth.login({ email, password });
        await saveTokens(payload.access, payload.refresh);
        setHasSession(true);
        setCustomer(payload.customer);
        setLocked(false);
      },
      async register(body) {
        const payload = await auth.register(body);
        await saveTokens(payload.access, payload.refresh);
        setHasSession(true);
        setCustomer(payload.customer);
        setLocked(false);
      },
      async signOut() {
        const refresh = await getRefreshToken();
        if (refresh) {
          try {
            await auth.logout(refresh);
          } catch {
            // Server-side revocation is best-effort; local clearing is the gate.
          }
        }
        await clearTokens();
        setHasSession(false);
        setCustomer(null);
        setLocked(false);
      },
      async unlockWithBiometrics() {
        const result = await LocalAuthentication.authenticateAsync({
          promptMessage: 'Unlock MetroDrip',
          fallbackLabel: 'Use password',
          disableDeviceFallback: false,
        });
        if (result.success) {
          setLocked(false);
          await restoreProfile();
        }
        return result.success;
      },
      async setBiometricPref(enabled) {
        setBiometricPrefState(enabled);
        await AsyncStorage.setItem(BIOMETRIC_PREF_KEY, enabled ? '1' : '0');
      },
      async refreshProfile() {
        await restoreProfile();
      },
    }),
    [customer, restoring, locked, hasSession, biometricsEnrolled, biometricPref, biometricLabel],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}

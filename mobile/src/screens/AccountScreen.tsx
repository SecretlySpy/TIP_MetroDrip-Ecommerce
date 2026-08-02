/**
 * M09 · Account (Tab) — Figma node 65:155.
 *
 * Volt 56pt avatar with onVolt initials, name, mono member line → three
 * surface stat cards (Anton 22 values) → menu rows (glyph, SemiBold 15 label,
 * mono meta, › chevron, hairline separators) → centered danger "Sign out".
 * The ⚙ opens appearance (FR-31 manual override) + biometric opt-in (FR-23).
 */

import { useIsFocused, useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import React, { useEffect, useState } from 'react';
import { Alert, Linking, Pressable, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { API_BASE_URL } from '@/api/client';
import { account, notifications, orders } from '@/api/endpoints';
import type { OrderPayload } from '@/api/types';
import { EmptyState, Mono, NavBar, PillButton } from '@/components/primitives';
import type { RootStackParamList } from '@/navigation';
import { useAuth } from '@/store/AuthContext';
import { useTheme } from '@/theme/ThemeProvider';
import { radius, space } from '@/theme/theme';
import { fonts } from '@/theme/typography';

const WEB_BASE = API_BASE_URL.replace('/api/mobile/v1', '');

export default function AccountScreen() {
  const { colors } = useTheme();
  const theme = useTheme();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const auth = useAuth();
  const focused = useIsFocused();

  const [recentOrders, setRecentOrders] = useState<OrderPayload[]>([]);
  const [wishlistCount, setWishlistCount] = useState(0);
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    if (!focused || !auth.customer) return;
    orders.history().then((page) => setRecentOrders(page.results)).catch(() => undefined);
    account.wishlist().then((page) => setWishlistCount(page.results.length)).catch(() => undefined);
    notifications.list().then((page) => setUnread(page.unread_count)).catch(() => undefined);
  }, [focused, auth.customer]);

  const openSettings = () => {
    Alert.alert('Settings', undefined, [
      {
        text: `Appearance: ${auth ? theme.preference : 'system'} →`,
        onPress: () =>
          Alert.alert('Appearance', 'FR-31: follows the system with a manual override.', [
            { text: 'System', onPress: () => theme.setPreference('system') },
            { text: 'Light', onPress: () => theme.setPreference('light') },
            { text: 'Dark', onPress: () => theme.setPreference('dark') },
          ]),
      },
      ...(auth.biometricsEnrolled
        ? [
            {
              text: `Biometric unlock: ${auth.biometricPref ? 'on' : 'off'}`,
              onPress: () => auth.setBiometricPref(!auth.biometricPref),
            },
          ]
        : []),
      { text: 'Close', style: 'cancel' as const },
    ]);
  };

  if (!auth.customer) {
    return (
      <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: colors.paper }}>
        <NavBar
          title="Account"
          right={
            <Pressable onPress={openSettings} hitSlop={12} accessibilityRole="button" accessibilityLabel="Settings">
              <Text style={{ fontSize: 18, color: colors.ink }}>⚙</Text>
            </Pressable>
          }
        />
        <EmptyState
          title="You're browsing as a guest"
          body="Sign in for order history, wishlist, and faster checkout."
          action={
            <View style={{ gap: space.s10 }}>
              <PillButton label="Sign in" variant="volt" onPress={() => navigation.navigate('Auth', { mode: 'signin' })} />
              <PillButton label="Create account" variant="outline" onPress={() => navigation.navigate('Auth', { mode: 'register' })} />
            </View>
          }
        />
      </SafeAreaView>
    );
  }

  const customer = auth.customer;
  const initials = customer.name
    .split(/\s+/)
    .map((part) => part.charAt(0))
    .join('')
    .slice(0, 2)
    .toUpperCase();
  const activeCount = recentOrders.filter((order) =>
    ['pending', 'paid', 'packed', 'shipped'].includes(order.status),
  ).length;

  const openOrders = () => {
    if (recentOrders.length === 0) {
      Alert.alert('My Orders', 'No orders yet — your next drop starts in the shop.');
      return;
    }
    Alert.alert(
      'My Orders',
      undefined,
      [
        ...recentOrders.slice(0, 6).map((order) => ({
          text: `${order.order_no} · ${order.status_display} · ${order.total_display}`,
          onPress: () => navigation.navigate('OrderTracking', { token: order.status_token }),
        })),
        { text: 'Close', style: 'cancel' as const },
      ],
    );
  };

  const signOut = () =>
    Alert.alert('Sign out', 'Sign out of MetroDrip on this device?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Sign out',
        style: 'destructive',
        onPress: async () => {
          await auth.signOut();
          navigation.reset({ index: 0, routes: [{ name: 'Splash' }] });
        },
      },
    ]);

  const rows: Array<{ glyph: string; label: string; meta?: string; onPress: () => void }> = [
    { glyph: '▤', label: 'My Orders', meta: `${activeCount} active`, onPress: openOrders },
    {
      glyph: '♡',
      label: 'Wishlist',
      meta: `${wishlistCount} item${wishlistCount === 1 ? '' : 's'}`,
      onPress: () => navigation.navigate('Tabs' as never, { screen: 'Saved' } as never),
    },
    {
      glyph: '◈',
      label: 'Addresses',
      meta: `${customer.addresses.length} saved`,
      onPress: () =>
        Alert.alert('Addresses', 'Saved addresses are managed on the web account page for now.'),
    },
    {
      glyph: '★',
      label: 'My Reviews',
      onPress: () => Alert.alert('My Reviews', 'Review items from a delivered order on its tracking page.'),
    },
    {
      glyph: '◔',
      label: 'Notifications',
      meta: unread > 0 ? `${unread} new` : undefined,
      onPress: () => navigation.navigate('Tabs' as never, { screen: 'Orders' } as never),
    },
    { glyph: '?', label: 'Help & FAQ', onPress: () => Linking.openURL(`${WEB_BASE}/pages/faq/`) },
    { glyph: '✉', label: 'Contact us', onPress: () => Linking.openURL(`${WEB_BASE}/contact/`) },
  ];

  const memberSince = new Date().getFullYear(); // joined date not exposed; see report

  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: colors.paper }}>
      <NavBar
        title="Account"
        right={
          <Pressable onPress={openSettings} hitSlop={12} accessibilityRole="button" accessibilityLabel="Settings">
            <Text style={{ fontSize: 18, color: colors.ink }}>⚙</Text>
          </Pressable>
        }
      />

      <ScrollView>
        <View style={{ paddingHorizontal: space.screenX, paddingVertical: space.s18, gap: space.s12 }}>
          {/* Identity row. */}
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.s14 }}>
            <View
              style={{
                width: 56,
                height: 56,
                borderRadius: radius.pill,
                backgroundColor: colors.volt,
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Text style={{ fontFamily: fonts.bodyBold, fontSize: 18, color: colors.onVolt }}>
                {initials}
              </Text>
            </View>
            <View style={{ flex: 1, gap: 3 }}>
              <Text style={{ fontFamily: fonts.bodyBold, fontSize: 18, color: colors.ink }}>
                {customer.name}
              </Text>
              <Mono size={10} color={colors.muted}>
                {`MEMBER SINCE ${String(memberSince)} · ${recentOrders.length} ORDER${recentOrders.length === 1 ? '' : 'S'}`}
              </Mono>
            </View>
          </View>

          {/* Stat cards. */}
          <View style={{ flexDirection: 'row', gap: space.s10 }}>
            {[
              { value: recentOrders.length, label: 'Orders' },
              { value: wishlistCount, label: 'Wishlist' },
              { value: unread, label: 'Unread' },
            ].map((stat) => (
              <View
                key={stat.label}
                style={{
                  flex: 1,
                  backgroundColor: colors.surface,
                  borderRadius: radius.card,
                  paddingVertical: space.s14,
                  alignItems: 'center',
                  gap: 3,
                }}
              >
                <Text style={{ fontFamily: fonts.display, fontSize: 22, color: colors.ink }}>
                  {stat.value}
                </Text>
                <Mono size={10} color={colors.muted}>{stat.label}</Mono>
              </View>
            ))}
          </View>
        </View>

        {/* Menu rows. */}
        <View style={{ paddingHorizontal: space.screenX, paddingTop: space.s6 }}>
          {rows.map((row) => (
            <Pressable
              key={row.label}
              onPress={row.onPress}
              accessibilityRole="button"
              accessibilityLabel={row.meta ? `${row.label}, ${row.meta}` : row.label}
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                gap: space.s14,
                paddingVertical: 15,
                borderBottomWidth: 1,
                borderBottomColor: colors.border,
                minHeight: 44,
              }}
            >
              <Text style={{ fontSize: 17, color: colors.ink }}>{row.glyph}</Text>
              <Text style={{ flex: 1, fontFamily: fonts.bodySemiBold, fontSize: 15, color: colors.ink }}>
                {row.label}
              </Text>
              {row.meta ? <Mono size={11} color={colors.muted}>{row.meta}</Mono> : null}
              <Text style={{ fontSize: 18, color: colors.muted }}>›</Text>
            </Pressable>
          ))}

          <Pressable
            onPress={signOut}
            accessibilityRole="button"
            accessibilityLabel="Sign out"
            style={{ paddingVertical: space.screenX, alignItems: 'center', minHeight: 44 }}
          >
            <Text style={{ fontFamily: fonts.bodySemiBold, fontSize: 15, color: colors.danger }}>
              Sign out
            </Text>
          </Pressable>
        </View>
        <View style={{ height: space.s10 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

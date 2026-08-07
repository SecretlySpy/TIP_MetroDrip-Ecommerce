/**
 * M08 · Notifications (Orders tab) — Figma node 65:83.
 *
 * TODAY / EARLIER mono section labels; unread rows = surface fill with a volt
 * circular icon badge; read rows = outlined with a surface icon circle. Rows
 * mirror delivered push messages (FR-28); tapping an order row opens tracking
 * and marks it read.
 */

import { useIsFocused, useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import React, { useEffect, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { notifications, orders } from '@/api/endpoints';
import type { AppNotification } from '@/api/types';
import { EmptyState, Mono, NavBar, PillButton } from '@/components/primitives';
import type { RootStackParamList } from '@/navigation';
import { useAuth } from '@/store/AuthContext';
import { useTheme } from '@/theme/ThemeProvider';
import { radius, space } from '@/theme/theme';
import { fonts } from '@/theme/typography';

const CATEGORY_GLYPHS: Record<AppNotification['category'], string> = {
  order: '🚚',
  drop: '🔥',
  stock: '♡',
  review: '★',
};

function timeAgo(iso: string): string {
  const minutes = Math.max(1, Math.floor((Date.now() - new Date(iso).getTime()) / 60_000));
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

const startOfToday = () => new Date(new Date().setHours(0, 0, 0, 0)).getTime();

export default function NotificationsScreen() {
  const { colors } = useTheme();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { customer } = useAuth();
  const focused = useIsFocused();

  const [items, setItems] = useState<AppNotification[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = () =>
    notifications
      .list()
      .then((page) => setItems(page.results))
      .catch(() => undefined);

  useEffect(() => {
    if (focused && customer) load();
  }, [focused, customer]);

  const open = async (item: AppNotification) => {
    if (!item.is_read) {
      notifications.markRead(item.id).catch(() => undefined);
      setItems((current) =>
        current.map((candidate) =>
          candidate.id === item.id ? { ...candidate, is_read: true } : candidate,
        ),
      );
    }
    if (item.order_no) {
      const order = await orders.detail(item.order_no).catch(() => null);
      if (order) navigation.navigate('OrderTracking', { token: order.status_token });
    }
  };

  if (!customer) {
    return (
      <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: colors.paper }}>
        <NavBar title="Notifications" />
        <EmptyState
          title="Sign in for updates"
          body="Order updates, drops, and restock alerts land here."
          action={
            <PillButton
              label="Sign in"
              variant="volt"
              onPress={() => navigation.navigate('Auth', { mode: 'signin' })}
            />
          }
        />
      </SafeAreaView>
    );
  }

  const today = items.filter((item) => new Date(item.created_at).getTime() >= startOfToday());
  const earlier = items.filter((item) => new Date(item.created_at).getTime() < startOfToday());

  const Row = ({ item }: { item: AppNotification }) => (
    <Pressable
      onPress={() => open(item)}
      accessibilityRole="button"
      accessibilityLabel={`${item.title}${item.is_read ? '' : ', unread'}`}
      style={{
        flexDirection: 'row',
        gap: space.s12,
        paddingHorizontal: space.s14,
        paddingVertical: 13,
        borderRadius: radius.card,
        backgroundColor: item.is_read ? colors.paper : colors.surface,
        borderWidth: item.is_read ? 1 : 0,
        borderColor: colors.border,
      }}
    >
      <View
        style={{
          width: 38,
          height: 38,
          borderRadius: radius.pill,
          backgroundColor: item.is_read ? colors.surface : colors.volt,
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Text style={{ fontSize: item.is_read ? 15 : 16, color: item.is_read ? colors.ink : colors.onVolt }}>
          {CATEGORY_GLYPHS[item.category]}
        </Text>
      </View>
      <View style={{ flex: 1, gap: 3 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text style={{ fontFamily: fonts.bodySemiBold, fontSize: 14, color: colors.ink }}>
            {item.title}
          </Text>
          <Mono size={10} color={colors.muted}>{timeAgo(item.created_at)}</Mono>
        </View>
        <Text style={{ fontFamily: fonts.body, fontSize: 12, color: colors.muted }}>
          {item.body}
        </Text>
      </View>
    </Pressable>
  );

  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: colors.paper }}>
      <NavBar
        title="Notifications"
        right={
          items.some((item) => !item.is_read) ? (
            <Pressable
              hitSlop={12}
              accessibilityRole="button"
              accessibilityLabel="Mark all read"
              onPress={() => {
                notifications.markAllRead().catch(() => undefined);
                setItems((current) => current.map((item) => ({ ...item, is_read: true })));
              }}
            >
              <Text style={{ fontSize: 18, color: colors.ink }}>⚙</Text>
            </Pressable>
          ) : (
            <Text style={{ fontSize: 18, color: colors.ink }}>⚙</Text>
          )
        }
      />

      <ScrollView
        contentContainerStyle={{ paddingHorizontal: space.screenX, paddingVertical: space.s14, gap: space.s10 }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={async () => {
              setRefreshing(true);
              await load();
              setRefreshing(false);
            }}
          />
        }
      >
        {items.length === 0 ? (
          <EmptyState title="Nothing yet" body="Order updates and drops will land here." />
        ) : (
          <>
            {today.length > 0 ? (
              <Mono size={9} weight="semibold" color={colors.muted} style={{ letterSpacing: 1.2 }}>
                TODAY
              </Mono>
            ) : null}
            {today.map((item) => (
              <Row key={item.id} item={item} />
            ))}
            {earlier.length > 0 ? (
              <Mono size={9} weight="semibold" color={colors.muted} style={{ letterSpacing: 1.2 }}>
                EARLIER
              </Mono>
            ) : null}
            {earlier.map((item) => (
              <Row key={item.id} item={item} />
            ))}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

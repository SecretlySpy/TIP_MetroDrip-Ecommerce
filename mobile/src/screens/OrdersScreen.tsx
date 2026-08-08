/* eslint-disable @typescript-eslint/no-unused-vars */
/* eslint-disable react-hooks/exhaustive-deps */
import { useIsFocused, useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import React, { useEffect, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { OfflineError } from '@/api/client';
import { orders } from '@/api/endpoints';
import type { OrderPayload } from '@/api/types';
import { EmptyState, Mono, NavBar, PillButton } from '@/components/primitives';
import type { RootStackParamList } from '@/navigation';
import { useAuth } from '@/store/AuthContext';
import { useTheme } from '@/theme/ThemeProvider';
import { radius, space } from '@/theme/theme';
import { fonts } from '@/theme/typography';

function timeAgo(iso: string): string {
  const minutes = Math.max(1, Math.floor((Date.now() - new Date(iso).getTime()) / 60_000));
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function OrdersScreen() {
  const { colors } = useTheme();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { customer } = useAuth();
  const focused = useIsFocused();

  const [items, setItems] = useState<OrderPayload[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<'offline' | 'failed' | null>(null);

  const load = () =>
    orders
      .history()
      .then((page) => {
        setItems(page.results);
        setLoadError(null);
      })
      .catch((err: unknown) => {
        setLoadError(err instanceof OfflineError ? 'offline' : 'failed');
      });

  useEffect(() => {
    if (focused && customer) load();
  }, [focused, customer]);

  if (!customer) {
    return (
      <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: colors.paper }}>
        <NavBar title="Orders" />
        <EmptyState
          title="Sign in for orders"
          body="Track your active orders and view history."
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

  const Row = ({ item }: { item: OrderPayload }) => (
    <Pressable
      onPress={() => navigation.navigate('OrderTracking', { token: item.status_token })}
      accessibilityRole="button"
      accessibilityLabel={`Order ${item.order_no}, ${item.status_display}`}
      style={{
        flexDirection: 'row',
        gap: space.s12,
        paddingHorizontal: space.s14,
        paddingVertical: 13,
        borderRadius: radius.card,
        backgroundColor: colors.surface,
        borderWidth: 0,
        borderColor: colors.border,
      }}
    >
      <View style={{ flex: 1, gap: 3 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text style={{ fontFamily: fonts.bodySemiBold, fontSize: 14, color: colors.ink }}>
            {item.order_no}
          </Text>
          <Mono size={10} color={colors.muted}>{timeAgo(item.created_at)}</Mono>
        </View>
        <Text style={{ fontFamily: fonts.body, fontSize: 12, color: colors.muted }}>
          {item.status_display} · {item.total_display}
        </Text>
      </View>
    </Pressable>
  );

  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: colors.paper }}>
      <NavBar title="Orders" />
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
          loadError ? (
            <EmptyState
              title={loadError === 'offline' ? "You're offline" : "Couldn't load orders"}
              body={
                loadError === 'offline'
                  ? 'Reconnect and pull to refresh.'
                  : 'Something went wrong — pull to try again.'
              }
              action={<PillButton label="Retry" variant="volt" onPress={load} />}
            />
          ) : (
            <EmptyState title="No orders yet" body="Your next drop starts in the shop." />
          )
        ) : (
          items.map((item) => <Row key={item.order_no} item={item} />)
        )}
      </ScrollView>
    </SafeAreaView>
  );
}


/**
 * M07 · Order Tracking — Figma node 65:2.
 *
 * Ink header (volt mono eyebrow, Anton 28 line, courier + elevated waybill
 * chip) → six-step timeline (16pt volt dots + volt rail when complete; 14pt
 * outlined dots + border rail when pending) → items → sticky outlined
 * "Get help" + volt "Track live".
 *
 * FR-26: every step state mirrors the server-side machine; the sixth step
 * (Out for delivery) reflects shipment status — nothing is inferred locally.
 */

import { useNavigation, useRoute } from '@react-navigation/native';
import type { RouteProp } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import React, { useCallback, useEffect, useState } from 'react';
import { Linking, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { API_BASE_URL, OfflineError } from '@/api/client';
import { orders } from '@/api/endpoints';
import type { OrderPayload } from '@/api/types';
import {
  EmptyState,
  LoadingState,
  Mono,
  NavBar,
  OfflineBanner,
  PillButton,
  StickyBar,
} from '@/components/primitives';
import type { RootStackParamList } from '@/navigation';
import { useTheme } from '@/theme/ThemeProvider';
import { radius, space } from '@/theme/theme';
import { fonts } from '@/theme/typography';

const FIT_SHORT: Record<string, string> = { slim: 'SLM', regular: 'REG', oversized: 'OVS' };

interface DisplayStep {
  title: string;
  detail: string;
  state: 'done' | 'todo';
  last?: boolean;
}

/** Fold the server order timeline + shipment status into the six drawn steps. */
function buildSteps(order: OrderPayload): DisplayStep[] {
  const orderState = (key: string) =>
    order.timeline?.find((step) => step.key === key)?.state ?? 'todo';
  const done = (key: string) => orderState(key) === 'done' || orderState(key) === 'current';
  const outForDelivery =
    order.shipment?.status === 'out_for_delivery' || order.shipment?.status === 'delivered';

  const placed = new Date(order.created_at);
  const stamp = placed.toLocaleDateString('en-PH', { month: 'short', day: 'numeric' });

  return [
    { title: 'Order placed', detail: stamp, state: 'done' },
    { title: 'Payment confirmed', detail: done('paid') ? stamp : '—', state: done('paid') ? 'done' : 'todo' },
    { title: 'Packed', detail: done('packed') ? stamp : '—', state: done('packed') ? 'done' : 'todo' },
    { title: 'Shipped', detail: done('shipped') ? stamp : '—', state: done('shipped') ? 'done' : 'todo' },
    { title: 'Out for delivery', detail: outForDelivery ? stamp : '—', state: outForDelivery ? 'done' : 'todo' },
    { title: 'Delivered', detail: done('delivered') ? stamp : '—', state: done('delivered') ? 'done' : 'todo', last: true },
  ];
}

export default function OrderTrackingScreen() {
  const { colors, onInk } = useTheme();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'OrderTracking'>>();
  const [order, setOrder] = useState<OrderPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<'offline' | 'failed' | null>(null);

  const load = useCallback((isInitial = false) => {
    if (isInitial) setLoading(true);
    orders
      .track(route.params.token)
      .then((data) => {
        setOrder(data);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof OfflineError ? 'offline' : 'failed');
      })
      .finally(() => setLoading(false));
  }, [route.params.token]);

  useEffect(() => {
    load(true);
    const interval = setInterval(() => load(false), 30_000);
    return () => clearInterval(interval);
  }, [load]);

  if (loading && !order) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.paper }}>
        <NavBar title="Order" onBack={() => navigation.goBack()} />
        <LoadingState label="Loading order…" />
      </SafeAreaView>
    );
  }

  if (!order) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.paper }}>
        <NavBar title="Order" onBack={() => navigation.goBack()} />
        {error === 'offline' ? <OfflineBanner onRetry={load} /> : null}
        <EmptyState
          title={error === 'offline' ? "You're offline" : 'Order not found'}
          body={
            error === 'offline'
              ? 'Reconnect to refresh tracking.'
              : 'Check the link or open the order from your account.'
          }
          action={<PillButton label="Retry" variant="volt" onPress={load} />}
        />
      </SafeAreaView>
    );
  }

  const steps = buildSteps(order);
  const getHelp = () =>
    Linking.openURL(`${API_BASE_URL.replace('/api/mobile/v1', '')}/contact/`).catch(() => undefined);
  const trackLive = () =>
    order.shipment?.tracking_url
      ? Linking.openURL(order.shipment.tracking_url).catch(() => undefined)
      : undefined;

  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: colors.paper }}>
      <NavBar
        title={`Order ${order.order_no}`}
        onBack={() => (navigation.canGoBack() ? navigation.goBack() : navigation.reset({ index: 0, routes: [{ name: 'Tabs' }] }))}
      />

      <ScrollView>
        {/* Ink status header — stays dark in both modes. */}
        <View style={{ backgroundColor: onInk.inkSurface, padding: space.screenX, gap: space.s6 }}>
          <Mono size={10} weight="semibold" color={colors.volt} style={{ letterSpacing: 1.4 }}>
            {order.shipment?.status === 'out_for_delivery' ? 'ARRIVING' : 'ORDER STATUS'}
          </Mono>
          <Text style={{ fontFamily: fonts.display, fontSize: 28, color: onInk.onInkSurface }}>
            {order.status_display}
          </Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.s8, paddingTop: space.xs }}>
            <Text style={{ fontFamily: fonts.bodyMedium, fontSize: 12, color: onInk.onInkMuted }}>
              {order.shipment ? (order.shipment.courier === 'jnt' ? 'J&T Express' : order.shipment.courier) : 'Courier pending'}
            </Text>
            {order.shipment?.waybill_no ? (
              <View
                style={{
                  backgroundColor: colors.elevated,
                  borderRadius: radius.tag,
                  paddingHorizontal: space.s8,
                  paddingVertical: 3,
                }}
              >
                <Mono size={10} color={onInk.onInkSurface}>{order.shipment.waybill_no}</Mono>
              </View>
            ) : null}
          </View>
        </View>

        {/* Six-step timeline. */}
        <View style={{ paddingHorizontal: space.screenX, paddingVertical: space.s18 }}>
          {steps.map((step) => (
            <View key={step.title} style={{ flexDirection: 'row', gap: space.s14 }}>
              <View style={{ width: 24, alignItems: 'center' }}>
                {step.state === 'done' ? (
                  <View style={{ width: 16, height: 16, borderRadius: radius.pill, backgroundColor: colors.volt }} />
                ) : (
                  <View
                    style={{
                      width: 14,
                      height: 14,
                      borderRadius: radius.pill,
                      backgroundColor: colors.paper,
                      borderWidth: 2,
                      borderColor: colors.border,
                    }}
                  />
                )}
                {!step.last ? (
                  <View
                    style={{
                      width: 2,
                      height: 38,
                      backgroundColor: step.state === 'done' ? colors.volt : colors.border,
                    }}
                  />
                ) : null}
              </View>
              <View style={{ flex: 1, paddingBottom: step.last ? 0 : space.s20, gap: 2 }}>
                <Text
                  style={{
                    fontFamily: fonts.bodySemiBold,
                    fontSize: 14,
                    color: step.state === 'done' ? colors.ink : colors.muted,
                  }}
                >
                  {step.title}
                </Text>
                <Mono size={11} color={colors.muted}>{step.detail}</Mono>
              </View>
            </View>
          ))}
        </View>

        {/* Items. */}
        <View style={{ paddingHorizontal: space.screenX, gap: space.s10 }}>
          <Text style={{ fontFamily: fonts.bodyBold, fontSize: 15, color: colors.ink }}>Items</Text>
          {(order.items ?? []).map((item) => (
            <View key={item.sku} style={{ flexDirection: 'row', alignItems: 'center', gap: space.s12 }}>
              <View
                style={{
                  width: 52,
                  height: 60,
                  borderRadius: radius.input,
                  backgroundColor: colors.surface,
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Text style={{ fontFamily: fonts.display, fontSize: 26, color: colors.muted }}>
                  {item.product_name.charAt(0)}
                </Text>
              </View>
              <View style={{ flex: 1, gap: 3 }}>
                <Text style={{ fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink }}>
                  {item.product_name}
                </Text>
                <Mono size={10} color={colors.muted}>
                  {`${item.color} · ${item.size} · ${FIT_SHORT[item.fit] ?? item.fit} ×${item.qty}`.toUpperCase()}
                </Mono>
              </View>
            </View>
          ))}
        </View>
        <View style={{ height: space.s14 }} />
      </ScrollView>

      <StickyBar>
        <View style={{ flexDirection: 'row', gap: space.s10 }}>
          <PillButton
            label="Get help"
            variant="outline"
            style={{ flex: 1, minHeight: 52 }}
            textStyle={{ fontFamily: fonts.bodyBold, fontSize: 15 }}
            onPress={getHelp}
          />
          <PillButton
            label="Track live"
            variant="volt"
            disabled={!order.shipment?.tracking_url}
            style={{ flex: 1, minHeight: 52 }}
            textStyle={{ fontFamily: fonts.bodyBold, fontSize: 15 }}
            onPress={trackLive}
          />
        </View>
      </StickyBar>
    </SafeAreaView>
  );
}

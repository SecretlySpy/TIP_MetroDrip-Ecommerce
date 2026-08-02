/**
 * M05 · Cart — Figma node 64:74.
 *
 * "Your Bag" nav (⋯ menu = clear bag) → line items (88×100 thumb r-12, dashed
 * variant tag, pill stepper with 44pt targets, mono line price) → dashed-INK
 * waybill summary card (mono eyebrow row, subtotal/shipping rows, Anton 26
 * total) → sticky INK "Checkout — <total>".
 *
 * Every money string on this screen comes from /cart/validate/ — including
 * line totals, subtotal, shipping preview, and the grand total (D-13).
 */

import { useIsFocused, useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import React, { useEffect, useState } from 'react';
import { Alert, Pressable, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { request } from '@/api/client';
import { commerce } from '@/api/endpoints';
import type { CartValidation, Zone } from '@/api/types';
import { EmptyState, Mono, NavBar, PillButton, QtyStepper, StickyBar } from '@/components/primitives';
import type { RootStackParamList } from '@/navigation';
import { useCart } from '@/store/CartContext';
import { useTheme } from '@/theme/ThemeProvider';
import { radius, space } from '@/theme/theme';
import { fonts } from '@/theme/typography';

export default function CartScreen() {
  const { colors } = useTheme();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const cart = useCart();
  const focused = useIsFocused();

  const [validation, setValidation] = useState<CartValidation | null>(null);
  const [zone, setZone] = useState<Zone | null>(null);
  const [serverTotals, setServerTotals] = useState<{
    shipping?: string;
    total?: string;
    zoneName?: string;
  }>({});

  useEffect(() => {
    if (!focused || cart.lines.length === 0) {
      setValidation(null);
      return;
    }
    (async () => {
      // Default preview zone = first active zone (NCR); checkout re-selects.
      const zoneList = zone ? null : await commerce.zones().catch(() => null);
      const previewZone = zone ?? zoneList?.results?.[0] ?? null;
      if (previewZone && !zone) setZone(previewZone);

      const items = cart.lines.map((line) => ({ variant_id: line.variantId, qty: line.qty }));
      const data = (await (previewZone
        ? validateWithZone(items, previewZone.id)
        : commerce.validateCart(items)
      ).catch(() => null)) as (CartValidation & Record<string, string>) | null;

      if (data) {
        setValidation(data);
        setServerTotals({
          shipping: data.shipping_fee_display,
          total: data.total_display,
          zoneName: data.zone_name,
        });
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focused, cart.lines]);

  const lineFor = (variantId: number) =>
    validation?.lines.find((line) => line.variant_id === variantId);

  const clearBag = () => {
    Alert.alert('Clear bag', 'Remove all items from your bag?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Clear', style: 'destructive', onPress: () => cart.clear() },
    ]);
  };

  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: colors.paper }}>
      <NavBar
        title="Your Bag"
        onBack={() => navigation.goBack()}
        right={
          cart.lines.length > 0 ? (
            <Pressable onPress={clearBag} hitSlop={12} accessibilityRole="button" accessibilityLabel="Bag options">
              <Text style={{ fontSize: 18, color: colors.ink, fontFamily: fonts.body }}>⋯</Text>
            </Pressable>
          ) : undefined
        }
      />

      {cart.lines.length === 0 ? (
        <EmptyState
          title="Your bag is empty"
          body="Fresh drops are waiting in the shop."
          action={
            <PillButton
              label="Shop the drop"
              variant="volt"
              onPress={() => navigation.navigate('Tabs', { screen: 'Shop' })}
            />
          }
        />
      ) : (
        <>
          <ScrollView contentContainerStyle={{ paddingHorizontal: space.screenX, paddingVertical: space.s14, gap: space.s14 }}>
            {cart.lines.map((line) => {
              const server = lineFor(line.variantId);
              const short = server && (server.available ?? 0) < line.qty;
              return (
                <View key={line.variantId} style={{ flexDirection: 'row', gap: space.s12 }}>
                  <View
                    style={{
                      width: 88,
                      height: 100,
                      borderRadius: radius.card,
                      backgroundColor: colors.surface,
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <Text style={{ fontFamily: fonts.display, fontSize: 42, color: colors.border }}>
                      {line.productName.charAt(0)}
                    </Text>
                  </View>

                  <View style={{ flex: 1, gap: space.s6 }}>
                    <Text style={{ fontFamily: fonts.bodySemiBold, fontSize: 14, color: colors.ink }}>
                      {line.productName}
                    </Text>
                    {/* Dashed waybill-style variant tag (§14 motif). */}
                    <View
                      style={{
                        alignSelf: 'flex-start',
                        borderWidth: 1,
                        borderStyle: 'dashed',
                        borderColor: colors.border,
                        borderRadius: radius.tag,
                        paddingHorizontal: space.s8,
                        paddingVertical: 3,
                      }}
                    >
                      <Mono size={10} color={colors.muted}>
                        {`${line.color} · ${line.size} · ${line.fit}`.toUpperCase()}
                      </Mono>
                    </View>
                    {short ? (
                      <Mono size={10} weight="medium" color={colors.danger}>
                        Only {server?.available ?? 0} available — adjust quantity
                      </Mono>
                    ) : null}
                    <View
                      style={{
                        flexDirection: 'row',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        paddingTop: space.xs,
                      }}
                    >
                      <QtyStepper
                        qty={line.qty}
                        max={server?.available}
                        onChange={(delta) => cart.updateQty(line.variantId, delta)}
                      />
                      <Mono size={14} weight="semibold">
                        {server?.line_total_display ?? line.priceDisplay}
                      </Mono>
                    </View>
                  </View>
                </View>
              );
            })}

            {/* Dashed-ink waybill summary card. */}
            <View
              style={{
                borderWidth: 1,
                borderStyle: 'dashed',
                borderColor: colors.ink,
                borderRadius: radius.card,
                paddingHorizontal: space.screenX,
                paddingVertical: space.s14,
                gap: 9,
              }}
            >
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Mono size={9} weight="semibold" color={colors.muted} style={{ letterSpacing: 1 }}>
                  ORDER SUMMARY
                </Mono>
                <Mono size={9} color={colors.muted}>
                  {cart.itemCount} ITEM{cart.itemCount === 1 ? '' : 'S'}
                </Mono>
              </View>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ fontFamily: fonts.body, fontSize: 13, color: colors.muted }}>Subtotal</Text>
                <Mono size={13} weight="semibold">{validation?.subtotal_display ?? '—'}</Mono>
              </View>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <Text style={{ fontFamily: fonts.body, fontSize: 13, color: colors.muted }}>
                  Shipping{serverTotals.zoneName ? ` — ${serverTotals.zoneName}` : ''}
                </Text>
                <Mono size={13} weight="semibold">{serverTotals.shipping ?? 'At checkout'}</Mono>
              </View>
              <View
                style={{
                  flexDirection: 'row',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  paddingTop: space.s8,
                }}
              >
                <Text style={{ fontFamily: fonts.bodyBold, fontSize: 14, color: colors.ink }}>Total</Text>
                <Text style={{ fontFamily: fonts.display, fontSize: 26, color: colors.ink }}>
                  {serverTotals.total ?? validation?.subtotal_display ?? '—'}
                </Text>
              </View>
            </View>
          </ScrollView>

          <StickyBar>
            <PillButton
              label={`Checkout — ${serverTotals.total ?? validation?.subtotal_display ?? ''}`}
              variant="ink"
              style={{ height: 54 }}
              textStyle={{ fontFamily: fonts.bodyBold, fontSize: 16 }}
              onPress={() => navigation.navigate('Checkout')}
            />
          </StickyBar>
        </>
      )}
    </SafeAreaView>
  );
}

/** Zone-aware validate: same endpoint plus zone_id, so shipping and the grand
 * total also come from the server (D-13 — the app adds nothing up itself). */
function validateWithZone(items: { variant_id: number; qty: number }[], zoneId: number) {
  return request<CartValidation & Record<string, string>>('/cart/validate/', {
    method: 'POST',
    body: { items, zone_id: zoneId },
    auth: false,
  });
}

/**
 * M04 · Product Detail — Figma node 64:2.
 *
 * Gallery (330pt, pagination dots — active is an 18×6 ink pill) → category →
 * name/price row → rating (stars in accentText) → colour swatches (2pt ink
 * ring on selected) → size chips (sold-out = surface + muted + strikethrough,
 * the §2.1 non-colour cue) → fit chips → danger stock line → description →
 * sticky volt "Add to Cart — <price>". Price text is the SERVER's display
 * string — the app never assembles money (D-13).
 */

import { useNavigation, useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RouteProp } from '@react-navigation/native';
import React, { useEffect, useMemo, useState } from 'react';
import { Image, Pressable, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { OfflineError } from '@/api/client';
import { account, catalog } from '@/api/endpoints';
import type { ProductDetail, Variant } from '@/api/types';
import {
  EmptyState,
  LoadingState,
  MicroLabel,
  Mono,
  NavBar,
  OfflineBanner,
  PillButton,
  StickyBar,
} from '@/components/primitives';
import type { RootStackParamList } from '@/navigation';
import { useAuth } from '@/store/AuthContext';
import { useCart } from '@/store/CartContext';
import { useTheme } from '@/theme/ThemeProvider';
import { radius, space } from '@/theme/theme';
import { fonts } from '@/theme/typography';

const SIZE_ORDER = ['XS', 'S', 'M', 'L', 'XL', 'XXL'];

/** Swatch fills for known colour names; unknown names fall back to surface. */
function swatchColor(name: string, palette: { ink: string; volt: string; border: string; surface: string }) {
  const normalized = name.toLowerCase();
  if (normalized.includes('black') || normalized.includes('navy')) return palette.ink;
  if (normalized.includes('lime') || normalized.includes('neon') || normalized.includes('volt'))
    return palette.volt;
  if (normalized.includes('white') || normalized.includes('bone') || normalized.includes('gray') || normalized.includes('grey'))
    return palette.border;
  return palette.surface;
}

export default function ProductDetailScreen() {
  const { colors } = useTheme();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute<RouteProp<RootStackParamList, 'ProductDetail'>>();
  const { customer } = useAuth();
  const cart = useCart();

  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<'offline' | 'failed' | null>(null);
  const [galleryIndex, setGalleryIndex] = useState(0);
  const [size, setSize] = useState<string | null>(null);
  const [color, setColor] = useState<string | null>(null);
  const [fit, setFit] = useState<string | null>(null);
  const [wishlisted, setWishlisted] = useState(false);
  const [added, setAdded] = useState(false);

  const load = () => {
    setLoading(true);
    setError(null);
    catalog
      .productDetail(route.params.slug)
      .then((data) => {
        setProduct(data);
        setWishlisted(data.is_wishlisted);
      })
      .catch((err) => {
        setProduct(null);
        setError(err instanceof OfflineError ? 'offline' : 'failed');
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route.params.slug]);

  const variants = product?.variants ?? [];
  const sizes = useMemo(
    () => [...new Set(variants.map((v) => v.size))].sort((a, b) => SIZE_ORDER.indexOf(a) - SIZE_ORDER.indexOf(b)),
    [variants],
  );
  const colorsAxis = useMemo(() => [...new Set(variants.map((v) => v.color))].sort(), [variants]);
  const fits = useMemo(() => [...new Set(variants.map((v) => v.fit))], [variants]);

  const matches = (v: Variant, axis: { size?: string | null; color?: string | null; fit?: string | null }) =>
    (!axis.size || v.size === axis.size) && (!axis.color || v.color === axis.color) && (!axis.fit || v.fit === axis.fit);

  const axisAvailable = (partial: { size?: string; color?: string; fit?: string }) =>
    variants.some((v) => matches(v, { size: partial.size ?? size, color: partial.color ?? color, fit: partial.fit ?? fit }) && v.available > 0);

  const selected = useMemo(
    () => (size && color && fit ? variants.find((v) => v.size === size && v.color === color && v.fit === fit) ?? null : null),
    [variants, size, color, fit],
  );

  const priceDisplay = selected?.price_display ?? product?.price_display ?? '';
  const stars = product ? '★'.repeat(Math.round(product.review_avg ?? 0)).padEnd(5, '☆') : '';

  if (loading) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.paper }}>
        <NavBar title="Product" onBack={() => navigation.goBack()} />
        <LoadingState />
      </SafeAreaView>
    );
  }

  if (!product) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.paper }}>
        <NavBar title="Product" onBack={() => navigation.goBack()} />
        {error === 'offline' ? <OfflineBanner onRetry={load} /> : null}
        <EmptyState
          title={error === 'offline' ? "You're offline" : 'Could not load product'}
          body={error === 'offline' ? 'Reconnect and try again.' : 'Pull back and open the product again.'}
          action={<PillButton label="Retry" variant="volt" onPress={load} />}
        />
      </SafeAreaView>
    );
  }

  const addToCart = () => {
    if (!product || !selected || selected.available < 1) return;
    cart.add(
      {
        variantId: selected.id,
        sku: selected.sku,
        productName: product.name,
        productSlug: product.slug,
        size: selected.size,
        color: selected.color,
        fit: selected.fit,
        priceDisplay: selected.price_display,
      },
      1,
    );
    setAdded(true);
    setTimeout(() => setAdded(false), 1800);
  };

  const toggleWishlist = async () => {
    if (!product) return;
    if (!customer) {
      navigation.navigate('Auth', { mode: 'signin' });
      return;
    }
    const result = await account.toggleWishlist(product.id).catch(() => null);
    if (result) setWishlisted(result.added);
  };

  if (!product) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.paper }}>
        <NavBar title="" onBack={() => navigation.goBack()} />
      </SafeAreaView>
    );
  }

  const chipStyle = (state: 'idle' | 'selected' | 'soldout') => ({
    paddingHorizontal: space.s14,
    paddingVertical: space.s10,
    borderRadius: radius.chip,
    backgroundColor: state === 'selected' ? colors.ink : state === 'soldout' ? colors.surface : colors.paper,
    borderWidth: state === 'selected' ? 0 : 1,
    borderColor: colors.border,
    minHeight: 44,
  });
  const chipText = (state: 'idle' | 'selected' | 'soldout') => ({
    fontFamily: fonts.bodySemiBold,
    fontSize: 13,
    color: state === 'selected' ? colors.paper : state === 'soldout' ? colors.muted : colors.ink,
    textDecorationLine: state === 'soldout' ? ('line-through' as const) : ('none' as const),
  });

  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: colors.paper }}>
      <NavBar
        title={product.category.name}
        onBack={() => navigation.goBack()}
        right={
          <Pressable onPress={toggleWishlist} hitSlop={12} accessibilityRole="button" accessibilityLabel={wishlisted ? 'Remove from wishlist' : 'Save to wishlist'}>
            <Text style={{ fontSize: 18, color: wishlisted ? colors.danger : colors.ink }}>
              {wishlisted ? '♥' : '♡'}
            </Text>
          </Pressable>
        }
      />

      <ScrollView>
        {/* Gallery — 330pt with pagination dots (active = 18×6 ink pill). */}
        <View style={{ height: 330, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' }}>
          {product.images.length > 0 ? (
            <Image source={{ uri: product.images[Math.min(galleryIndex, product.images.length - 1)] }} resizeMode="cover" style={{ width: '100%', height: '100%' }} />
          ) : (
            <Text style={{ fontFamily: fonts.display, fontSize: 170, color: colors.border }}>
              {product.name.charAt(0)}
            </Text>
          )}
          <View style={{ position: 'absolute', bottom: space.s12, flexDirection: 'row', gap: space.s6 }}>
            {(product.images.length > 0 ? product.images : [0, 1, 2, 3]).map((_, index, all) => (
              <Pressable
                key={index}
                onPress={() => setGalleryIndex(index)}
                // A 6dp dot with hitSlop 8 gave a 22x22 target — half the
                // minimum, with four of them side by side. 19 each side clears
                // 44pt without changing a pixel of the visual.
                hitSlop={19}
                accessibilityRole="button"
                accessibilityLabel={`Image ${index + 1} of ${all.length}`}
                accessibilityState={{ selected: index === galleryIndex }}
              >
                <View
                  style={{
                    width: index === galleryIndex ? 18 : 6,
                    height: 6,
                    borderRadius: radius.pill,
                    backgroundColor: index === galleryIndex ? colors.ink : colors.border,
                  }}
                />
              </Pressable>
            ))}
          </View>
        </View>

        <View style={{ padding: space.screenX, gap: 13 }}>
          <Mono size={10} color={colors.muted} style={{ letterSpacing: 0.4 }}>
            {product.category.name.toLowerCase()}
          </Mono>

          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text
              style={{
                fontFamily: fonts.bodyBold,
                fontSize: 20,
                color: colors.ink,
                flex: 1,
                marginRight: 12,
              }}
            >
              {product.name}
            </Text>
            {/* Price must never be the thing that shrinks: it is the one
                figure on this screen a shopper is looking for, and it is
                server-computed (D-13), so truncating it would misreport it. */}
            <Mono size={18} weight="semibold" style={{ flexShrink: 0 }}>
              {priceDisplay}
            </Mono>
          </View>

          {product.review_count > 0 ? (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.s8 }}>
              <Text style={{ fontFamily: fonts.body, fontSize: 13, color: colors.accentText }}>{stars}</Text>
              <Mono size={12} weight="semibold">{(product.review_avg ?? 0).toFixed(1)}</Mono>
              <Text style={{ fontFamily: fonts.body, fontSize: 12, color: colors.muted }}>
                {product.review_count} review{product.review_count === 1 ? '' : 's'}
              </Text>
            </View>
          ) : null}

          {/* Colour axis — swatches, 2pt ink outline on selected. */}
          <View style={{ gap: space.s8 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={{ fontFamily: fonts.bodySemiBold, fontSize: 11, color: colors.muted }}>Color</Text>
              <Mono size={11} weight="semibold">{color ?? '—'}</Mono>
            </View>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.s8 }}>
              {colorsAxis.map((name) => (
                <Pressable
                  key={name}
                  // 34dp swatch + 5 each side reaches 44pt; the circle stays 34.
                  hitSlop={5}
                  accessibilityRole="button"
                  accessibilityLabel={`Colour ${name}`}
                  accessibilityState={{ selected: color === name, disabled: !axisAvailable({ color: name }) }}
                  onPress={() => setColor(color === name ? null : name)}
                  style={{
                    width: 34,
                    height: 34,
                    borderRadius: radius.pill,
                    backgroundColor: swatchColor(name, colors),
                    borderWidth: color === name ? 2 : 0,
                    borderColor: colors.ink,
                    opacity: axisAvailable({ color: name }) ? 1 : 0.4,
                  }}
                />
              ))}
            </View>
          </View>

          {/* Size axis — chips; sold-out uses surface + muted + strikethrough. */}
          <View style={{ gap: space.s8 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={{ fontFamily: fonts.bodySemiBold, fontSize: 11, color: colors.muted }}>Size</Text>
              <Mono size={11} weight="semibold">{size ?? '—'}</Mono>
            </View>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.s8 }}>
              {sizes.map((value) => {
                const soldOut = !axisAvailable({ size: value });
                const state = size === value ? 'selected' : soldOut ? 'soldout' : 'idle';
                return (
                  <Pressable
                    key={value}
                    accessibilityRole="button"
                    accessibilityLabel={soldOut ? `Size ${value}, sold out` : `Size ${value}`}
                    accessibilityState={{ selected: size === value, disabled: soldOut }}
                    disabled={soldOut}
                    onPress={() => setSize(size === value ? null : value)}
                    style={chipStyle(state)}
                  >
                    <Text style={chipText(state)}>{value}</Text>
                  </Pressable>
                );
              })}
            </View>
          </View>

          {/* Fit axis. */}
          <View style={{ gap: space.s8 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={{ fontFamily: fonts.bodySemiBold, fontSize: 11, color: colors.muted }}>Fit</Text>
              <Mono size={11} weight="semibold">
                {fit ? fit.charAt(0).toUpperCase() + fit.slice(1) : '—'}
              </Mono>
            </View>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.s8 }}>
              {fits.map((value) => {
                const soldOut = !axisAvailable({ fit: value });
                const state = fit === value ? 'selected' : soldOut ? 'soldout' : 'idle';
                return (
                  <Pressable
                    key={value}
                    accessibilityRole="button"
                    accessibilityLabel={`Fit ${value}`}
                    accessibilityState={{ selected: fit === value, disabled: soldOut }}
                    disabled={soldOut}
                    onPress={() => setFit(fit === value ? null : value)}
                    style={{ ...chipStyle(state), paddingHorizontal: 15 }}
                  >
                    <Text style={chipText(state)}>{value.charAt(0).toUpperCase() + value.slice(1)}</Text>
                  </Pressable>
                );
              })}
            </View>
          </View>

          {/* Live stock status — server-decided (D-13). */}
          {selected ? (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.s8 }}>
              <View
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: radius.pill,
                  backgroundColor: selected.available > 0 ? (selected.available <= 5 ? colors.danger : colors.accentText) : colors.danger,
                }}
              />
              <Mono size={11} weight="medium" color={selected.available <= 5 ? colors.danger : colors.muted}>
                {selected.available <= 0
                  ? 'Out of stock'
                  : selected.available <= 5
                    ? `Only ${selected.available} left in this variant`
                    : `${selected.available} in stock`}
              </Mono>
            </View>
          ) : null}

          {product.description ? (
            <Text style={{ fontFamily: fonts.body, fontSize: 13, color: colors.muted }}>
              {product.description}
            </Text>
          ) : null}
        </View>
      </ScrollView>

      <StickyBar>
        <PillButton
          label={added ? '✓ Added to cart' : selected ? `Add to Cart — ${priceDisplay}` : 'Select size · colour · fit'}
          variant="volt"
          disabled={!selected || selected.available < 1}
          style={{ minHeight: 54 }}
          textStyle={{ fontFamily: fonts.bodyBold, fontSize: 16 }}
          onPress={addToCart}
        />
      </StickyBar>
    </SafeAreaView>
  );
}

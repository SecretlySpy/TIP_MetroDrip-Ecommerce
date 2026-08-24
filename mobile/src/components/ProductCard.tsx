/**
 * Grid card shared by M02 (63:105), M03 (63:187), and M11 (67:62).
 *
 * M02/M03: 186pt surface thumbnail (radius 14), 30pt paper heart circle with
 * ♡, mono category, SemiBold 13 name, mono SemiBold 13 price.
 * M11: 180pt thumbnail, FILLED heart (ink circle, volt ♥), and the price row
 * carries an inline Add/Notify pill; sold-out items show a danger tag inside
 * the thumbnail.
 */

import React from 'react';
import { Image, Pressable, Text, View } from 'react-native';

import type { ProductCard as ProductCardData } from '@/api/types';
import { MicroLabel, Mono } from '@/components/primitives';
import { useTheme } from '@/theme/ThemeProvider';
import { radius, space } from '@/theme/theme';
import { fonts } from '@/theme/typography';

export function ProductCard({
  product,
  onPress,
  wishlisted,
  onToggleWishlist,
  soldOut,
  /** M11 renders an Add/Notify pill inline with the price. */
  action,
  thumbHeight = 186,
}: {
  product: ProductCardData;
  onPress: () => void;
  wishlisted?: boolean;
  onToggleWishlist?: () => void;
  soldOut?: boolean;
  action?: React.ReactNode;
  thumbHeight?: number;
}) {
  const { colors } = useTheme();
  const image = product.images?.[0];

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${product.name}, ${product.price_display}${soldOut ? ', sold out' : ''}`}
      style={{ flex: 1, gap: space.s6 }}
    >
      <View
        style={{
          height: thumbHeight,
          borderRadius: radius.thumb,
          backgroundColor: colors.surface,
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
        }}
      >
        {image ? (
          <Image source={{ uri: image }} resizeMode="cover" style={{ width: '100%', height: '100%' }} />
        ) : (
          // Placeholder monogram exactly as drawn (Anton, border colour).
          <Text style={{ fontFamily: fonts.display, fontSize: 72, color: colors.border }}>
            {product.name.charAt(0)}
          </Text>
        )}

        {onToggleWishlist ? (
          <Pressable
            onPress={onToggleWishlist}
            // Visual circle is 30pt per the design; hitSlop lifts the touch
            // target to ≥ 44×44 without changing what's drawn (NFR-20).
            hitSlop={7}
            accessibilityRole="button"
            accessibilityLabel={wishlisted ? 'Remove from wishlist' : 'Save to wishlist'}
            style={{
              position: 'absolute',
              top: space.s8,
              right: space.s8,
              width: 30,
              height: 30,
              borderRadius: radius.pill,
              backgroundColor: wishlisted ? colors.ink : colors.paper,
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Text style={{ fontSize: wishlisted ? 13 : 14, color: wishlisted ? colors.volt : colors.ink }}>
              {wishlisted ? '♥' : '♡'}
            </Text>
          </Pressable>
        ) : null}

        {soldOut ? (
          <View
            style={{
              position: 'absolute',
              left: space.s8,
              bottom: space.s8,
              backgroundColor: colors.danger,
              borderRadius: radius.tag,
              paddingHorizontal: space.s8,
              paddingVertical: space.xs,
            }}
          >
            <Mono size={8} weight="semibold" color={colors.paper} style={{ letterSpacing: 0.5 }}>
              SOLD OUT
            </Mono>
          </View>
        ) : null}
      </View>

      <MicroLabel style={{ fontSize: 9, letterSpacing: 0.4 }}>
        {product.category.name.toLowerCase()}
      </MicroLabel>
      <Text numberOfLines={2} style={{ fontFamily: fonts.bodySemiBold, fontSize: 13, color: colors.ink }}>
        {product.name}
      </Text>

      {action ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <Mono size={13} weight="semibold">{product.price_display}</Mono>
          {action}
        </View>
      ) : (
        <Mono size={13} weight="semibold">{product.price_display}</Mono>
      )}
    </Pressable>
  );
}

/** Small inline pill used by M11's price row (volt "Add" / surface "Notify"). */
export function CardActionPill({
  label,
  variant,
  onPress,
}: {
  label: string;
  variant: 'volt' | 'surface';
  onPress: () => void;
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={onPress}
      hitSlop={12}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={{
        backgroundColor: variant === 'volt' ? colors.volt : colors.surface,
        borderRadius: radius.pill,
        paddingHorizontal: space.s10,
        paddingVertical: 5,
      }}
    >
      <Text
        style={{
          fontFamily: fonts.bodySemiBold,
          fontSize: 11,
          color: variant === 'volt' ? colors.onVolt : colors.muted,
        }}
      >
        {label}
      </Text>
    </Pressable>
  );
}

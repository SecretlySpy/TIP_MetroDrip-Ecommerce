/* eslint-disable @typescript-eslint/no-unused-vars */
/* eslint-disable react-hooks/exhaustive-deps */
/**
 * M11 · Saved / Wishlist (Tab) — Figma node 67:45.
 *
 * "Saved" nav with ⋯ action → count row (mono 11 left, accentText SemiBold 12
 * "Move all to bag" right) → 2-column grid of 180pt cards with FILLED hearts
 * (ink circle, volt ♥); in-stock cards carry a volt "Add" pill inline with the
 * price, sold-out cards a danger "SOLD OUT" tag and a surface "Notify" pill.
 */

import { useIsFocused, useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import React, { useEffect, useState } from 'react';
import { Alert, FlatList, Pressable, RefreshControl, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { OfflineError } from '@/api/client';
import { account } from '@/api/endpoints';
import type { WishlistEntry } from '@/api/types';
import { CardActionPill, ProductCard } from '@/components/ProductCard';
import { EmptyState, LoadingState, Mono, NavBar, PillButton } from '@/components/primitives';
import type { RootStackParamList } from '@/navigation';
import { useAuth } from '@/store/AuthContext';
import { useTheme } from '@/theme/ThemeProvider';
import { space } from '@/theme/theme';
import { fonts } from '@/theme/typography';

export default function WishlistScreen() {
  const { colors } = useTheme();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { customer } = useAuth();
  const focused = useIsFocused();

  const [entries, setEntries] = useState<WishlistEntry[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const [loadError, setLoadError] = useState<'offline' | 'failed' | null>(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    // Was `.catch(() => undefined)`, which left `entries` empty and rendered
    // the "Nothing saved yet" state — telling the shopper their wishlist was
    // empty when the request had actually failed. An error and an empty list
    // are different facts and must look different.
    return account
      .wishlist()
      .then((page) => {
        setEntries(page.results);
        setLoadError(null);
      })
      .catch((err: unknown) => {
        setLoadError(err instanceof OfflineError ? 'offline' : 'failed');
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (focused && customer) load();
  }, [focused, customer]);

  if (!customer) {
    return (
      <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: colors.paper }}>
        <NavBar title="Saved" />
        <EmptyState
          title="Save your favourites"
          body="Sign in to keep fits you love and get restock alerts."
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

  const remove = async (productId: number) => {
    // The row used to be filtered out unconditionally, even when the server
    // call failed — so a failed removal looked successful until the next load
    // silently brought the item back. Only drop it once the server agrees.
    const previous = entries;
    setEntries((current) => current.filter((entry) => entry.product.id !== productId));
    try {
      await account.toggleWishlist(productId);
    } catch {
      setEntries(previous);
      setLoadError('failed');
    }
  };

  // Wishlist saves are product-level; the exact SKU is chosen on the detail
  // page where the three-axis picker lives (D-13: the app never guesses one).
  const addToBag = (entry: WishlistEntry) =>
    navigation.navigate('ProductDetail', { slug: entry.product.slug });

  const notifyMe = (entry: WishlistEntry) =>
    Alert.alert(
      'Notify me',
      `We'll alert you when ${entry.product.name} is back in stock — it stays saved here.`,
    );

  const moveAllToBag = () => {
    const first = entries.find((entry) => entry.in_stock);
    if (first) addToBag(first);
  };

  const clearAll = () =>
    Alert.alert('Saved items', undefined, [
      { text: 'Move all to bag', onPress: moveAllToBag },
      {
        text: 'Remove all',
        style: 'destructive',
        onPress: async () => {
          for (const entry of entries) await remove(entry.product.id);
        },
      },
      { text: 'Cancel', style: 'cancel' },
    ]);

  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: colors.paper }}>
      <NavBar
        title="Saved"
        right={
          entries.length > 0 ? (
            <Pressable onPress={clearAll} hitSlop={12} accessibilityRole="button" accessibilityLabel="Saved options">
              <Text style={{ fontSize: 18, color: colors.ink, fontFamily: fonts.body }}>⋯</Text>
            </Pressable>
          ) : undefined
        }
      />

      <FlatList
        data={entries}
        numColumns={2}
        keyExtractor={(entry) => String(entry.product.id)}
        columnWrapperStyle={{ gap: space.s12, paddingHorizontal: space.screenX }}
        contentContainerStyle={{ gap: space.s12, paddingVertical: space.s14 }}
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
        ListHeaderComponent={
          entries.length > 0 ? (
            <View
              style={{
                flexDirection: 'row',
                justifyContent: 'space-between',
                alignItems: 'center',
                paddingHorizontal: space.screenX,
                paddingBottom: space.s12,
              }}
            >
              <Mono size={11} color={colors.muted}>
                {entries.length} item{entries.length === 1 ? '' : 's'} saved
              </Mono>
              {entries.some((entry) => entry.in_stock) ? (
                <Pressable
                  onPress={moveAllToBag}
                  hitSlop={12}
                  accessibilityRole="button"
                  accessibilityLabel="Move all to bag"
                >
                  <Text style={{ fontFamily: fonts.bodySemiBold, fontSize: 12, color: colors.accentText }}>
                    Move all to bag
                  </Text>
                </Pressable>
              ) : null}
            </View>
          ) : null
        }
        renderItem={({ item }) => (
          <ProductCard
            product={item.product}
            thumbHeight={180}
            wishlisted
            soldOut={!item.in_stock}
            onToggleWishlist={() => remove(item.product.id)}
            onPress={() => navigation.navigate('ProductDetail', { slug: item.product.slug })}
            action={
              item.in_stock ? (
                <CardActionPill label="Add" variant="volt" onPress={() => addToBag(item)} />
              ) : (
                <CardActionPill label="Notify" variant="surface" onPress={() => notifyMe(item)} />
              )
            }
          />
        )}
        ListEmptyComponent={
          loading ? (
            <LoadingState label="Loading saved items…" />
          ) : loadError ? (
            <EmptyState
              title={loadError === 'offline' ? "You're offline" : "Couldn't load your saves"}
              body={
                loadError === 'offline'
                  ? 'Reconnect and pull to refresh.'
                  : 'Something went wrong on our side — your saved items are safe.'
              }
              action={<PillButton label="Retry" variant="volt" onPress={load} />}
            />
          ) : (
            <EmptyState
              title="Nothing saved yet"
              body="Tap the heart on any product to keep it here."
              action={
                <PillButton
                  label="Browse the shop"
                  variant="volt"
                  onPress={() => navigation.navigate('Tabs', { screen: 'Shop' })}
                />
              }
            />
          )
        }
      />
    </SafeAreaView>
  );
}


/**
 * M02 · Home (Tab) — Figma node 63:67.
 *
 * Header (brand lockup, bell with danger unread dot, bag) → ink hero with volt
 * eyebrow + Anton 38 headline + volt CTA → category chip rail → "New Arrivals"
 * 2-column grid. Pull-to-refresh; FR-30 cached browse when offline.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import React, { useCallback, useEffect, useState } from 'react';
import { FlatList, Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { account, catalog, notifications } from '@/api/endpoints';
import { OfflineError } from '@/api/client';
import type { CategoryRef, ProductCard as ProductCardData } from '@/api/types';
import { ProductCard } from '@/components/ProductCard';
import { MicroLabel, Mono, OfflineBanner, PillButton } from '@/components/primitives';
import type { RootStackParamList } from '@/navigation';
import { useAuth } from '@/store/AuthContext';
import { useTheme } from '@/theme/ThemeProvider';
import { radius, space } from '@/theme/theme';
import { fonts } from '@/theme/typography';

const CACHE_KEY = 'metrodrip.cache.home';

export default function HomeScreen() {
  const { colors, onInk } = useTheme();
  const { customer } = useAuth();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();

  const [products, setProducts] = useState<ProductCardData[]>([]);
  const [categories, setCategories] = useState<CategoryRef[]>([]);
  const [activeCategory, setActiveCategory] = useState<string>('');
  const [unread, setUnread] = useState(0);
  const [offline, setOffline] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [wishlisted, setWishlisted] = useState<Set<number>>(new Set());

  const load = useCallback(
    async (category = activeCategory) => {
      try {
        const [productPage, categoryList] = await Promise.all([
          catalog.products({ sort: 'newest', category: category || undefined }),
          catalog.categories(),
        ]);
        setProducts(productPage.results.slice(0, 8));
        setCategories(categoryList.results);
        setOffline(false);
        AsyncStorage.setItem(
          CACHE_KEY,
          JSON.stringify({ products: productPage.results.slice(0, 8), categories: categoryList.results }),
        ).catch(() => undefined);
      } catch (error) {
        if (error instanceof OfflineError) {
          // FR-30: cached catalog browsing with the explicit banner.
          setOffline(true);
          const cached = await AsyncStorage.getItem(CACHE_KEY);
          if (cached) {
            const parsed = JSON.parse(cached);
            setProducts(parsed.products ?? []);
            setCategories(parsed.categories ?? []);
          }
        }
      }
      if (customer) {
        notifications
          .list()
          .then((page) => setUnread(page.unread_count))
          .catch(() => undefined);
        account
          .wishlist()
          .then((page) => setWishlisted(new Set(page.results.map((entry) => entry.product.id))))
          .catch(() => undefined);
      }
    },
    [activeCategory, customer],
  );

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customer]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const selectCategory = (slug: string) => {
    setActiveCategory(slug);
    load(slug);
  };

  const toggleWishlist = async (productId: number) => {
    if (!customer) {
      navigation.navigate('Auth', { mode: 'signin' });
      return;
    }
    const result = await account.toggleWishlist(productId).catch(() => null);
    if (result) {
      setWishlisted((previous) => {
        const next = new Set(previous);
        if (result.added) next.add(productId);
        else next.delete(productId);
        return next;
      });
    }
  };

  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: colors.paper }}>
      {/* Header — brand lockup; "Drip" uses accentText on light (§2.1 rule 1). */}
      <View
        style={{
          height: 52,
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingHorizontal: space.screenX,
        }}
      >
        <View style={{ flexDirection: 'row' }}>
          <Text style={{ fontFamily: fonts.display, fontSize: 22, color: colors.ink }}>Metro</Text>
          <Text style={{ fontFamily: fonts.display, fontSize: 22, color: colors.accentText }}>
            Drip
          </Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.screenX }}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={unread > 0 ? `Notifications, ${unread} unread` : 'Notifications'}
            hitSlop={12}
            onPress={() => navigation.navigate('Tabs' as never, { screen: 'Orders' } as never)}
          >
            <Text style={{ fontSize: 19, color: colors.ink, fontFamily: fonts.body }}>◔</Text>
            {unread > 0 ? (
              <View
                style={{
                  position: 'absolute',
                  left: 11,
                  top: 0,
                  width: 8,
                  height: 8,
                  borderRadius: radius.pill,
                  backgroundColor: colors.danger,
                }}
              />
            ) : null}
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Cart"
            hitSlop={12}
            onPress={() => navigation.navigate('Cart')}
          >
            <Text style={{ fontSize: 17, color: colors.ink, fontFamily: fonts.body }}>🛍</Text>
          </Pressable>
        </View>
      </View>

      {offline ? <OfflineBanner onRetry={() => load()} /> : null}

      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        contentContainerStyle={{ paddingBottom: space.screenX }}
      >
        {/* Hero — ink block stays dark in BOTH modes (§2 nuance). */}
        <View
          style={{
            backgroundColor: onInk.inkSurface,
            paddingHorizontal: space.s20,
            paddingTop: space.screenX,
            paddingBottom: space.s20,
            gap: space.s10,
          }}
        >
          <Mono size={10} weight="semibold" color={colors.volt} style={{ letterSpacing: 1.4 }}>
            DROP 01 · LIVE NOW
          </Mono>
          <Text
            style={{
              fontFamily: fonts.display,
              fontSize: 38,
              lineHeight: 38,
              color: onInk.onInkSurface,
              width: 300,
            }}
          >
            Urban Style{'\n'}Redefined
          </Text>
          <PillButton
            label="Shop the drop  →"
            variant="volt"
            style={{ alignSelf: 'flex-start', minHeight: 0, paddingVertical: space.s12 }}
            textStyle={{ fontFamily: fonts.bodyBold, fontSize: 14 }}
            onPress={() => navigation.navigate('Tabs' as never, { screen: 'Shop' } as never)}
          />
        </View>

        {/* Category chip rail. */}
        <View style={{ paddingHorizontal: space.screenX, paddingTop: space.screenX, gap: space.s10 }}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <View style={{ flexDirection: 'row', gap: space.s8 }}>
              {[{ name: 'All', slug: '' }, ...categories].map((category) => {
                const active = activeCategory === category.slug;
                return (
                  <Pressable
                    key={category.slug || 'all'}
                    accessibilityRole="button"
                    accessibilityState={{ selected: active }}
                    accessibilityLabel={`Category ${category.name}`}
                    onPress={() => selectCategory(category.slug)}
                    style={{
                      paddingHorizontal: space.s14,
                      paddingVertical: space.s8,
                      borderRadius: radius.pill,
                      backgroundColor: active ? colors.ink : colors.paper,
                      borderWidth: active ? 0 : 1,
                      borderColor: colors.border,
                    }}
                  >
                    <Text
                      style={{
                        fontFamily: fonts.bodyMedium,
                        fontSize: 13,
                        color: active ? colors.paper : colors.ink,
                      }}
                    >
                      {category.name}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          </ScrollView>

          {/* Section heading row. */}
          <View
            style={{
              flexDirection: 'row',
              justifyContent: 'space-between',
              alignItems: 'center',
              paddingTop: space.s6,
            }}
          >
            <Text style={{ fontFamily: fonts.display, fontSize: 20, color: colors.ink }}>
              New Arrivals
            </Text>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="See all products"
              onPress={() => navigation.navigate('Tabs' as never, { screen: 'Shop' } as never)}
            >
              <Mono size={11} color={colors.muted}>
                See all →
              </Mono>
            </Pressable>
          </View>

          {/* 2-column grid of product cards. */}
          <FlatList
            data={products}
            scrollEnabled={false}
            numColumns={2}
            keyExtractor={(item) => String(item.id)}
            columnWrapperStyle={{ gap: space.s12 }}
            contentContainerStyle={{ gap: space.screenX }}
            renderItem={({ item }) => (
              <ProductCard
                product={item}
                wishlisted={wishlisted.has(item.id)}
                onToggleWishlist={() => toggleWishlist(item.id)}
                onPress={() => navigation.navigate('ProductDetail', { slug: item.slug })}
              />
            )}
            ListEmptyComponent={
              !offline ? (
                <MicroLabel style={{ paddingVertical: space.s24 }}>Loading the drop…</MicroLabel>
              ) : null
            }
          />
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

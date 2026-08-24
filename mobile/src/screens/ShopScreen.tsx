/**
 * M03 · Shop & Search (Tab) — Figma node 63:155.
 *
 * Pill search field on surface → filter chip rail ("Filter · N" ink pill +
 * removable ✕ chips) → results count + sort control → 2-column grid with
 * infinite scroll (server pages of ≤ 20, NFR-18) and pull-to-refresh.
 */

import { useNavigation, useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, FlatList, Pressable, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import AsyncStorage from '@react-native-async-storage/async-storage';

import { OfflineError } from '@/api/client';
import { account, catalog, type CatalogQuery } from '@/api/endpoints';
import type { ProductCard as ProductCardData } from '@/api/types';
import { ProductCard } from '@/components/ProductCard';
import { EmptyState, LoadingState, Mono, NavBar, OfflineBanner } from '@/components/primitives';
import type { RootStackParamList } from '@/navigation';
import { useAuth } from '@/store/AuthContext';
import { useTheme } from '@/theme/ThemeProvider';
import { radius, space } from '@/theme/theme';
import { fonts } from '@/theme/typography';

const SHOP_CACHE_KEY = 'metrodrip.shop.cache.v1';

const SORTS: { key: string; label: string }[] = [
  { key: 'newest', label: 'Newest' },
  { key: 'price_asc', label: 'Price ↑' },
  { key: 'price_desc', label: 'Price ↓' },
  { key: 'name_asc', label: 'A–Z' },
  { key: 'popularity', label: 'Popular' },
];

const SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL'];
const FITS = ['slim', 'regular', 'oversized'];

type Filters = { size?: string; fit?: string; color?: string; category?: string };

export default function ShopScreen() {
  const { colors } = useTheme();
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const route = useRoute();
  const { customer } = useAuth();

  const [query, setQuery] = useState('');
  const [filters, setFilters] = useState<Filters>(
    (route.params as { category?: string } | undefined)?.category
      ? { category: (route.params as { category: string }).category }
      : {},
  );
  const [sort, setSort] = useState(SORTS[0]);
  const [products, setProducts] = useState<ProductCardData[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [wishlisted, setWishlisted] = useState<Set<number>>(new Set());
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(
    async (reset: boolean, pageOverride?: number) => {
      const nextPage = reset ? 1 : (pageOverride ?? page + 1);
      const params: CatalogQuery = { ...filters, sort: sort.key, page: nextPage };
      if (query.trim()) params.q = query.trim();
      try {
        const data = await catalog.products(params);
        setOffline(false);
        setCount(data.count);
        setHasNext(data.next !== null);
        setPage(nextPage);
        setProducts((previous) => (reset ? data.results : [...previous, ...data.results]));
        if (reset) {
          AsyncStorage.setItem(
            SHOP_CACHE_KEY,
            JSON.stringify({ results: data.results, count: data.count }),
          ).catch(() => undefined);
        }
      } catch (err) {
        if (err instanceof OfflineError) {
          setOffline(true);
          if (reset && products.length === 0) {
            const cached = await AsyncStorage.getItem(SHOP_CACHE_KEY).catch(() => null);
            if (cached) {
              try {
                const parsed = JSON.parse(cached) as { results: ProductCardData[]; count: number };
                setProducts(parsed.results);
                setCount(parsed.count);
              } catch {
                /* ignore corrupt cache */
              }
            }
          }
        }
      } finally {
        setLoading(false);
      }
    },
    [filters, sort, query, page, products.length],
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Starts an asynchronous catalog refresh.
    load(true);
    if (customer) {
      account
        .wishlist()
        .then((data) => setWishlisted(new Set(data.results.map((entry) => entry.product.id))))
        .catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, sort]);

  const onSearchChange = (text: string) => {
    setQuery(text);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => load(true), 350);
  };

  const pick = (title: string, options: string[], key: keyof Filters) =>
    Alert.alert(title, undefined, [
      ...options.map((option) => ({
        text: option,
        onPress: () => setFilters((f) => ({ ...f, [key]: option })),
      })),
      { text: 'Clear', style: 'destructive' as const, onPress: () => removeFilter(key) },
    ]);

  const openFilterMenu = () =>
    Alert.alert('Filter', undefined, [
      { text: 'Size…', onPress: () => pick('Size', SIZES, 'size') },
      { text: 'Fit…', onPress: () => pick('Fit', FITS, 'fit') },
      { text: 'Cancel', style: 'cancel' },
    ]);

  const removeFilter = (key: keyof Filters) =>
    setFilters((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });

  const cycleSort = () =>
    Alert.alert(
      'Sort by',
      undefined,
      SORTS.map((candidate) => ({ text: candidate.label, onPress: () => setSort(candidate) })),
    );

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

  const activeChips = Object.entries(filters) as [keyof Filters, string][];

  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: colors.paper }}>
      <NavBar title="Shop" right={<Text style={{ fontSize: 18, color: colors.ink }}>⚙</Text>} />
      {offline ? <OfflineBanner onRetry={() => load(true)} /> : null}

      {loading && products.length === 0 ? (
        <LoadingState label="Loading shop…" />
      ) : (
      <FlatList
        data={products}
        numColumns={2}
        keyExtractor={(item) => String(item.id)}
        columnWrapperStyle={{ gap: space.s12, paddingHorizontal: space.screenX }}
        contentContainerStyle={{ gap: space.screenX, paddingBottom: space.screenX, flexGrow: 1 }}
        refreshing={refreshing}
        onRefresh={async () => {
          setRefreshing(true);
          await load(true);
          setRefreshing(false);
        }}
        onEndReachedThreshold={0.4}
        onEndReached={() => hasNext && load(false)}
        ListEmptyComponent={
          <EmptyState
            title={offline ? "You're offline" : 'No results'}
            body={
              offline
                ? 'Connect to the network to browse the full catalog.'
                : 'Try another search or clear filters.'
            }
          />
        }
        ListHeaderComponent={
          <View style={{ paddingHorizontal: space.screenX, paddingTop: space.s12, gap: space.s12 }}>
            {/* Pill search field. */}
            <View
              style={{
                minHeight: 44,
                borderRadius: radius.pill,
                backgroundColor: colors.surface,
                flexDirection: 'row',
                alignItems: 'center',
                paddingHorizontal: space.s14,
                gap: space.s8,
              }}
            >
              <Text style={{ fontSize: 16, color: colors.muted }}>⌕</Text>
              <TextInput
                value={query}
                onChangeText={onSearchChange}
                placeholder="Search products, SKU…"
                placeholderTextColor={colors.muted}
                accessibilityLabel="Search products"
                autoCapitalize="none"
                style={{ flex: 1, fontFamily: fonts.body, fontSize: 14, color: colors.ink, padding: 0 }}
              />
            </View>

            {/* Filter chip rail. */}
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.s8 }}>
              <Pressable
                onPress={openFilterMenu}
                accessibilityRole="button"
                accessibilityLabel="Open filters"
                style={{ backgroundColor: colors.ink, borderRadius: radius.pill, padding: space.s12 }}
              >
                <Text style={{ fontFamily: fonts.bodyMedium, fontSize: 12, color: colors.paper }}>
                  Filter{activeChips.length ? ` · ${activeChips.length}` : ''}
                </Text>
              </Pressable>
              {activeChips.map(([key, value]) => (
                <Pressable
                  key={key}
                  onPress={() => removeFilter(key)}
                  accessibilityRole="button"
                  accessibilityLabel={`Remove filter ${value}`}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    gap: space.s6,
                    borderWidth: 1,
                    borderColor: colors.border,
                    borderRadius: radius.pill,
                    padding: space.s12,
                    backgroundColor: colors.paper,
                  }}
                >
                  <Text style={{ fontFamily: fonts.bodyMedium, fontSize: 12, color: colors.ink }}>
                    {key === 'size' ? `Size: ${value}` : value.charAt(0).toUpperCase() + value.slice(1)}
                  </Text>
                  <Text style={{ fontSize: 10, color: colors.muted }}>✕</Text>
                </Pressable>
              ))}
            </View>

            {/* Results + sort. */}
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <Mono size={11} color={colors.muted}>
                {count} result{count === 1 ? '' : 's'}
              </Mono>
              <Pressable
      onPress={cycleSort}
      hitSlop={15}
      accessibilityRole="button"
      accessibilityLabel={`Sort, ${sort.label}`}
    >
                <Text style={{ fontFamily: fonts.bodyMedium, fontSize: 12, color: colors.ink }}>
                  {sort.label} ⌄
                </Text>
              </Pressable>
            </View>
          </View>
        }
        renderItem={({ item }) => (
          <ProductCard
            product={item}
            wishlisted={wishlisted.has(item.id)}
            onToggleWishlist={() => toggleWishlist(item.id)}
            onPress={() => navigation.navigate('ProductDetail', { slug: item.slug })}
          />
        )}
      />
      )}
    </SafeAreaView>
  );
}

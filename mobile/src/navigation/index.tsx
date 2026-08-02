/**
 * Navigation (§1): bottom tabs — Home · Shop · Saved · Orders · Account —
 * with the 5pt volt active dot beneath the label, plus the root stack for
 * detail/cart/checkout/tracking/auth flows.
 */

import { NavigationContainer, DefaultTheme, createNavigationContainerRef } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import React, { useCallback } from 'react';
import { Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { usePushRegistration } from '@/hooks/usePushRegistration';
import { useAuth } from '@/store/AuthContext';
import { useTheme } from '@/theme/ThemeProvider';
import { metrics, radius } from '@/theme/theme';
import { fonts } from '@/theme/typography';

import AccountScreen from '@/screens/AccountScreen';
import AuthScreen from '@/screens/AuthScreen';
import CartScreen from '@/screens/CartScreen';
import CheckoutScreen from '@/screens/CheckoutScreen';
import HomeScreen from '@/screens/HomeScreen';
import NotificationsScreen from '@/screens/NotificationsScreen';
import OrderTrackingScreen from '@/screens/OrderTrackingScreen';
import ProductDetailScreen from '@/screens/ProductDetailScreen';
import ShopScreen from '@/screens/ShopScreen';
import SplashScreen from '@/screens/SplashScreen';
import WishlistScreen from '@/screens/WishlistScreen';

export type RootStackParamList = {
  Splash: undefined;
  Tabs: undefined;
  ProductDetail: { slug: string };
  Cart: undefined;
  Checkout: undefined;
  OrderTracking: { token: string };
  Auth: { mode?: 'signin' | 'register' } | undefined;
};

export type TabParamList = {
  Home: undefined;
  Shop: { category?: string } | undefined;
  Saved: undefined;
  Orders: undefined;
  Account: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tabs = createBottomTabNavigator<TabParamList>();

/** Lets the push handler navigate from outside the component tree. */
export const navigationRef = createNavigationContainerRef<RootStackParamList>();

// Glyphs exactly as drawn in the Figma tab bar (M02 node 63:138).
const TAB_GLYPHS: Record<keyof TabParamList, string> = {
  Home: '⌂',
  Shop: '⌕',
  Saved: '♡',
  Orders: '▤',
  Account: '◉',
};

function TabIcon({ name, focused }: { name: keyof TabParamList; focused: boolean }) {
  const { colors } = useTheme();
  return (
    <Text style={{ fontSize: 20, color: focused ? colors.ink : colors.muted }}>
      {TAB_GLYPHS[name]}
    </Text>
  );
}

function TabLabel({ name, focused }: { name: keyof TabParamList; focused: boolean }) {
  const { colors } = useTheme();
  return (
    <View style={{ alignItems: 'center' }}>
      <Text
        style={{
          fontFamily: focused ? fonts.bodySemiBold : fonts.body,
          fontSize: 10,
          color: focused ? colors.ink : colors.muted,
        }}
      >
        {name}
      </Text>
      {/* §1: the volt active dot is part of the design — 5pt beneath the label. */}
      <View
        style={{
          width: 5,
          height: 5,
          borderRadius: radius.pill,
          marginTop: 3,
          backgroundColor: focused ? colors.volt : 'transparent',
        }}
      />
    </View>
  );
}

function MainTabs() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <Tabs.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarIcon: ({ focused }) => <TabIcon name={route.name} focused={focused} />,
        tabBarLabel: ({ focused }) => <TabLabel name={route.name} focused={focused} />,
        tabBarStyle: {
          height: metrics.tabBarHeight + Math.max(insets.bottom - 10, 0),
          backgroundColor: colors.paper,
          borderTopWidth: 1,
          borderTopColor: colors.border,
          paddingTop: 8,
        },
      })}
    >
      <Tabs.Screen name="Home" component={HomeScreen} />
      <Tabs.Screen name="Shop" component={ShopScreen} />
      <Tabs.Screen name="Saved" component={WishlistScreen} />
      <Tabs.Screen name="Orders" component={NotificationsScreen} />
      <Tabs.Screen name="Account" component={AccountScreen} />
    </Tabs.Navigator>
  );
}

export function AppNavigator() {
  const { colors, scheme } = useTheme();
  const { restoring, customer } = useAuth();

  // FR-27/FR-28: register this device and deep-link a tapped push to its order.
  const openOrder = useCallback((statusToken: string) => {
    if (navigationRef.isReady()) {
      navigationRef.navigate('OrderTracking', { token: statusToken });
    }
  }, []);
  usePushRegistration(!!customer, openOrder);

  const navTheme = {
    ...DefaultTheme,
    dark: scheme === 'dark',
    colors: {
      ...DefaultTheme.colors,
      background: colors.paper,
      card: colors.paper,
      text: colors.ink,
      border: colors.border,
      primary: colors.ink,
      notification: colors.danger,
    },
  };

  return (
    <NavigationContainer ref={navigationRef} theme={navTheme}>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        {restoring ? (
          <Stack.Screen name="Splash" component={SplashScreen} />
        ) : (
          <>
            <Stack.Screen name="Splash" component={SplashScreen} />
            <Stack.Screen name="Tabs" component={MainTabs} />
            <Stack.Screen name="ProductDetail" component={ProductDetailScreen} />
            <Stack.Screen name="Cart" component={CartScreen} />
            <Stack.Screen
              name="Checkout"
              component={CheckoutScreen}
              options={{ presentation: 'modal' }}
            />
            <Stack.Screen name="OrderTracking" component={OrderTrackingScreen} />
            <Stack.Screen name="Auth" component={AuthScreen} options={{ presentation: 'modal' }} />
          </>
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}

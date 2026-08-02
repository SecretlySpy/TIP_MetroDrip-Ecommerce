/**
 * H-10: device registration + foreground push handling (FR-27/FR-28).
 *
 * Registers the Expo push token against the signed-in customer so order
 * transitions reach this device, and routes a tapped notification to the
 * order it belongs to. Permission denial is a no-op — push is enhancement
 * tier and must never block using the app.
 */

import * as Notifications from 'expo-notifications';
import { useEffect, useRef } from 'react';
import { Platform } from 'react-native';

import { notifications as notificationsApi, orders } from '@/api/endpoints';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: false,
    shouldSetBadge: true,
  }),
});

export function usePushRegistration(
  signedIn: boolean,
  onOpenOrder: (statusToken: string) => void,
) {
  const registered = useRef(false);

  useEffect(() => {
    if (!signedIn || registered.current) return;
    (async () => {
      try {
        const existing = await Notifications.getPermissionsAsync();
        const granted =
          existing.granted ||
          (await Notifications.requestPermissionsAsync()).granted;
        if (!granted) return;

        if (Platform.OS === 'android') {
          await Notifications.setNotificationChannelAsync('default', {
            name: 'Order updates',
            importance: Notifications.AndroidImportance.DEFAULT,
          });
        }

        const token = (await Notifications.getExpoPushTokenAsync()).data;
        await notificationsApi.registerDevice(token, Platform.OS === 'ios' ? 'ios' : 'android');
        registered.current = true;
      } catch {
        // Simulators and permission-less installs simply get no push.
      }
    })();
  }, [signedIn]);

  useEffect(() => {
    const subscription = Notifications.addNotificationResponseReceivedListener(async (response) => {
      const orderNo = response.notification.request.content.data?.order_no;
      if (typeof orderNo !== 'string') return;
      const order = await orders.detail(orderNo).catch(() => null);
      if (order) onOpenOrder(order.status_token);
    });
    return () => subscription.remove();
  }, [onOpenOrder]);
}

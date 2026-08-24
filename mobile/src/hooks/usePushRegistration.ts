/**
 * H-10: device registration + push handling (FR-27/FR-28).
 *
 * Registers the Expo push token against the signed-in customer so order
 * transitions reach this device, and routes a tapped notification to the
 * order it belongs to. Permission denial is a no-op — push is enhancement
 * tier and must never block using the app.
 */

import Constants from 'expo-constants';
import * as Notifications from 'expo-notifications';
import { useEffect, useRef } from 'react';
import { Platform } from 'react-native';

import { notifications as notificationsApi, orders } from '@/api/endpoints';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: false,
    shouldSetBadge: true,
  }),
});

async function openOrderFromData(
  data: Record<string, unknown> | undefined,
  onOpenOrder: (statusToken: string) => void,
): Promise<boolean> {
  const orderNo = data?.order_no;
  if (typeof orderNo !== 'string') return false;
  const order = await orders.detail(orderNo).catch(() => null);
  if (!order) return false;
  onOpenOrder(order.status_token);
  return true;
}

export function usePushRegistration(
  signedIn: boolean,
  onOpenOrder: (statusToken: string) => void,
  onForegroundPush?: () => void,
) {
  const registered = useRef(false);

  useEffect(() => {
    if (!signedIn) {
      registered.current = false;
      return;
    }
    if (registered.current) return;

    (async () => {
      try {
        // Android needs its channel before the permission prompt; creating it
        // afterwards can leave the first notification without a valid target.
        if (Platform.OS === 'android') {
          await Notifications.setNotificationChannelAsync('default', {
            name: 'Order updates',
            importance: Notifications.AndroidImportance.DEFAULT,
          });
        }

        const existing = await Notifications.getPermissionsAsync();
        const granted =
          existing.granted || (await Notifications.requestPermissionsAsync()).granted;
        if (!granted) return;

        const projectId =
          Constants.expoConfig?.extra?.eas?.projectId ??
          Constants.easConfig?.projectId;
        if (!projectId) {
          console.warn(
            'Push registration is disabled: configure an EAS project ID before requesting an Expo push token.',
          );
          return;
        }
        const token = (
          await Notifications.getExpoPushTokenAsync({ projectId: String(projectId) })
        ).data;
        await notificationsApi.registerDevice(token, Platform.OS === 'ios' ? 'ios' : 'android');
        registered.current = true;
      } catch (error) {
        // Push is enhancement-tier. Surface a diagnostic without logging a
        // token or customer data, while leaving the rest of the app usable.
        console.warn(
          'Push registration is unavailable on this installation.',
          error instanceof Error ? error.message : 'Unknown error',
        );
      }
    })();
  }, [signedIn]);

  useEffect(() => {
    const consumeResponse = async (response: Notifications.NotificationResponse) => {
      if (!signedIn) return;
      const opened = await openOrderFromData(
        response.notification.request.content.data as Record<string, unknown> | undefined,
        onOpenOrder,
      );
      if (opened) Notifications.clearLastNotificationResponse();
    };

    const responseSub = Notifications.addNotificationResponseReceivedListener((response) => {
      consumeResponse(response).catch(() => undefined);
    });

    const receivedSub = Notifications.addNotificationReceivedListener(() => {
      onForegroundPush?.();
    });

    // Keep a cold-start response until authentication, order lookup, and the
    // navigation handoff all succeed. An offline lookup can then be retried on
    // a later mount instead of losing the user's tap permanently.
    try {
      const response = Notifications.getLastNotificationResponse();
      if (response && signedIn) consumeResponse(response).catch(() => undefined);
    } catch {
      // The synchronous API may be unavailable in non-native test runtimes.
    }

    return () => {
      responseSub.remove();
      receivedSub.remove();
    };
  }, [signedIn, onOpenOrder, onForegroundPush]);
}

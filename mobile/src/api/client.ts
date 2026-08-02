/**
 * Mobile API client (§6): token-authenticated, versioned, offline-aware.
 *
 * NFR-19: the access/refresh pair lives ONLY in expo-secure-store
 * (Keychain / Keystore) — never AsyncStorage. No PII is ever logged.
 *
 * D-13: this module transports intent and renders server truth. It never
 * computes prices, decides stock, or transitions order state.
 */

import * as SecureStore from 'expo-secure-store';

export const API_BASE_URL =
  process.env.EXPO_PUBLIC_API_URL ?? 'http://10.0.2.2:8080/api/mobile/v1';

export const CLIENT_VERSION = '1.0.0';

const ACCESS_KEY = 'metrodrip.access';
const REFRESH_KEY = 'metrodrip.refresh';

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public fields?: Record<string, string[]>,
  ) {
    super(message);
  }
}

export class OfflineError extends Error {
  constructor() {
    super('You appear to be offline.');
  }
}

export async function saveTokens(access: string, refresh: string): Promise<void> {
  await SecureStore.setItemAsync(ACCESS_KEY, access);
  await SecureStore.setItemAsync(REFRESH_KEY, refresh);
}

export async function clearTokens(): Promise<void> {
  await SecureStore.deleteItemAsync(ACCESS_KEY);
  await SecureStore.deleteItemAsync(REFRESH_KEY);
}

export async function getRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(REFRESH_KEY);
}

export async function hasStoredSession(): Promise<boolean> {
  return (await SecureStore.getItemAsync(REFRESH_KEY)) !== null;
}

async function refreshAccessToken(): Promise<string | null> {
  const refresh = await SecureStore.getItemAsync(REFRESH_KEY);
  if (!refresh) return null;
  const response = await fetch(`${API_BASE_URL}/auth/refresh/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Client-Version': CLIENT_VERSION },
    body: JSON.stringify({ refresh }),
  });
  if (!response.ok) {
    await clearTokens(); // the pair is dead; force a fresh sign-in
    return null;
  }
  const data = await response.json();
  await saveTokens(data.access, data.refresh ?? refresh);
  return data.access as string;
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  /** Attach the bearer token (default true; public endpoints pass false). */
  auth?: boolean;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, auth = true } = options;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    // NFR-22: every mobile request self-identifies its app version.
    'X-Client-Version': CLIENT_VERSION,
  };
  if (auth) {
    const access = await SecureStore.getItemAsync(ACCESS_KEY);
    if (access) headers.Authorization = `Bearer ${access}`;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    // FR-30: network failures surface as an explicit, retryable state.
    throw new OfflineError();
  }

  // One transparent refresh on an expired access token, then replay.
  if (response.status === 401 && auth) {
    const newAccess = await refreshAccessToken();
    if (newAccess) {
      headers.Authorization = `Bearer ${newAccess}`;
      try {
        response = await fetch(`${API_BASE_URL}${path}`, {
          method,
          headers,
          body: body === undefined ? undefined : JSON.stringify(body),
        });
      } catch {
        throw new OfflineError();
      }
    }
  }

  if (response.status === 204 || response.status === 205) return undefined as T;

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = data?.error ?? {};
    throw new ApiError(
      response.status,
      error.code ?? 'error',
      error.message ?? 'Something went wrong.',
      error.fields,
    );
  }
  return data as T;
}

/** Typed wrappers for every /api/mobile/v1/ route the 11 screens use. */

import { request } from './client';
import type {
  AppNotification,
  AuthPayload,
  CartValidation,
  CategoryRef,
  CheckoutResult,
  Customer,
  OrderPayload,
  Paginated,
  ProductCard,
  ProductDetail,
  WishlistEntry,
  Zone,
} from './types';

// --- Auth (H-3) ---

export const auth = {
  register: (body: { email: string; password: string; name: string; phone?: string }) =>
    request<AuthPayload>('/auth/register/', { method: 'POST', body, auth: false }),
  login: (body: { email: string; password: string }) =>
    request<AuthPayload>('/auth/login/', { method: 'POST', body, auth: false }),
  logout: (refresh: string) =>
    request<void>('/auth/logout/', { method: 'POST', body: { refresh } }),
  requestPasswordReset: (email: string) =>
    request<void>('/auth/password-reset/', { method: 'POST', body: { email }, auth: false }),
};

// --- Catalog (H-2) ---

export interface CatalogQuery {
  q?: string;
  category?: string;
  size?: string;
  color?: string;
  fit?: string;
  price_min?: string;
  price_max?: string;
  sort?: string;
  page?: number;
}

export const catalog = {
  products: (query: CatalogQuery = {}) => {
    const params = new URLSearchParams();
    Object.entries(query).forEach(([key, value]) => {
      if (value !== undefined && value !== '') params.append(key, String(value));
    });
    const suffix = params.toString() ? `?${params.toString()}` : '';
    return request<Paginated<ProductCard>>(`/catalog/products/${suffix}`, { auth: false });
  },
  productDetail: (slug: string) =>
    request<ProductDetail>(`/catalog/products/${slug}/`, { auth: false }),
  categories: () =>
    request<{ results: (CategoryRef & { product_count: number })[] }>('/catalog/categories/', {
      auth: false,
    }),
};

// --- Cart + checkout (H-4) ---

export interface CheckoutContact {
  customer_name: string;
  email: string;
  phone: string;
  address_line1: string;
  city: string;
  zone_id: number;
}

export const commerce = {
  validateCart: (items: { variant_id: number; qty: number }[]) =>
    request<CartValidation>('/cart/validate/', { method: 'POST', body: { items }, auth: false }),
  zones: () => request<{ results: Zone[] }>('/shipping/zones/', { auth: false }),
  checkout: (contact: CheckoutContact, items: { variant_id: number; qty: number }[]) =>
    request<CheckoutResult>('/checkout/', { method: 'POST', body: { ...contact, items } }),
  confirmSimulated: (statusToken: string) =>
    request<{ order_no: string; status: string }>('/checkout/confirm-simulated/', {
      method: 'POST',
      body: { status_token: statusToken },
      auth: false,
    }),
};

// --- Orders (H-5) ---

export const orders = {
  history: () => request<{ results: OrderPayload[] }>('/orders/'),
  detail: (orderNo: string) => request<OrderPayload>(`/orders/${orderNo}/`),
  track: (token: string) =>
    request<OrderPayload>(`/orders/track/${encodeURIComponent(token)}/`, { auth: false }),
};

// --- Account, wishlist, reviews (H-6) ---

export const account = {
  profile: () => request<Customer>('/account/profile/'),
  updateProfile: (body: { name?: string; phone?: string }) =>
    request<Customer>('/account/profile/', { method: 'PATCH', body }),
  wishlist: () => request<{ results: WishlistEntry[] }>('/wishlist/'),
  toggleWishlist: (productId: number) =>
    request<{ added: boolean }>('/wishlist/', { method: 'POST', body: { product_id: productId } }),
  submitReview: (body: { order_no: string; product_id: number; rating: number; body: string }) =>
    request<{ status: string }>('/reviews/', { method: 'POST', body }),
};

// --- Devices + notification centre (H-10) ---

export const notifications = {
  registerDevice: (token: string, platform: 'ios' | 'android') =>
    request<void>('/notifications/devices/', { method: 'POST', body: { token, platform } }),
  list: () => request<Paginated<AppNotification> & { unread_count: number }>('/notifications/'),
  markRead: (id: number) => request<void>(`/notifications/${id}/read/`, { method: 'POST' }),
  markAllRead: () => request<void>('/notifications/read-all/', { method: 'POST' }),
};

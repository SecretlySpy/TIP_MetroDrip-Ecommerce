/**
 * Server payload shapes (mirror apps/mobile_api). Money fields are integer
 * centavos PLUS a server-formatted `*_display` string — the app renders the
 * display value and never does arithmetic on the integer (D-13).
 */

export interface Customer {
  id: number;
  email: string;
  name: string;
  phone: string;
  addresses: unknown[];
}

export interface AuthPayload {
  access: string;
  refresh: string;
  customer: Customer;
}

export interface CategoryRef {
  name: string;
  slug: string;
}

export interface ProductCard {
  id: number;
  name: string;
  slug: string;
  category: CategoryRef;
  price: number;
  price_display: string;
  images: string[];
  review_avg: number | null;
  review_count: number;
}

export interface Variant {
  id: number;
  sku: string;
  size: string;
  color: string;
  fit: string;
  price: number;
  price_display: string;
  available: number;
}

export interface ReviewEntry {
  author: string;
  rating: number;
  body: string;
  created_at: string;
}

export interface ProductDetail extends ProductCard {
  description: string;
  reviews: ReviewEntry[];
  variants: Variant[];
  is_wishlisted: boolean;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Zone {
  id: number;
  name: string;
  fee: number;
  fee_display: string;
}

export interface CartLineValidation {
  variant_id: number;
  removed?: boolean;
  sku?: string;
  product_name?: string;
  qty?: number;
  available?: number;
  unit_price?: number;
  unit_price_display?: string;
  line_total?: number;
  line_total_display?: string;
}

export interface CartValidation {
  lines: CartLineValidation[];
  subtotal: number;
  subtotal_display: string;
  all_available: boolean;
}

export interface CheckoutResult {
  order_no: string;
  status_token: string;
  checkout_url: string;
  payment_provider: string;
  total: number;
  total_display: string;
}

export interface TimelineStep {
  key: string;
  label: string;
  state: 'done' | 'current' | 'todo';
}

export interface OrderItemLine {
  product_name: string;
  product_slug: string;
  sku: string;
  size: string;
  color: string;
  fit: string;
  qty: number;
  unit_price: number;
  unit_price_display: string;
}

export interface OrderPayload {
  order_no: string;
  status: string;
  status_display: string;
  created_at: string;
  subtotal_display: string;
  shipping_fee_display: string;
  total_display: string;
  shipping_address: Record<string, string>;
  status_token: string;
  timeline: TimelineStep[] | null;
  item_count: number;
  shipment: {
    courier: string;
    waybill_no: string;
    tracking_url: string;
    status: string;
  } | null;
  items?: OrderItemLine[];
}

export interface WishlistEntry {
  product: ProductCard;
  in_stock: boolean;
  saved_at: string;
}

export interface AppNotification {
  id: number;
  title: string;
  body: string;
  category: 'order' | 'drop' | 'stock' | 'review';
  order_no: string | null;
  is_read: boolean;
  created_at: string;
}

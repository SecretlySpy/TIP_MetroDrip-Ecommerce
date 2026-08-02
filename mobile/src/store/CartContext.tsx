/**
 * Client-side cart (FR-25, ADR-C-001 mobile twin).
 *
 * Stores variant references + display strings for OFFLINE RENDERING ONLY.
 * Line totals shown before checkout are server-provided display values from
 * /cart/validate/; the app performs no price arithmetic (D-13). Quantities
 * are intent, validated server-side at checkout.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

const CART_KEY = 'metrodrip.cart';
const MAX_LINE_QTY = 99;

export interface CartLine {
  variantId: number;
  sku: string;
  productName: string;
  productSlug: string;
  size: string;
  color: string;
  fit: string;
  /** Server-formatted unit price for offline display; server re-prices at checkout. */
  priceDisplay: string;
  qty: number;
}

interface CartContextValue {
  lines: CartLine[];
  itemCount: number;
  add: (line: Omit<CartLine, 'qty'>, qty: number) => void;
  updateQty: (variantId: number, delta: number) => void;
  remove: (variantId: number) => void;
  clear: () => void;
}

const CartContext = createContext<CartContextValue | null>(null);

export function CartProvider({ children }: { children: React.ReactNode }) {
  const [lines, setLines] = useState<CartLine[]>([]);

  useEffect(() => {
    AsyncStorage.getItem(CART_KEY).then((stored) => {
      if (!stored) return;
      try {
        setLines(JSON.parse(stored));
      } catch {
        setLines([]);
      }
    });
  }, []);

  const persist = (next: CartLine[]) => {
    setLines(next);
    AsyncStorage.setItem(CART_KEY, JSON.stringify(next)).catch(() => undefined);
  };

  const value = useMemo<CartContextValue>(
    () => ({
      lines,
      itemCount: lines.reduce((sum, line) => sum + line.qty, 0),
      add(line, qty) {
        const existing = lines.find((l) => l.variantId === line.variantId);
        if (existing) {
          persist(
            lines.map((l) =>
              l.variantId === line.variantId
                ? { ...l, qty: Math.min(l.qty + qty, MAX_LINE_QTY) }
                : l,
            ),
          );
        } else {
          persist([...lines, { ...line, qty: Math.min(qty, MAX_LINE_QTY) }]);
        }
      },
      updateQty(variantId, delta) {
        const next = lines
          .map((l) =>
            l.variantId === variantId
              ? { ...l, qty: Math.min(Math.max(l.qty + delta, 0), MAX_LINE_QTY) }
              : l,
          )
          .filter((l) => l.qty > 0);
        persist(next);
      },
      remove(variantId) {
        persist(lines.filter((l) => l.variantId !== variantId));
      },
      clear() {
        persist([]);
      },
    }),
    [lines],
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart(): CartContextValue {
  const context = useContext(CartContext);
  if (!context) throw new Error('useCart must be used inside CartProvider');
  return context;
}

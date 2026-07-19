/**
 * MetroDrip Cart Module (C-4, FR-3).
 *
 * Client-side localStorage cart. Stock reservation happens at checkout start
 * (Epic D), not when adding to cart. The cart stores last-known pricing and
 * variant details; real stock validation happens only at checkout.
 *
 * Cart data structure (in localStorage key 'metrodrip_cart'):
 * [
 *   {
 *     variantId: number,
 *     sku: string,
 *     productName: string,
 *     size: string,
 *     color: string,
 *     fit: string,
 *     price: number,        // centavos
 *     priceDisplay: string,  // formatted "₱899.00"
 *     qty: number,
 *   },
 *   ...
 * ]
 */

/**
 * Alpine.js cart page component.
 * Reads from localStorage, renders the full cart UI, and provides
 * add/remove/update operations.
 */
function cartPage() {
  return {
    items: [],
    loading: true,

    init() {
      this.loadCart();
      this.loading = false;
      // Listen for updates from other tabs or components.
      window.addEventListener('cart-updated', () => this.loadCart());
      window.addEventListener('storage', (e) => {
        if (e.key === 'metrodrip_cart') this.loadCart();
      });
    },

    loadCart() {
      try {
        this.items = JSON.parse(localStorage.getItem('metrodrip_cart') || '[]');
      } catch {
        this.items = [];
      }
    },

    saveCart() {
      localStorage.setItem('metrodrip_cart', JSON.stringify(this.items));
      window.dispatchEvent(new CustomEvent('cart-updated'));
    },

    removeItem(variantId) {
      this.items = this.items.filter(item => item.variantId !== variantId);
      this.saveCart();
    },

    updateQty(variantId, delta) {
      const item = this.items.find(i => i.variantId === variantId);
      if (!item) return;
      const newQty = item.qty + delta;
      if (newQty < 1) {
        this.removeItem(variantId);
      } else {
        item.qty = newQty;
        this.saveCart();
      }
    },

    clearCart() {
      this.items = [];
      this.saveCart();
    },

    get itemCount() {
      return this.items.reduce((sum, item) => sum + item.qty, 0);
    },

    /** Calculate line total in centavos. */
    lineTotal(item) {
      return item.price * item.qty;
    },

    /** Format centavos to peso display string. */
    formatPeso(centavos) {
      const major = Math.floor(centavos / 100);
      const minor = centavos % 100;
      return '₱' + major.toLocaleString() + '.' + String(minor).padStart(2, '0');
    },

    get subtotal() {
      return this.items.reduce((sum, item) => sum + this.lineTotal(item), 0);
    },

    get subtotalDisplay() {
      return this.formatPeso(this.subtotal);
    },
  };
}

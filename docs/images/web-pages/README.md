# MetroDrip web page screenshot inventory

This directory contains the desktop web-page capture set created on
2026-09-06. Title-case filenames are deliberate: each PNG reads as a page label
when shared outside the repository.

## Storefront and customer account — 17 files

| File | Visible page/state |
|---|---|
| `Home Page.png` | Public storefront home and featured catalog |
| `Shop Page.png` | Searchable and filterable product listing |
| `Product Detail Page.png` | Product details and variant picker |
| `Cart Page.png` | Populated browser cart and order summary |
| `Checkout Page.png` | Populated delivery form and checkout summary |
| `Order Confirmed Page.png` | Successful simulated order confirmation |
| `Order Tracking Page.png` | Delivered order status, timeline, shipping, and items |
| `Customer Invoice Page.png` | Customer-facing printable invoice |
| `Contact Page.png` | Public contact-support form |
| `Developers Page.png` | Public development-team page |
| `About Page.png` | About MetroDrip flat page |
| `FAQ Page.png` | Frequently Asked Questions flat page |
| `Privacy Policy Page.png` | Privacy Policy flat page |
| `Log In Page.png` | Customer login form with empty credentials |
| `Register Page.png` | Customer registration form with empty credentials |
| `My Account Page.png` | Authenticated customer profile, recent orders, and wishlist |
| `Order History Page.png` | Authenticated customer order history |

## Development-only page — 1 file

| File | Visible page/state |
|---|---|
| `Staging Seed Preview Page.png` | Complete preview of the development mock-catalog fixture with the staging gate temporarily enabled |

## Merchant console — 28 files

| File | Visible page/state |
|---|---|
| `Merchant Login Page.png` | Merchant-specific login form with empty credentials |
| `Merchant Dashboard Page.png` | Store-management KPIs and low-stock table |
| `Merchant Categories Page.png` | Category list |
| `Merchant Category Detail Page.png` | Category edit page |
| `Merchant Products Page.png` | Product list |
| `Merchant Product Detail Page.png` | Product and variant-matrix edit page |
| `Merchant Inventory Page.png` | Stock-record list |
| `Merchant Inventory Detail Page.png` | Stock-record edit page |
| `Merchant Stock Movements Page.png` | Append-only stock-movement list |
| `Merchant Stock Movement Detail Page.png` | Read-only stock-movement detail |
| `Merchant Reservations Page.png` | Inventory-reservation list |
| `Merchant Reservation Detail Page.png` | Read-only reservation detail |
| `Merchant Orders Page.png` | Fulfilment order list |
| `Merchant Order Detail Page.png` | Read-only order data and fulfilment actions |
| `Merchant Sales Report Page.png` | Sales and status analytics report |
| `Merchant Invoice Page.png` | Merchant printable invoice |
| `Merchant Packing Slip Page.png` | Warehouse packing slip without prices |
| `Merchant Payments Page.png` | Payment list |
| `Merchant Payment Detail Page.png` | Read-only payment detail |
| `Merchant Shipments Page.png` | Shipment list |
| `Merchant Shipment Detail Page.png` | Shipment edit page |
| `Merchant Reviews Page.png` | Review moderation list/empty state |
| `Merchant Homepage Banners Page.png` | Homepage-banner list |
| `Merchant Homepage Banner Detail Page.png` | Homepage-banner edit page |
| `Merchant Contact Messages Page.png` | Contact-message list/empty state |
| `Merchant Flat Pages Page.png` | Store-content flat-page list |
| `Merchant Flat Page Detail Page.png` | Flat-page edit page |
| `Merchant Wrong Console Page.png` | Administrator refused by the merchant console with recovery actions |

## Administrator console — 19 files

| File | Visible page/state |
|---|---|
| `Administrator Login Page.png` | Administrator-specific login form with empty credentials |
| `Administrator Dashboard Page.png` | Platform KPIs, audit summary, and governance modules |
| `Administrator Groups Page.png` | Permission-group list |
| `Administrator Group Detail Page.png` | Permission-group edit page |
| `Administrator Sites Page.png` | Django sites list |
| `Administrator Site Detail Page.png` | Site edit page |
| `Administrator TOTP Devices Page.png` | Time-based one-time-password device empty state |
| `Administrator Static Devices Page.png` | Static backup-token device empty state |
| `Administrator Shipping Zones Page.png` | Shipping-zone list |
| `Administrator Shipping Zone Detail Page.png` | Shipping-zone edit page |
| `Administrator Customers Page.png` | Customer and staff account list |
| `Administrator Customer Detail Page.png` | Fictional customer account detail with masked password metadata |
| `Administrator Wishlist Items Page.png` | Wishlist-item list |
| `Administrator Wishlist Item Detail Page.png` | Read-only wishlist-item detail |
| `Administrator Audit Trail Page.png` | Append-only audit-log empty state |
| `Administrator Outstanding Tokens Page.png` | Outstanding-token list |
| `Administrator Outstanding Token Detail Page.png` | Detail page backed by an explicit non-credential placeholder token |
| `Administrator Blacklisted Tokens Page.png` | Blacklisted-token empty state |
| `Administrator Wrong Console Page.png` | Merchant refused by the administrator console with recovery actions |

## Page-template and shared-component coverage audit

All 32 repository-owned HTML templates are rendered by at least one capture.
The matrix below groups shared partials with representative pages; the 65-file
inventory above supplies the individual route and data-state coverage.

| Template/component family | Representative captures |
|---|---|
| Storefront shell, navigation, footer, category menu, product grid, and product cards | Home, Shop, Product Detail |
| Cart, checkout, confirmation, tracking, and customer invoice | Corresponding storefront page captures |
| Customer authentication, profile, wishlist summary, and order history | Log In, Register, My Account, Order History |
| Contact, developers, and reusable flat-page template | Contact, Developers, About, FAQ, Privacy Policy |
| Staging fixture preview | Staging Seed Preview |
| Console login shell and role-boundary refusal template | Both console Login and Wrong Console pairs |
| Console sidebar, topbar, theme picker, action chip, and KPI card | Both dashboards and every authenticated console page |
| Django changelist, filters, actions, pagination, and empty states | Every registered module list page |
| Django change form, read-only fields, inline matrix, and submit controls | Representative detail page for every registered module |
| Merchant sales report, invoice, and packing slip | Corresponding merchant document captures |

Transient messages and destructive confirmation dialogs reuse the captured
console shell and Django form primitives; they are interaction states, not
separate navigable pages. API responses, HTMX fragments, health checks,
webhooks, logout handlers, and POST-only mutations likewise do not render page
templates and are not screenshot entries.

## Capture provenance and boundaries

- **Browser:** Google Chrome 152.0.7977.82 in headless mode at a fixed
  **1600×1000** desktop viewport, light color scheme, and reduced motion. Each
  PNG uses Chrome's full-document content bounds rather than a viewport-only
  frame. Nested console scrollers are expanded into normal flow for capture,
  so output widths range from **1600 to 1841 pixels** and heights range from
  **1000 to 76373 pixels**.
- **Application:** live local Django development server and database-backed
  pages; simulated payment and shipping providers; no production services.
- **Data:** fictional `.test` accounts and addresses. Authenticated storefront
  pages and the three customer order pages use simulated order
  `MD-2026-00009`. Cart and checkout use its in-stock product variant.
- **Console security:** dedicated fictional merchant and administrator sessions
  exercised the two server-side role boundaries. The outstanding-token detail
  uses the visible string `NOT-A-REAL-BEARER-TOKEN`; no working bearer token,
  session cookie, password, one-time password, secret, or environment value is
  present in any frame.
- **Coverage boundary:** includes every public HTML storefront/account route,
  all three flat pages, the development staging-seed preview, both console
  login/dashboard/access-denied pages, every registered console module list
  page, populated representative detail pages, and all custom order
  documents/reports. API, webhook, readiness/liveness, logout, POST-only
  mutation, and HTMX fragment endpoints are not webpages and are excluded. The
  staging gate was enabled only for its isolated capture and returned to its
  disabled-by-default state afterward.
- **Verification:** each navigation was checked for an expected page heading
  before capture. All 65 PNG files were decoded and checked against Chrome's
  complete content bounds. Fifty-two files exceed the 1000-pixel viewport
  height after public-page and nested-console overflow is included. The
  storefront, staging, merchant, and administrator groups were visually
  reviewed without resizing or cropping the source files.

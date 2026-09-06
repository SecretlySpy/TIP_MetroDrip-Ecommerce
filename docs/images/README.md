# Guide image manifest and provenance

These assets support the beginner-facing GitHub Pages guide in root
`index.html`. Screenshots are additional evidence; they do not replace any
diagram.

Five pre-existing diagrams must remain:

- four accessible inline SVGs in `index.html`: local architecture,
  host/toolchain decision, app-to-API address map, and four-process run order;
- `09-troubleshooting-flowchart.png`.

The legacy `01-` through `08-` PNGs are retained for history but are no longer
the guide's current evidence. Do not delete or retouch them. The current guide
uses the step-based manifest below plus the troubleshooting diagram.

## Current step-based manifest

| Step | File | Visible success signal | Capture class |
|---:|---|---|---|
| 1 | `step-01-tools-verified.png` | Required Git, Python, uv, Docker/Compose, Node, npm, and Java versions | Linux terminal |
| 2 | `step-02-code-cloned.png` | Repository entered and expected top-level files visible | Linux terminal |
| 3 | `step-03-python-ready.png` | Python 3.14 virtual environment and dependencies ready | Linux terminal |
| 4 | `step-04-env-created-and-ignored.png` | `.env` exists and Git ignores it; no values shown | Linux terminal |
| 5 | `step-05-data-services-healthy.png` | MySQL and Redis both healthy | Linux terminal |
| 6 | `step-06-demo-seed-complete.png` | Migrations and canonical five-product seed complete | Linux terminal |
| 7 | `step-07-storefront-home.png` | Live seeded storefront home | Browser |
| 7 | `step-07-category-menu.png` | Category navigation after the optional mock seed | Browser |
| 8 | `step-08-merchant-console.png` | Scoped merchant console dashboard | Browser |
| 8 | `step-08-admin-console.png` | Separate scoped administrator console | Browser |
| 9 | `step-09-category-filter.png` | Optional mock-catalog category filter | Browser |
| 9 | `step-09-cart.png` | Real selected variant in the cart | Browser |
| 9 | `step-09-checkout.png` | Checkout carrying the same server-priced line | Browser |
| 10 | `step-10-tests-passed.png` | Current QA commands completing successfully | Linux terminal |
| 11 | `step-11-mobile-dependencies-ready.png` | Expo dependency check and Doctor (21/21) complete; typecheck and lint are verified separately | Linux terminal |
| 11 | `step-11-android-avd-ready.png` | Named API 36 AVD/toolchain ready on its reserved serial | Linux terminal/tooling |
| 12 | `step-12-app-launched.png` | MetroDrip development client launched, not Expo Go | Android device capture |
| 12 | `step-12-mobile-home.png` | Signed-in mobile Home | Android device capture |
| 12 | `step-12-mobile-product-detail.png` | Product with size/colour/fit selected | Android device capture |
| 12 | `step-12-mobile-cart.png` | Matching selected variant in mobile cart | Android device capture |
| 12 | `step-12-mobile-checkout.png` | Zone and server-formatted total at checkout | Android device capture |
| 12 | `step-12-mobile-order-tracking.png` | Signed-in simulated purchase at Paid | Android device capture |
| 12 | `step-12-mobile-notifications.png` | Home bell → Notifications showing Order confirmed | Android device capture |
| 12 | `step-12-order-in-merchant-console.png` | Matching order number in `/merchant/` → Orders | Browser |
| 13 | `step-13-safe-stop.png` | Processes stopped while the persistent DB volume remains | Linux terminal |

Every numbered guide step must have at least one referenced image. The guide QA
gate must fail if a referenced local asset is absent, if declared dimensions do
not match the PNG, or if a screenshot lacks unique alt text, lazy loading, async
decoding, a caption, and a full-resolution link.

## 2026-08-24 capture provenance

- **Host:** Linux. Windows, macOS, and native iOS were not claimed as executed.
- **Data:** disposable MySQL/Redis capture services and database
  `metrodrip_guide_capture`; simulated payment/push providers; fictional `.test`
  identities; no production or personal data.
- **Order of data creation:** canonical customer flows ran after `seed_demo` and
  before `seed_mock_catalog`. Only category/filter shots use the optional mock
  fixture. `seed_demo` supplies no image attachments or Men/Women children.
- **Browser:** the real Django server driven at a 1280×860 light,
  reduced-motion viewport, captured at 1.25 scale to **1600×1075**.
- **Terminal/tooling:** real sanitized command output on a consistent
  **1598×918** canvas (the final capture-tool adjustment from the nominal
  1600×900 target). Paths are repository-relative; secrets and `.env` values
  are never rendered.
- **Android:** real `MetroDrip_Pixel_API36` AVD and local API, captured from ADB
  at the device framebuffer's **1080×2400** resolution. The device image is
  cropped to the screen, not the emulator toolbar or desktop. Repeat captures use
  `npm run start:android:emulator`, which restores `adb reverse tcp:8081 tcp:8081` and opens the
  exact localhost development-client URL; Django remains separate at `10.0.2.2:8080`.
- **Checkout evidence:** the NCR checkout frame uses a separate fictional
  signed-in capture account so its complete short `.test` email remains legible.
  The Paid tracking, in-app Order confirmed notification, and merchant-console
  frames remain the correlated `MD-2026-00001` proof. Neither flow claims
  OS-level remote push delivery.
- **Safe-stop evidence:** the capture services use disposable tmpfs storage, so
  Step 13 demonstrates volume retention with a separate disposable named volume.
  It does not stop or inspect the developer's normal project containers.
- **Processing:** PNG metadata removed and images losslessly optimized. Never
  blur a secret after capture; prevent the secret from entering the frame.

If final capture tooling produces a different intrinsic dimension, update both
the manifest and the HTML `width`/`height` attributes in the same change. Do not
stretch an image to fit the nominal sizes above.

## 2026-09-06 complete mobile page capture

The `mobile-pages/` directory is a route-level inventory requested as separate,
human-readable page files. These images are not replacements for the numbered
guide evidence above. Their title-case filenames are deliberate so each export
reads as a page label when shared outside the repository.

| File | Visible page/state |
|---|---|
| `mobile-pages/Splash Page.png` | Guest onboarding with Create account, Sign in, and Continue as guest actions |
| `mobile-pages/Home Page.png` | Online home catalog |
| `mobile-pages/Shop Page.png` | Online catalog constrained to the finite one-result `Harness Prod` search state |
| `mobile-pages/Product Detail Page.png` | In-stock product with colour, size, and fit selected |
| `mobile-pages/Cart Page.png` | Populated cart with server-calculated totals |
| `mobile-pages/Checkout Page.png` | Guest delivery and payment form |
| `mobile-pages/Order Tracking Page.png` | Simulated guest order at Paid |
| `mobile-pages/Notifications Page.png` | Guest notification sign-in state |
| `mobile-pages/Saved Page.png` | Guest wishlist sign-in state |
| `mobile-pages/Orders Page.png` | Guest order-history sign-in state |
| `mobile-pages/Account Page.png` | Guest account state |
| `mobile-pages/Sign In Page.png` | Sign-in form with no credentials entered |
| `mobile-pages/Create Account Page.png` | Registration form with no personal data entered |
| `mobile-pages/Signed In Home Page.png` | Authenticated home with a saved item and unread-notification indicator |
| `mobile-pages/Signed In Saved Page.png` | Authenticated wishlist with one saved product |
| `mobile-pages/Signed In Checkout Page.png` | Checkout prefilled from the fictional customer profile |
| `mobile-pages/Signed In Order Tracking Page.png` | Authenticated simulated order at Delivered, with the complete six-step timeline |
| `mobile-pages/Signed In Order History Page.png` | Authenticated order history with all three simulated orders |
| `mobile-pages/Signed In Notifications Page.png` | Full authenticated notification history for the three simulated orders |
| `mobile-pages/Signed In Account Page.png` | Authenticated account dashboard with order, wishlist, and unread counts |

### Order journey: tracking and history at every step

The `mobile-pages/order-status-steps/` directory follows one authenticated
simulated order through the complete successful fulfilment journey. Each step
has two independent captures: the detailed tracking page and the order-history
list that a signed-in customer sees.

| Journey step | Order Tracking capture | Order History capture | Server state represented |
|---:|---|---|---|
| 1. Order placed | `Order Tracking - Order Placed Step.png` | `Order History - Order Placed Step.png` | Order `Pending`; no shipment yet |
| 2. Payment confirmed | `Order Tracking - Payment Confirmed Step.png` | `Order History - Payment Confirmed Step.png` | Order `Paid`; stock hold consumed |
| 3. Packed | `Order Tracking - Packed Step.png` | `Order History - Packed Step.png` | Order `Packed`; simulated shipment booked |
| 4. Shipped | `Order Tracking - Shipped Step.png` | `Order History - Shipped Step.png` | Order `Shipped`; shipment `In Transit` |
| 5. Out for delivery | `Order Tracking - Out for Delivery Step.png` | `Order History - Out for Delivery Step.png` | Order remains `Shipped`; shipment is `Out for Delivery` |
| 6. Delivered | `Order Tracking - Delivered Step.png` | `Order History - Delivered Step.png` | Order and shipment both `Delivered` |

The fifth Order History capture intentionally says `Shipped`. `Out for
Delivery` is a shipment-level checkpoint in the domain model, while the order
itself remains `Shipped`; the tracking page combines both state machines and
therefore advances to the fifth step.

### Page-component coverage audit

The code-level audit found 12 components in `mobile/src/screens/`. Every screen
component has at least one page capture; `AuthScreen` has both of its page
modes, and credential-dependent destinations have authenticated variants.

| Screen component | Page capture coverage |
|---|---|
| `SplashScreen` | `Splash Page.png` |
| `HomeScreen` | `Home Page.png`, `Signed In Home Page.png` |
| `ShopScreen` | `Shop Page.png` |
| `ProductDetailScreen` | `Product Detail Page.png` |
| `CartScreen` | `Cart Page.png` |
| `CheckoutScreen` | `Checkout Page.png`, `Signed In Checkout Page.png` |
| `OrderTrackingScreen` | Guest and signed-in page captures, plus all six journey-step captures above |
| `NotificationsScreen` | `Notifications Page.png`, `Signed In Notifications Page.png` |
| `WishlistScreen` | `Saved Page.png`, `Signed In Saved Page.png` |
| `OrdersScreen` | `Orders Page.png`, `Signed In Order History Page.png`, plus all six history captures above |
| `AccountScreen` | `Account Page.png`, `Signed In Account Page.png` |
| `AuthScreen` | `Sign In Page.png`, `Create Account Page.png` |

Reusable UI components are also represented inside these route-level pages:

| Reusable component | Representative full-page capture |
|---|---|
| `ProductCard` | Home, Shop, and Signed In Saved |
| `NavBar` | Home, Shop, Saved, Orders, and Account variants |
| `StickyBar` | Product Detail, Cart, Checkout, and Order Tracking |
| `PillButton` | Splash, authentication, empty states, checkout, and tracking |
| `MicroLabel` and `Mono` | Home, product, cart, checkout, account, and tracking |
| `EmptyState` | Guest Notifications, Saved, and Orders |
| `QtyStepper` | Cart |
| `CardActionPill` | Signed In Saved |

`OfflineBanner` and `LoadingState` are transient state components rather than
pages. They are deliberately absent from this online page set: the normal
emulator launch is readiness-gated, and none of these final captures was taken
from the offline fallback or during an indeterminate load. The exported
`BarcodeStrip` primitive is not imported by any screen and therefore has no
routed-page rendering to capture; Splash uses its own screen-local barcode
motif, which is visible in `Splash Page.png`.

- **Capture environment:** real `MetroDrip_Pixel_API36` Android emulator and
  live local Django API. ADB framebuffers are **1080 pixels wide**. Long native
  scroll views were captured to their true content end and stitched while
  retaining the app header, tab/sticky bar, and Android system inset exactly
  once; resulting heights range from **2400 to 4356 pixels**.
- **Infinite-scroll boundary:** the default Shop catalog has 1003 results and
  can keep loading additional pages, so it has no finite full-page endpoint.
  `Shop Page.png` uses the visible search `Harness Prod` (one result), making
  the captured page complete and reproducible rather than arbitrarily truncated.
- **Transaction evidence:** `Order Tracking Page.png` came from simulated guest
  order `MD-2026-00006`. The signed-in set uses a separate fictional customer
  and three simulated orders; order `MD-2026-00009` is shown at Delivered.
  The twelve journey-step captures follow that same order from Pending through
  Delivered. All flows use `.test` contact data.
- **Verification:** all 32 PNG files were decoded and dimension-checked. The 13
  route-level files, seven authenticated variants, and twelve order-journey
  captures were reviewed in generated contact sheets. Scroll probes reached a
  stable end before every stitched file was accepted. No offline banner,
  loading overlay, keyboard, password, token, or real personal data is visible.

## 2026-09-06 complete web page capture

The separate `web-pages/` collection contains 65 title-labelled desktop PNGs:
17 storefront/customer pages, one development-only staging preview, 28
merchant-console pages, and 19 administrator-console pages. Every image is a
full-document browser capture: the viewport is 1600×1000, while PNG dimensions
expand to the rendered content bounds. Fixed-height console scrollers are
expanded for capture so their complete navigation, forms, and table rows are
present. The collection covers every navigable HTML route, every registered
console module, representative populated detail pages, both role-boundary
refusal pages, and the custom order report/documents without replacing the
numbered setup-guide evidence above.

See [`web-pages/README.md`](web-pages/README.md) for the complete page-to-file
matrix, capture provenance, security controls, and explicit non-page exclusions.

## Exact unverified follow-up captures

These slots are intentionally absent and unreferenced. Capture them only on the
named platform, then add the image and platform-specific guide markup together.
Never copy a Linux/Android image and label it as another platform.

### Windows 10/11 + Android

Planned review-only slots:

`followup-windows-step-01-tools.png`,
`followup-windows-step-03-python-ready.png`,
`followup-windows-step-04-env-ignored.png`,
`followup-windows-step-05-services-healthy.png`,
`followup-windows-step-10-tests-passed.png`,
`followup-windows-step-11-api36-avd-ready.png`, and
`followup-windows-step-13-safe-stop.png`.

Checklist:

1. Use a clean Windows 10/11 x64 account with Docker Desktop, Node 22.13+, and
   JDK 17; show versions but no username/home path.
2. Run `scripts\setup-android-emulator.ps1`; verify Platform 36, Build Tools
   36.0.0, and `MetroDrip_Pixel_API36` with a 10 GB data partition.
3. Run `MetroDrip: Full mobile stack`; verify Compose health, Django readiness,
   AVD name, `emulator-5554`, the `tcp:8081` reverse mapping, and the MetroDrip development client.
4. Run the Windows backend and mobile QA commands from the guide. Capture only
   final success output, not environment values or tokens.
5. Stop Metro/Django/emulator and use `docker compose down` without `-v`; prove
   the named volume was retained.
6. Compare every visible command/result with the Windows tab before publishing;
   mark Windows verified only after the entire checklist passes.

### macOS + iOS simulator

Planned review-only slots:

`followup-macos-step-01-tools.png`,
`followup-macos-step-03-python-ready.png`,
`followup-macos-step-05-services-healthy.png`,
`followup-macos-step-10-tests-passed.png`,
`followup-macos-step-11-xcode-ios26-ready.png`,
`followup-macos-step-12-ios-simulator-launched.png`, and
`followup-macos-step-13-safe-stop.png`.

Checklist:

1. Use macOS capable of Xcode 26.4+ and the iOS 26 SDK; record `xcodebuild
   -version`, Node 22.13+, Python 3.14, Docker/Compose, and JDK 17.
2. Run `npm ci`, dependency check, Doctor, typecheck, lint, and both exports.
3. Set `EXPO_PUBLIC_API_URL=http://localhost:8080/api/mobile/v1`, bind Django to
   `0.0.0.0:8080`, run `npm run ios`, and confirm the generated project targets
   iOS 16.4 with bundle ID `ph.metrodrip.app`.
4. Capture only the simulator screen. Repeat the guest Paid flow and signed-in
   Paid → Home bell → Order confirmed → merchant-order match.
5. Exercise dark mode, keyboard/insets, permission denied/granted, offline/retry,
   and session restore before marking native iOS verified.
6. Stop services without deleting the DB volume and record the exact Xcode/iOS
   simulator versions in this file.

### Physical iPhone/local network and remote push

Planned review-only slots:

`followup-ios-device-local-network-permission.png`,
`followup-ios-device-app-launched.png`,
`followup-ios-device-order-confirmed.png`, and, only after real remote delivery,
`followup-ios-device-system-push.png`.

Checklist:

1. Use fictional `.test` account data and a development-signed internal build.
2. Put phone and host on the same trusted Wi-Fi, set the host LAN API URL, bind
   Django to `0.0.0.0:8080`, and accept MetroDrip's local-network prompt.
3. Prove denied permission produces a recoverable offline state, then restore
   permission in Settings and prove API recovery.
4. Complete the signed-in purchase and match tracking, in-app notification, and
   merchant order number.
5. Capture a system notification only with a real EAS project ID, Apple push
   credentials, and `PUSH_PROVIDER=expo`; redact device identifiers and do not
   expose the notification shade's unrelated personal content.
6. Record signing type, iOS version, network topology, and whether delivery was
   foreground/background/terminated. In-app simulated delivery alone must not
   be labelled remote push verification.

## Capture and maintenance rules

- PNG for terminal/application captures; SVG remains SVG for the favicon and
  inline diagrams.
- Use kebab-case filenames exactly as listed; numbering follows guide steps.
- Exclude browser/editor/emulator chrome unless the chrome itself is the setup
  evidence.
- Show only fictional accounts. Never capture passwords, bearer tokens, TOTP
  QR codes, `.env` contents, API keys, signing identities, device IDs, or real
  names/email addresses.
- Use descriptive alt text that states the visible result, not “screenshot of”.
- Any shared navigation, admin chrome, mobile layout, command, tool version, or
  seed change triggers a staleness review of every affected image.
- Replace an image by recapturing the real state. Do not composite, retouch, or
  relabel evidence from another platform.

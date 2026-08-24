# MetroDrip Mobile (Epic H)

Expo SDK 57 + React Native 0.86 (TypeScript) customer app for iOS and Android. Consumes the
public mobile API at `/api/mobile/v1/`; the Merchant and Administrator consoles
stay web-only (D-14).

## The one rule

**The app is a client only (D-13).** It never computes or re-computes prices,
subtotals, shipping fees, or totals; never decides stock availability; never
transitions order state; never decides whether a review is permitted. Money
arrives as integer centavos **plus** a server-formatted display string, and the
app renders the display string.

Verify with:

```bash
# Should return no hits in src/ (excluding the theme's numeric tokens)
grep -rnE "(price|subtotal|total|fee)\s*[*+/-]" src/
```

## Setup

Requirements: Node.js 22.13+; for Android, JDK 17 plus Android API 36 / Build
Tools 36.0.0 (the app's runtime minimum is API 24); for iOS, macOS with Xcode
26.4+ and the iOS 26 SDK.

```bash
npm ci
cp .env.example .env        # point EXPO_PUBLIC_API_URL at your backend
npm run android             # first Android build/install
# macOS only: npm run ios   # first iOS build/install

# Later JavaScript-only sessions, once the development client is installed:
npm start
```

`npm start` runs `expo start --dev-client`. Expo Go is not the supported client.
Native projects use Continuous Native Generation: `android/` and `ios/` are
ignored outputs created from `app.json`. Put durable native configuration in
Expo config or a config plugin, then validate it with a clean prebuild; do not
hand-edit generated projects (ADR-H-006).

Android compiles/targets API 36 and declares API 24 as its minimum. The versioned
`withAndroidCoreLibraryDesugaring` config plugin adds `desugar_jdk_libs` 2.0.3
for Java time APIs on API 24–25. The same clean debug APK has rendered on API 24
and API 36 emulators; normal development uses the named API 36 AVD below.

> **Running it on an Android emulator in Antigravity IDE?** See
> [EMULATOR.md](EMULATOR.md) — one script installs the SDK and creates the
> AVD, and `.vscode/tasks.json` boots the whole stack from
> *Terminal → Run Task… → MetroDrip: Full mobile stack*.

`EXPO_PUBLIC_API_URL` defaults to `http://10.0.2.2:8080/api/mobile/v1`
(the Android emulator's alias for the host machine). For a physical device use
your LAN IP, e.g. `http://192.168.1.10:8080/api/mobile/v1`.

Run the Django backend with the simulated payment provider so checkout
completes without PayMongo keys:

```bash
# repo root (Linux/macOS)
PAYMENT_PROVIDER=simulated python manage.py runserver 0.0.0.0:8080
```

Development honors an explicit `PAYMENT_PROVIDER=simulated` or `paymongo`.
When the variable is blank, it selects PayMongo only when a non-empty
`PAYMONGO_SECRET_KEY` exists; an invalid value or explicit keyless PayMongo
selection fails during startup.

Verify purchase ownership with two separate flows:

- A guest purchase reaches public Order Tracking at **Paid**. Because it has no
  customer, it does not create an in-app notification or later appear in an
  account automatically.
- A signed-in purchase reaches **Paid**, appears under the Home bell as **Order
  confirmed**, and has the same order number in `/merchant/` → Orders.

## Internal preview builds and store release

Profiles are scaffolded, but distribution remains blocked until store accounts,
real assets, URLs, and signing/push credentials exist:

1. `npm i -g eas-cli` and `eas login`
2. Run `eas init` to add the real owner/project ID; no fake IDs are committed
3. Add approved icon, splash, adaptive icon, and store-listing assets
4. Configure `EXPO_PUBLIC_API_URL` in the named EAS environment; it is public bundle configuration, never a secret
5. Build internal preview binaries:

```bash
npm run build:android   # Internally distributed Android APK
npm run build:ios       # Internally distributed iOS build; requires an Apple team
```

Those scripts use the `preview` profile. They do not upload to TestFlight or a
Google Play testing track. Store-bound artifacts use the `production` profile
after package ownership, signing, listings, and review metadata are ready.

Staging must set `PUSH_PROVIDER=expo`, configure an EAS project ID, and provide
push credentials for real device delivery. The in-app notification centre does
not prove OS-level remote push delivery.

## Structure

| Path | Role |
|---|---|
| `src/theme/` | Design tokens (§2), typography (§3), light/dark provider (FR-31) |
| `src/api/` | Fetch client (secure-store tokens, version header, refresh), typed endpoints |
| `src/store/` | Auth session (FR-22/23) and the client cart (FR-25) |
| `src/components/` | Shared primitives + the grid product card |
| `src/screens/` | 11 Figma-mapped screens plus the distinct Orders tab |
| `src/navigation/` | 5-tab bar (volt active dot) + root stack |
| `src/hooks/` | Push registration and deep-link routing (FR-27/28) |

## Screens ↔ Figma frames

| Screen file | Frame | Node |
|---|---|---|
| `SplashScreen` | M01 Splash & Onboarding | `63:3` |
| `HomeScreen` | M02 Home (Tab) | `63:67` |
| `ShopScreen` | M03 Shop & Search (Tab) | `63:155` |
| `ProductDetailScreen` | M04 Product Detail | `64:2` |
| `CartScreen` | M05 Cart | `64:74` |
| `CheckoutScreen` | M06 Checkout | `64:152` |
| `OrderTrackingScreen` | M07 Order Tracking | `65:2` |
| `NotificationsScreen` | M08 Notifications | `65:83` |
| `AccountScreen` | M09 Account | `65:155` |
| `AuthScreen` | M10 Sign In / Register | `67:2` |
| `WishlistScreen` | M11 Saved / Wishlist | `67:45` |
| `OrdersScreen` | Additional Orders tab (no separate supplied frame) | — |

## QA

```bash
npm ci
npm run dependencies:check
npm run doctor
npm run typecheck
npm run lint
npm run export:android
npm run export:ios

# JDK 17 + Android API 36
npm run prebuild:android
./android/gradlew -p android --no-daemon :app:assembleDebug
```

On Windows use `.\android\gradlew.bat -p android --no-daemon :app:assembleDebug` for the final
command.

The export commands validate both JavaScript bundles on any host; they are not
an iOS native compile. A real iOS build and simulator/device walkthrough remain
macOS-only follow-ups. Clean prebuild deletes and recreates only ignored native
output, so move no durable work into those directories.

## Colour rules (violations are bugs)

1. `volt` is a **background** colour. Volt-as-text on light uses `accentText`.
2. Text on a volt fill is always `onVolt` — never `ink` (which inverts in dark).
3. `border` is never a text colour; disabled/sold-out states use `muted` plus a
   non-colour cue (strikethrough or a "SOLD OUT" label).

Sections that are ink-**filled** in light mode (splash, home hero, tracking
header) keep a dark fill in dark mode via `useTheme().onInk` — they must never
invert to white.

## Security (NFR-19)

- JWT access/refresh live in `expo-secure-store` (Keychain / Keystore) only —
  never `AsyncStorage`.
- Refresh tokens rotate and the previous one is blacklisted server-side.
- Payment runs through the provider's hosted flow; card data never touches the
  app.
- No PII in logs.

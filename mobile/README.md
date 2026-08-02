# MetroDrip Mobile (Epic H)

React Native + Expo (TypeScript) customer app for iOS and Android. Consumes the
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

```bash
npm install
cp .env.example .env        # point EXPO_PUBLIC_API_URL at your backend
npm start                   # then press i / a, or scan with Expo Go
```

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

## Internal builds (H-13 — TestFlight / Play)

Scaffold only until store accounts and real assets exist:

1. `npm i -g eas-cli` and `eas login`
2. Replace `extra.eas.projectId` and `owner` in `app.json` via `eas init`
3. Add brand `assets/icon.png`, `splash.png`, `adaptive-icon.png` and wire them in `app.json`
4. Set `EXPO_PUBLIC_API_URL` in `eas.json` profiles to your staging/production API
5. Build internal binaries:

```bash
npm run build:android   # Play internal / APK preview
npm run build:ios       # TestFlight (requires Apple team)
```

Staging must set `PUSH_PROVIDER=expo` for real device pushes.

## Structure

| Path | Role |
|---|---|
| `src/theme/` | Design tokens (§2), typography (§3), light/dark provider (FR-31) |
| `src/api/` | Fetch client (secure-store tokens, version header, refresh), typed endpoints |
| `src/store/` | Auth session (FR-22/23) and the client cart (FR-25) |
| `src/components/` | Shared primitives + the grid product card |
| `src/screens/` | M01–M11, one file per Figma frame |
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

# MetroDrip — Session Continuity Handover

```yaml
doc_type: session_continuity_handover
audience: LLM_agent_successor
project: MetroDrip (TIP_MetroDrip-Ecommerce)
repo_root: /home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce
remote: https://github.com/SecretlySpy/TIP_MetroDrip-Ecommerce.git
branch: main
head_commit: a396899
remote_head: a396899          # verified via `git ls-remote origin main` — local == remote
working_tree: clean
generated: 2026-08-07
supersedes: nothing
complements: MetroDrip_AI_Handover.md (v1.4, the pre-implementation PLAN)
```

> **Read this first.** This document captures **current state and continuity** — what is built, what is verified, what is broken, and what to do next. It does **not** restate the full product plan. `MetroDrip_AI_Handover.md` is the approved plan and remains authoritative for scope, data model, and requirements. Where the two disagree about *what exists today*, **this document wins**, because it was written against a running system.

---

## 0. Source-of-truth precedence

Resolve any conflict in this order. Do not trust a lower tier over a higher one.

| Rank | Source | Authority |
|---|---|---|
| 1 | The code + a passing command | Ground truth. Always verifiable. |
| 2 | `DECISIONS.md` (66 ADRs) | Why the code is the way it is. Records reversals honestly. |
| 3 | This document | Current state, session continuity, traps. |
| 4 | `MetroDrip_AI_Handover.md` | Approved plan: scope, FRs, NFRs, data model. |
| 5 | `AGENTS.md` / `CLAUDE.md` | Operating rules for the agent. `CLAUDE.md` delegates to `AGENTS.md`. |
| 6 | `AI Documentation Notes.md`, `README.md` | Module-level narrative. |

**Operating rule inherited from `AGENTS.md`:** do not mark work complete without a passing verification command, and record any deviation forced by a constraint as a new ADR in `DECISIONS.md` rather than dropping it silently.

---

## 1. Snapshot — verified status

All figures below were produced by running the command, not recalled.

| Gate | Command | Result |
|---|---|---|
| Python tests | `.venv/bin/python -m pytest` | **560 collected** across 25 test files |
| Lint | `.venv/bin/ruff check .` | **All checks passed** |
| Format | `.venv/bin/ruff format --check .` | **191 files already formatted** |
| Mobile types | `cd mobile && npm run typecheck` | **clean** (`tsc --noEmit`, no output) |
| Mobile lint | `cd mobile && npm run lint` | **0 errors, 9 warnings** |
| Responsive | `node scripts/check-responsive.mjs` | 15 routes × 4 widths, **60/60** |
| Dead CSS | `node scripts/check-css-selectors.mjs` | pass, both stylesheets |
| Git sync | `git ls-remote origin main` | `a396899` — **fully pushed, nothing outstanding** |

**Correction carried forward:** earlier in the session the last three commits were believed unpushed and blocked on missing credentials. That is **false as of verification** — `origin/main` and local `main` are both at `a396899`. There is no pending push. Do not re-attempt one.

---

## 2. What this system is

**MetroDrip** is a B2C e-commerce + inventory platform for a Metro Manila streetwear brand. Solo developer, bootstrap budget (infra ≤ ~$25/month).

### 2.1 Architecture — stated accurately

This is a **service-oriented modular monolith with bounded contexts, mid-migration to microservices via the strangler-fig pattern.** It is *not* a microservices system today, and any status report claiming otherwise is wrong.

```
[ Expo client ]──JWT──▶ /api/mobile/v1/ ─┐
[ Browser     ]─HTMX──▶ Django storefront ├─▶ MySQL 8 (InnoDB, utf8mb4)
[ Merchant    ]───────▶ /merchant/        │      single instance
[ Admin       ]───────▶ /admin/           ┘
                              │ opt-in HTTP (defaults OFF)
                              ├─▶ notifications:8002  (email/SMS/push I/O)
                              ├─▶ fulfillment:8003    (waybill booking I/O)
                              └─▶ inventory:8001      (full contract; default stays local)
Public Caddy → app:8000 only. Internal Caddy :9080 → /internal/* sidecars.
```

- Sidecars are containerized, token-authenticated, health-checked, and **fail closed** without their tokens.
- They sit behind the Compose **`services` profile** in both dev and staging (ADR-P3-026), so the default stack never instantiates them.
- **Django still owns stock ownership, checkout atomicity, and all DDL.** Shared schema / exclusive writer (ADR-P3-013) — this is precisely what makes rollback a single environment variable.

### 2.2 Tech stack (locked)

| Layer | Choice |
|---|---|
| Language / framework | Python 3.14 · Django 5.2 |
| Database | MySQL 8, InnoDB only, `utf8mb4` |
| Concurrency | Django ORM + `transaction.atomic()` + `select_for_update()` |
| Web frontend | Django Templates + **HTMX + Alpine.js** — server-rendered, no SPA |
| Mobile | **React Native 0.74.5 · React 18.2.0 · Expo SDK 51 · strict TypeScript** |
| Public API | DRF at `/api/mobile/v1/` (JWT + refresh rotation) |
| Sidecars | FastAPI + uvicorn under `services/` |
| Messaging | **Transactional outbox + `FOR UPDATE SKIP LOCKED` poller. No broker.** (ADR-P3-018) |
| Deploy | Docker + Caddy; single host |
| Testing | pytest against real MySQL; ruff; CI on every push |

**Design system is hand-rolled.** No CSS framework, no component library — on either platform. Do not introduce one. All colours resolve through existing tokens; do not add raw colour values.

---

## 3. Hard invariants — non-negotiable

Violating any of these is a defect regardless of what else the change achieves.

1. **No overselling, ever.** `available = qty_on_hand − qty_reserved`. Every stock mutation inside `transaction.atomic()` with `select_for_update()`. The N-parallel-buyers concurrency test is a release gate.
2. **Money is integer centavos.** No floats anywhere. `INT` columns. Format at display time only.
3. **Webhooks are payment truth.** `Pending → Paid` only via signature-verified PayMongo webhook. Client redirects are never trusted. Handlers are idempotent.
4. **Append-only stock audit.** Every change writes a `StockMovement` row (`delta`, `reason`, `ref_order`). Never update or delete one.
5. **Order state machine enforced server-side.** `Pending → Paid → Packed → Shipped → Delivered`, plus `Cancelled` / `Refunded`. Illegal transitions raise.
6. **MySQL InnoDB + utf8mb4** from the first migration.
7. **Card data never touches the server** — PayMongo hosted flow only.
8. **The mobile app is a client only.** No business logic, no price math, no stock decisions on device. Server prices win at checkout.
9. **Python 3 syntax only.**

---

## 4. Repository map

```
TIP_MetroDrip-Ecommerce/
├── AGENTS.md, CLAUDE.md          # agent operating rules (CLAUDE.md → AGENTS.md)
├── DECISIONS.md                  # 66 ADRs — the reasoning record
├── MetroDrip_AI_Handover.md      # v1.4 approved PLAN (scope/FR/NFR/data model)
├── MetroDrip_Continuity_Handover.md   # THIS FILE — current state
├── AI Documentation Notes.md     # module-level narrative
├── apps/                         # Django bounded contexts
│   ├── accounts/  catalog/  cms/  core/  inventory/  mobile_api/
│   ├── notifications/  orders/  payments/  reviews/  shipping/  storefront/
├── services/                     # FastAPI strangler sidecars
│   ├── inventory/   (api, models, database, idempotency, main)
│   ├── notifications/  fulfillment/  _shared/security.py
├── contracts/                    # shared contract defs: inventory_v1, fulfillment_v1,
│                                 #   notifications_v1, errors
├── config/settings/{base,dev,staging,prod,test}.py
├── templates/  static/css/{storefront,console}.css  static/js/
├── mobile/                       # Expo app
│   └── src/{api,components,hooks,navigation,screens,store,theme}/
├── scripts/                      # verification harnesses (see §7)
├── tests/                        # 25 files, 560 tests + tests/contract/
├── deploy/  docker/  jobs/  docs/
└── .github/workflows/ci.yml      # jobs: qa · deployment-contracts · mobile
```

### 4.1 Key modules to know

| Concern | Location | Note |
|---|---|---|
| Single HTTP egress | `apps/core/http.py` | `ServiceRejected` / `ServiceUnavailable` / `ServiceUncertain`; split connect/read timeouts; **process-local** breaker (cache-backed would no-op under DummyCache) |
| Checkout | `apps/orders/checkout.py` | Reserve-before-order (ADR-P3-022); `_release_quietly()`; cancels order if payment session fails |
| Stock holds | `apps/orders/models.py` | `StockHold`, `StockHoldState`, `OutboxMessage`, `OutboxState` |
| Hold consumption | `apps/payments/holds.py` | `consume_order_holds()` — one implementation, both providers |
| Mobile API | `apps/mobile_api/urls.py` | 24 routes, see §5.2 |
| Mobile typography | `mobile/src/theme/typography.ts` | `lineHeightFor(fontSize, ratio)` via `PixelRatio.getFontScale()` |
| Mobile primitives | `mobile/src/components/primitives.tsx` | `ForwardedTextProps`, `EmptyState`, `LoadingState`, `PillButton`, `QtyStepper` |

---

## 5. Core features & functional surface

### 5.1 Web (Django, server-rendered)

- **Storefront:** home, shop with filters/sort/pagination (htmx-swapped), product detail with variant selection, cart, checkout, contact, developers, flatpages.
- **Accounts:** register/login, profile, saved addresses, order history, wishlist, reviews (verified purchase only).
- **Two separate AdminSites** with **disjoint model registries** — `/admin/` (administrator) and `/merchant/` (merchant). The other console's URLs are not merely forbidden, they are **unrouted** (NFR-9).
- Guest checkout supported alongside accounts.

### 5.2 Mobile API — `/api/mobile/v1/`

```
auth/register/            auth/login/             auth/refresh/
auth/logout/              auth/password-reset/    auth/password-reset/confirm/
catalog/products/         catalog/products/<slug>/    catalog/categories/
cart/validate/            checkout/               checkout/confirm-simulated/
shipping/zones/           shipping/zones/resolve/
orders/                   orders/<order_no>/      orders/track/<token>/
account/profile/          wishlist/               reviews/
notifications/            notifications/read-all/ notifications/<pk>/read/
notifications/devices/
```

> **Trap:** the product list is `catalog/products/`, **not** `products/`. Guessing the shorter path returns 404.

### 5.3 Mobile app — 11 screens

`Splash · Auth · Home · Shop · ProductDetail · Cart · Checkout · OrderTracking · Wishlist · Notifications · Account`

Navigation is a 5-tab bar + native stack. Tokens live in SecureStore only. Cart is client-side; **server prices authoritative at checkout**.

> **Known defect, unfixed:** the tab labelled **Orders renders `NotificationsScreen`**, so the announced accessible name contradicts the screen title. Recorded but not repaired — see §9.

---

## 6. What this session changed (all committed & pushed)

Four commits, oldest first:

| Commit | Scope |
|---|---|
| `e4df737` | `fix(ci)`: staging sidecars behind the `services` profile |
| `04a1ef8` | `fix(ui)`: console table scrolling, 320/1440 tiers, mobile fixed widths |
| `5a6ed66` | `fix(a11y)`: focus ring contrast, press feedback, 44px touch targets |
| `52bca01` | `feat(ui)`: wire htmx swaps, convert ad-hoc empty states |
| `a396899` | `fix(mobile)`: Dynamic Type, touch targets, errors misreported as empty |

### 6.1 Substantive fixes worth knowing

- **P0 table clipping.** The real bug was `.dense-table`, *not* `.results` as the brief claimed. Fixed with a `.table-scroll` wrapper plus **`min-width: 0` on `.console-panel`** — the load-bearing line. A naive `scrollWidth` check *passes because of* this bug, which is why `check-responsive.mjs` measures clipping separately.
- **Genuine WCAG failure.** `console.css` set `outline: 2px solid rgba(212,255,63,0.3)` on focused inputs — nowhere near the 3:1 required by SC 1.4.11/2.4.11, and specific enough to *suppress* the good global indicator. Alpha removed.
- **Zero `:active` rules existed** in 3,567 lines of CSS, so no control acknowledged a press on touch. Added across both stylesheets.
- **htmx was loaded on every page and used by nothing**, while the server half (`views.py` answering `HX-Request`) was built and tested. Now wired: `hx-swap="outerHTML"` (the fragment emits its own `#product-results` wrapper — `innerHTML` would nest a duplicate per swap), indicator **outside** the swapped region, `hx-boost` scoped to the filter `<aside>` and pagination `<nav>` only.
- **Dynamic Type.** RN scales `fontSize` but leaves a literal `lineHeight` alone. Worst case put 76dp glyphs in a 38dp line box at 200%. Line heights are now ratios × `PixelRatio.getFontScale()`; 12 interactive rows moved `height` → `minHeight`. **No global `maxFontSizeMultiplier`** — the OS setting is honoured; the prop is forwardable per call site.
- **Dead-end checkout.** `CheckoutScreen`'s zone fetch had no `.catch`; on failure `zone` stayed null, `disabled={!zone}` greyed Pay out permanently, and nothing explained why. Recoverable only by force-quitting. Fixed, plus `accessibilityLiveRegion="assertive"` (there were **zero** live regions in the app).
- **Errors rendered as empty states.** Shop / Wishlist / Notifications each caught an error and showed their *empty* state — telling a shopper their wishlist was empty when the request had failed. Wishlist `remove()` also dropped the row even when the server call failed; now rolls back.

### 6.2 Live end-to-end run (this session)

Both applications were launched and **driven**, not merely started.

**Web** — Django dev server, all storefront routes 200, consoles 302→login. P0 fix proven programmatically: `{"tableScrolledBy":586,"consoleFrameMoved":false}`.

**Mobile** — booted AVD `MoneyMap_VSCode_API_35` (API 35), ran the app in Expo Go, completed a full purchase:

| Step | Evidence |
|---|---|
| Home | `catalog/categories/` 200, `catalog/products/?sort=newest` 200 |
| Product | variant → Carbon Black / M / Regular, "10 in stock", CTA enables only when complete |
| Cart | ₱2,499×2 + ₱899×3 = ₱7,695 + ₱159 Luzon = **₱7,854** |
| Checkout | zone resolved Luzon; Pay enabled |
| Order | `checkout/` **201** → `confirm-simulated/` **200** → **MD-2026-00001, Paid** |

**Invariants verified in the database afterwards, not assumed:**

```
StockHold        → state = committed
OutboxMessage    → topic = stock.commit, state = sent   (poller drained it)
StockMovement    → delta = -2 and -3, reason = sale, ref_order_id = 1
```

Append-only movements match cart quantities exactly. The outbox → poller → ledger path works end to end through a real mobile client.

---

## 7. How to run and verify everything

### 7.1 Web

```bash
cd /home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce
docker compose up -d db                       # MySQL 8; sidecars are NOT in the default profile
export DJANGO_SETTINGS_MODULE=config.settings.dev
.venv/bin/python manage.py migrate            # ← see §8.1, this is not optional
PAYMENT_PROVIDER=simulated .venv/bin/python manage.py runserver 0.0.0.0:8080 --noreload
```

Bind `0.0.0.0` and use port **8080** if the emulator must reach it — `mobile/.env` hardcodes `EXPO_PUBLIC_API_URL=http://10.0.2.2:8080/api/mobile/v1`.

### 7.2 Mobile on the Android emulator

```bash
export PATH="$PATH:$HOME/Android/Sdk/emulator:$HOME/Android/Sdk/platform-tools"
emulator -avd MoneyMap_VSCode_API_35 -no-audio -no-snapshot-save -gpu swiftshader_indirect &
# wait for: adb shell getprop sys.boot_completed == 1   (~45s)

adb reverse tcp:8081 tcp:8081
adb reverse tcp:8080 tcp:8080

cd mobile
npx expo start --offline --port 8081 &        # ← --offline is REQUIRED, see §8.2

adb shell am start -a android.intent.action.VIEW -d "exp://127.0.0.1:8081" host.exp.exponent
adb exec-out screencap -p > /tmp/shot.png     # then LOOK at it; a blank frame is a failed launch
```

Expo Go **2.31.2** is already installed on that AVD and matches SDK 51. Drive with `adb shell input tap X Y` / `input text`.

### 7.3 Verification harnesses

Both are hand-rolled, drive headless Chrome over the **Chrome DevTools Protocol** using Node 22's built-in `fetch`/`WebSocket`, and add **no dependency** to a repo that has deliberately avoided a frontend toolchain.

| Script | Purpose |
|---|---|
| `scripts/check-responsive.mjs` | NFR-08 gate. Page scroll + **clipped tables** + touch targets at 320/768/1024/1440. Exits non-zero on failure. Set `CONSOLE_USER` / `CONSOLE_PASSWORD` to include the 5 console routes. |
| `scripts/check-css-selectors.mjs` | Dead-selector guard, scoped to `@media` blocks. Understands template-composed names (`kpi-card--{{ variant }}`) and Alpine `:class` bindings. |
| `scripts/smoke-services.sh` | Sidecar smoke test. |

```bash
node scripts/check-responsive.mjs http://127.0.0.1:8080
node scripts/check-css-selectors.mjs
.venv/bin/python -m pytest && .venv/bin/ruff check . && .venv/bin/ruff format --check .
cd mobile && npm run typecheck && npm run lint
```

> **Process trap:** never `pkill -f "python -m pytest"` — it matches and kills the invoking shell. Match on `comm` instead. Two concurrent pytest runs deadlock on the test database and present as a hang; that is process management, not a code bug.

### 7.4 CI

`.github/workflows/ci.yml` — three jobs: **`qa`**, **`deployment-contracts`**, **`mobile`**. `deployment-contracts` validates the Compose schema *with* the `services` profile but never instantiates the sidecars; that job previously failed with `No such image: metrodrip-services:staging`, fixed in `e4df737`.

---

## 8. Environment traps — read before debugging

These cost real time this session. Each is environmental, not a code defect.

### 8.1 Migrations are not applied by default

A fresh checkout will **500 on checkout** with:

```
django.db.utils.ProgrammingError: (1146, "Table 'metrodrip.inventory_idempotencyrecord' doesn't exist")
```

Three migrations from this work stream must be applied: `inventory.0003_idempotencyrecord_reservation_checkout_id`, `orders.0002_stockhold`, `orders.0003_outboxmessage`. Confirm the models are in sync first — `manage.py makemigrations --check --dry-run` should report **"No changes detected"**. If it does, the fix is `migrate`, not new migrations.

### 8.2 `expo start` requires `--offline` here

`app.json` declares `owner: "metrodrip"` with a **placeholder** `projectId` (`00000000-...`). The CLI tries to resolve that owner, demands an Expo account, and exits non-interactively:

```
CommandError: Input is required, but 'npx expo' is in non-interactive mode.
```

`--offline` skips the resolution. Also avoid `expo start --android`: it tries to *download* Expo Go and hits the same wall. Use `adb reverse` + an `exp://` deep link instead.

Note the failure mode is subtle: when the CLI dies this way, **Metro survives** and `/status` returns `packager-status:running`, but the manifest endpoint the client needs is gone — Expo Go then reports *"Could not load exp://127.0.0.1:8081."*

### 8.3 Metro is silent without a TTY

Bundling progress never reaches a redirected log. Absence of `Android Bundled …` is **not** evidence of failure. Prime and time the bundle directly instead:

```bash
curl -s -o /dev/null -w "%{http_code} %{size_download} %{time_total}\n" \
  'http://127.0.0.1:8081/node_modules/expo/AppEntry.bundle?platform=android&dev=true&hot=false&lazy=true&transform.engine=hermes&transform.bytecode=true&transform.routerRoot=app'
# observed: 200, 9,171,366 bytes, 16.9s cold
```

### 8.4 `mobile/node_modules` carries untracked packages

`react-native-web`, `react-dom`, `@expo/metro-runtime` were installed with `--no-save` during a web-render attempt. They are **not** in `package.json`; a clean `npm ci` will not reproduce them. `package.json` and `app.json` were verified unmodified. Harmless, but do not mistake them for declared dependencies.

### 8.5 `adb shell input text` mangles `@`

Use `adb shell input keyevent KEYCODE_AT` for the literal character. `%s` encodes a space.

---

## 9. Open items & immediate next steps

Ordered by value. Each has an acceptance criterion, per the "no completion without a passing command" rule.

### P0 — Verify 200% Dynamic Type on the emulator

**ADR-P5-003 states this was verified by reasoning only, "there is no simulator in this environment." That premise is now obsolete** — AVD `MoneyMap_VSCode_API_35` boots and runs the app (§6.2). This is the single highest-value outstanding item because it closes the one gap the ADR explicitly flagged.

```bash
adb shell settings put system font_scale 2.0
# relaunch, then screenshot Home / ProductDetail / Cart / Checkout and LOOK at them
```

**Accept when:** no clipped line boxes, no truncated CTA labels, no overlapping rows at `font_scale 2.0` across all 11 screens. **Then amend ADR-P5-003** to replace the "not device-verified" paragraph with the result — including if it fails.

### P1 — Fix the Orders tab rendering `NotificationsScreen`

`mobile/src/navigation/index.tsx` — the tab labelled *Orders* renders the wrong screen, so the accessible name contradicts the screen title. **Accept when:** the tab renders the orders list and `tabBarAccessibilityLabel` matches; typecheck + lint stay clean.

### P2 — Measure the `consume_order_holds` latency hazard in staging

The residual risk stated in **ADR-P3-025**: under `INVENTORY_PROVIDER=service`, a stock commit is an HTTP call made **while holding a lock on the `Payment` row**, up to the timeout budget. Latency/throughput hazard, not correctness (the outbox makes intent durable, the ledger de-duplicates). **This is explicitly named as the next thing to address before anyone selects `service` in production.** Nothing has ever run this provider in a deployed environment.

**Accept when:** p50/p95 lock-hold duration measured in staging under the `services` profile, recorded in a new ADR, with a go/no-go on the default flip. **Do not flip `INVENTORY_PROVIDER` to `service` by default** — ADR-P3-005's rule (never flip until parity) still binds; ADR-P3-025 only widened the allowlist.

### P3 — Smaller, well-defined

| Item | Detail | Accept when |
|---|---|---|
| 9 mobile lint warnings | 4 auto-fixable via `--fix` | `npm run lint` → 0 warnings, typecheck still clean |
| Wordmark contrast | Header "Drip" renders volt-on-white in light mode — close to illegible. **Pre-existing token pairing, not introduced by the P0–P3 work.** Needs a token decision, not a raw colour. | Contrast ≥ 4.5:1 in both themes, no new colour values |
| Pre-existing dead CSS | `.account-grid`, `.announce-bar` sit in the guard's allowlist rather than deleted — removing another author's unapplied layout was judged a separate call | Explicit decision recorded either way |

### Not next — deliberately

Do **not** start a "convert the mobile app to JavaScript/React Native" migration. That was requested earlier in this session on two false premises: the backend migration is *not* complete (see §2.1), and the app is *already* React Native 0.74.5 + React 18.2.0 in strict TypeScript. The premises were checked and rejected; the user redirected to closing the real CI gap instead.

---

## 10. Working method that proved out

Carry these forward; each was earned by being wrong first.

1. **Measure, never estimate.** `.btn` was estimated at 50px, measured 43. `.navbar__toggle` passed on height, failed on width. Django's changelist search crushed to 26px. Every estimate that was checked was wrong.
2. **A passing metric can be an artifact of the bug.** The naive `scrollWidth` check passes *because* the table is clipped. When a check passes suspiciously easily, ask what would make it pass while broken.
3. **Verify the brief before implementing it.** The P0 diagnosis named the wrong element; `.results` already scrolled. Implementing it verbatim would have shipped a no-op labelled as a fix.
4. **A dead selector is worse than a missing one** — in review it reads as covered. Hence `check-css-selectors.mjs`, written after shipping three dead selectors.
5. **Run the app, don't just launch it.** Launching proves the entrypoint resolves; that's typechecking with extra steps. The migration bug in §8.1 was invisible to 560 passing tests and appeared the instant a real client tapped Pay.
6. **Reduced motion means less motion, not no feedback.** A blanket `animation-duration: 0.01ms !important` silenced the loading spinner — a progress indicator that cannot indicate progress. Progress indicators are exempted.
7. **State unverified things as unverified.** ADR-P5-003 says plainly that 200% Dynamic Type was reasoned, not device-tested. That honesty is why §9's P0 is actionable rather than a surprise at release.

---

## 11. Document map

| File | Contains |
|---|---|
| `MetroDrip_AI_Handover.md` | v1.4 approved plan: product summary, tech stack, data model, FR/NFR, build order, milestones, risks, out-of-scope |
| `DECISIONS.md` | 66 ADRs. Recent: P3-018 outbox · P3-020 concurrency gates + the idempotency hole they found · P3-021 full contract · P3-022 reserve-before-order · P3-025 service permitted, default local · P3-026 profiled sidecars in staging · P5-002 audit of the presentation brief · P5-003 P2 completion |
| `AI Documentation Notes.md` | Module-level narrative, seeding scripts |
| `AGENTS.md` | Agent operating rules — planning, QA, security, docs workflow |
| `docs/BRANCH_PROTECTION.md` | Branch policy |
| `contracts/` | `inventory_v1`, `fulfillment_v1`, `notifications_v1`, `errors` |

---

## 12. Continuity checklist for the successor agent

Run this before touching anything:

```bash
cd /home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce
git log --oneline -5 && git status --short
git ls-remote origin main                      # confirm local == remote
.venv/bin/python manage.py makemigrations --check --dry-run   # expect "No changes detected"
.venv/bin/python manage.py migrate             # §8.1 — do this even if tests pass
.venv/bin/python -m pytest -q
cd mobile && npm run typecheck && npm run lint
```

Then read, in order: this document → `DECISIONS.md` (last 6 ADRs) → `MetroDrip_AI_Handover.md` §3 Hard Invariants → the code you intend to change.

**All work goes to `main`.** Commits are pushed to `main` directly per the standing instruction from this session.

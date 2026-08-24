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
  cropped to the screen, not the emulator toolbar or desktop.
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
   AVD name, `emulator-5554`, and the MetroDrip development client.
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

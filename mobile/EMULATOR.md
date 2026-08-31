# Running the MetroDrip development client

Antigravity is VS Code-based, so it uses the repository's `.vscode/tasks.json`
directly. This guide runs the Expo 57 development client against the local
Django API on the dedicated **`MetroDrip_Pixel_API36`** emulator.

Verified scope through 2026-08-30: Linux host, real API 36 Android AVD, local Django
API, simulated checkout, deterministic Metro reconnect after a cold boot, and clean-APK render
smoke tests on API 24 and API 36.
The APK declares compile/minimum/target SDK 36/24/36; a CNG config plugin supplies
`desugar_jdk_libs` 2.0.3 for Java time APIs on API 24–25. The Windows installer/task path is syntax- and
contract-checked but has not been executed on Windows in this delivery. Native
iOS execution remains unverified until run on qualifying macOS hardware.

## 1. One-time host setup

Requirements:

| Requirement | Contract | Check |
|---|---|---|
| Node.js | 22.13+ | `node --version` |
| Java | JDK 17 | `java -version` |
| Android SDK | platform 36, Build Tools 36.0.0, platform-tools, emulator | `sdkmanager --list_installed` |
| AVD | `MetroDrip_Pixel_API36`, Google APIs x86_64, 10 GB data | `emulator -list-avds` |
| Host | Hardware virtualisation and about 15 GB free | OS-specific check |

### Windows automated path

From the repository root in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-android-emulator.ps1
```

The idempotent script installs the required SDK packages under
`%LOCALAPPDATA%\Android\Sdk`, sets `ANDROID_HOME`/`ANDROID_SDK_ROOT`, accepts
licenses, creates the exact AVD, and repairs its target/tag metadata. It refuses
a Java version other than 17. Restart Antigravity after the first run so it
inherits the new environment variables.

### Linux and macOS Android path

Use Android Studio's SDK Manager to install Android SDK Platform 36, Build Tools
36.0.0, Platform Tools, Emulator, and the API 36 Google APIs x86_64 image. In
Device Manager create a Pixel 7-class device named exactly
`MetroDrip_Pixel_API36`, give it a 10 GB data partition, and enable hardware
keyboard input.

### Install project dependencies

From `mobile/`:

```bash
npm ci
cp .env.example .env          # PowerShell: Copy-Item .env.example .env
```

Native projects are generated from `app.json` through Expo Continuous Native
Generation. `android/` and `ios/` are ignored outputs; do not put durable edits
inside them.

## 2. Daily run

The one-click Android path is:

**Terminal → Run Task… → `MetroDrip: Full mobile stack`**

It waits for healthy MySQL/Redis, starts Django with simulated payments, polls
the database-backed readiness endpoint, starts only the named AVD on
`emulator-5554`, waits for `sys.boot_completed=1` and the boot animation to
stop, then builds/installs MetroDrip on that verified AVD.

The same flow by hand uses four terminals:

```bash
# 1. Repository root: data services
docker compose up -d db redis --wait

# 2. Repository root: device-reachable API
PAYMENT_PROVIDER=simulated .venv/bin/python manage.py runserver 0.0.0.0:8080

# 3. Repository root: exact named emulator and bounded readiness check
.venv/bin/python scripts/launch-android-emulator.py \
  --avd MetroDrip_Pixel_API36 --port 5554 --timeout 240

# 4. mobile/: first native build/install and deterministic Metro connection
npm run android:emulator
```

PowerShell uses:

```powershell
$env:PAYMENT_PROVIDER="simulated"
.\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8080
.\.venv\Scripts\python.exe scripts\launch-android-emulator.py `
  --avd MetroDrip_Pixel_API36 --port 5554 --timeout 240
Set-Location mobile
npm run android:emulator
```

After the native development client is installed, emulator JavaScript-only sessions use
`npm run start:android:emulator`. The command validates `emulator-5554`, restores and verifies
`adb reverse tcp:8081 tcp:8081`, starts localhost Metro, and opens the exact development-client
URL. Re-run `npm run android:emulator` after changing Expo plugins, native settings, or native
dependencies. `npm start` is deliberately retained for LAN-connected physical devices.

Both emulator commands first call the database-backed host readiness URL
`http://127.0.0.1:8080/healthz/ready/`. If MySQL or Django is unavailable, they stop before
building or opening the app and print the cross-platform startup commands. To exercise the real
saved-content/offline state on purpose, bypass only this gate:

```bash
npm run start:android:emulator -- --allow-offline
```

ADB reverse rules disappear when the emulator or ADB server restarts. Expo's development launcher
also remembers prior LAN URLs. The emulator commands recreate the rule every time and bypass saved
history without clearing the app's session, cart, or other data.

## 3. API address and local-network behavior

The emulator is a virtual machine. Its `127.0.0.1` is not the host, while
Android maps **`10.0.2.2`** to the host loopback. Django must bind
`0.0.0.0:8080`.

| Target | `EXPO_PUBLIC_API_URL` |
|---|---|
| Android emulator | `http://10.0.2.2:8080/api/mobile/v1` |
| iOS simulator on macOS | `http://localhost:8080/api/mobile/v1` |
| Physical device on the same Wi-Fi | `http://<host-LAN-IP>:8080/api/mobile/v1` |

For physical devices, `config/settings/dev.py` adds the host's LAN addresses to
`ALLOWED_HOSTS` when it can resolve them. If Django returns a 400 naming the
host, add only that development address. iOS also displays the local-network
permission text configured in `app.json`; deny means the local API cannot be
reached until the permission is restored in Settings.

## 4. Verify the integrated flows

First confirm infrastructure:

```bash
docker compose ps
curl http://127.0.0.1:8080/healthz/ready/
adb -s emulator-5554 shell getprop sys.boot_completed
adb -s emulator-5554 emu avd name
```

Expect healthy MySQL/Redis, `{"status": "ok"}`, boot value `1`, and AVD name
`MetroDrip_Pixel_API36`.

Then check both ownership paths:

1. **Guest:** Continue as guest → product → select size/colour/fit → Cart →
   Checkout → Pay. Public Order Tracking must reach **Paid**. No notification
   or account order is expected because the order has no customer.
2. **Signed in:** sign in before checkout and repeat the purchase. Tracking must
   reach **Paid**; Home → bell → Notifications must show **Order confirmed**;
   the same order number must appear in `/merchant/` → Orders.

Simulated in-app delivery proves the application's notification lifecycle. It
does not prove Android system push; that additionally requires a real EAS
project ID, push credentials, `PUSH_PROVIDER=expo`, and a physical/internal
build environment.

## 5. What the IDE tasks do

| Task | Purpose |
|---|---|
| `MetroDrip: MySQL + Redis (docker)` | Starts both services with Compose `--wait` and a bounded timeout |
| `MetroDrip: Django API (0.0.0.0:8080)` | Runs the device-reachable API with explicit simulated payments |
| `MetroDrip: Wait for Django API` | Polls `/healthz/ready/` until the database-backed check returns 200 |
| `MetroDrip: Start and verify Android emulator` | Starts the exact API 36 AVD on port 5554 and waits for full boot |
| `MetroDrip: Expo on Android` | Builds/installs, restores the 8081 reverse mapping, and opens localhost Metro on the verified AVD |
| `MetroDrip: Full mobile stack` | Executes the complete dependency graph |
| `MetroDrip: Backend QA` | Runs Ruff and pytest |
| `MetroDrip: Mobile typecheck` | Runs strict TypeScript checking |

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `emulator: command not found` | SDK path was not inherited | Restart the terminal/editor; verify `ANDROID_HOME` |
| Setup script rejects Java | JDK is not version 17 | Select JDK 17 before rerunning the script |
| AVD is not installed | Name or API image differs | Create/run `MetroDrip_Pixel_API36`; do not silently substitute another AVD |
| Reserved port has another AVD | `emulator-5554` belongs to a personal device | Stop it yourself; the helper intentionally refuses to kill or reuse it |
| `adb` stays `offline` | Guest has not completed boot or virtualisation is unhealthy | Wait; then inspect the emulator window/log. Use a physical device if the host cannot virtualise |
| Launcher says `MetroDrip API is not ready` | Django or its MySQL dependency is stopped/unready | From the repository root run `docker compose up -d --wait db redis`, start Django on `0.0.0.0:8080` as printed, then rerun the emulator command |
| App shows the offline banner after bypassing the gate | Intentional offline mode, API binding/address mismatch, or wrong target URL | Remove `--allow-offline`; bind Django to `0.0.0.0:8080`; use `10.0.2.2` in the emulator |
| `HTTP 400 missing_client_version` | Code bypassed `src/api/client.ts` | Route every mobile API call through the shared client |
| “Failed to connect to /192.168…:8081” | The launcher reopened a saved LAN URL while Metro listens on localhost, or an emulator restart removed ADB reverse | Run `npm run start:android:emulator`; do not clear app data |
| Metro says no development build is installed | Only the bundler was started | Run `npm run android:emulator` once, then use `npm run start:android:emulator` |
| Bundle is stale | Metro cache | Stop Metro and run `npm run start:android:emulator -- --clear` |
| Port 8081 belongs to another project or host mode | A foreign or LAN-mode Metro process is already running | Stop that process; the helper refuses to reuse an incompatible manifest |
| Doctor reports native/config drift | Generated native output is stale or hand-edited | Recreate the ignored native directory with a clean prebuild |
| Checkout succeeds but Notifications is empty | Purchase was made as a guest | Sign in before checkout; guest notifications are deliberately skipped |
| Order is absent from `/admin/` | Orders belong to the merchant console | Verify the matching order number under `/merchant/` |

Do not solve emulator problems by deleting an arbitrary AVD or project data.
Confirm the exact target first; the helper's refusal messages are designed to
make the safe recovery path explicit.

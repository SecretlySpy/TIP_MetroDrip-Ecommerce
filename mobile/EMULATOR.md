# Running the MetroDrip app in Antigravity IDE

Antigravity is VS Code-based, so it uses this repo's `.vscode/` tasks and
extension recommendations directly. This guide gets an Android emulator running
the app against your local Django API.

---

## 1. One-time setup

From the repo root, in a PowerShell terminal:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-android-emulator.ps1
```

The script is idempotent — re-run it safely if a step fails. It:

1. Installs the Android command-line tools to `%LOCALAPPDATA%\Android\Sdk`
2. Sets `ANDROID_HOME` / `ANDROID_SDK_ROOT` and extends your user `Path`
3. Accepts the SDK licences
4. Installs `platform-tools`, `emulator`, `platforms;android-34`, and the
   `google_apis;x86_64` system image
5. Creates the **`MetroDrip_Pixel7_API34`** AVD and tunes it to 2 GB RAM /
   6 GB data / hardware keyboard

**Restart Antigravity afterwards** so it inherits `ANDROID_HOME`.

### Prerequisites

| Requirement | Why | Check |
|---|---|---|
| JDK 17+ | `sdkmanager` and `avdmanager` are Java tools | `java -version` |
| ~10 GB free disk | SDK + system image + AVD data | — |
| Virtualisation enabled in BIOS | x86_64 emulator needs WHPX/HAXM | `systeminfo` → Hyper-V requirements |

> If your CPU cannot virtualise, use a physical device instead: enable USB
> debugging, plug it in, and run `npm run android`. Everything else is identical.

---

## 2. Daily run

The fastest path is the bundled task:

**Terminal → Run Task… → `MetroDrip: Full mobile stack`**

That runs, in order: Docker (MySQL + Redis) → Django on `0.0.0.0:8080` →
emulator → Expo. Or do it by hand in three terminals:

```powershell
# 1. API — must bind 0.0.0.0, not 127.0.0.1, or the emulator cannot reach it
$env:PAYMENT_PROVIDER="simulated"
.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8080

# 2. Emulator
emulator -avd MetroDrip_Pixel7_API34

# 3. App
cd mobile
npm run android
```

### Why `0.0.0.0` and `10.0.2.2`

The emulator is a virtual machine with its own loopback. `127.0.0.1` inside it
means *the emulator*, not your PC. Android's emulator maps **`10.0.2.2`** to the
host's loopback, which is why `mobile/.env.example` ships:

```
EXPO_PUBLIC_API_URL=http://10.0.2.2:8080/api/mobile/v1
```

A server bound to `127.0.0.1` will refuse that connection, so bind `0.0.0.0`.

| Target | `EXPO_PUBLIC_API_URL` |
|---|---|
| Android emulator | `http://10.0.2.2:8080/api/mobile/v1` |
| iOS simulator (macOS) | `http://localhost:8080/api/mobile/v1` |
| Physical device (same Wi-Fi) | `http://<your-LAN-IP>:8080/api/mobile/v1` |

For a physical device you must also add your LAN IP to `ALLOWED_HOSTS` in
`config/settings/dev.py`.

---

## 3. Verifying it works

Once the app loads you should be able to complete a full purchase, because the
dev server runs the **simulated** payment provider:

1. Splash → *Continue as guest* (or create an account)
2. Home → tap a product → pick size / colour / fit → **Add to Cart**
3. Cart → **Checkout** → fill the form → pick a zone → **Pay**
4. The app lands on Order Tracking with the timeline at *Paid*
5. Sign in and check **Orders** — the notification centre shows
   "Order confirmed"

If step 3 fails with a network error, the API binding is wrong — see above.

---

## 4. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `emulator: command not found` | `Path` not reloaded | Restart Antigravity / the terminal |
| Emulator hangs on the boot logo | Virtualisation off | Enable it in BIOS; or use a physical device |
| App shows the offline banner | API not reachable | Bind `0.0.0.0:8080`; confirm `10.0.2.2` in `.env` |
| `HTTP 400 missing_client_version` | Request bypassed the API client | All calls must go through `src/api/client.ts` |
| Metro cache weirdness after edits | Stale bundler cache | `npx expo start -c` |
| `adb devices` empty | Emulator not booted yet | Wait for the home screen, then re-run |

---

## 5. What the IDE tasks do

| Task | Purpose |
|---|---|
| `MetroDrip: MySQL + Redis (docker)` | Brings up the data services |
| `MetroDrip: Django API (0.0.0.0:8080)` | Emulator-reachable API, simulated payments |
| `MetroDrip: Start Android emulator` | Boots the AVD |
| `MetroDrip: Expo on Android` | Metro bundler + installs the app |
| `MetroDrip: Full mobile stack` | All of the above, in order |
| `MetroDrip: Backend QA` | ruff + pytest |
| `MetroDrip: Mobile typecheck` | `tsc --noEmit` |

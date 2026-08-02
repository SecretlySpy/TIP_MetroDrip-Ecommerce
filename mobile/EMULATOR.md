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
4. Installs `platform-tools`, `emulator`, `platforms;android-35`, and the
   `google_apis;x86_64` system image
5. Creates the **`MetroDrip_Pixel_API35`** AVD and tunes it to 2 GB RAM /
   6 GB data / hardware keyboard

> **Why API 35 and not 34.** Expo Go 2.31.2 — the client for SDK 51, which
> this app targets — crashes on boot on the `android-34;google_apis` image
> with `Failed to create NativeModule 'UIManager'` and
> `host.exp.exponent.MainApplication cannot be cast to
> com.facebook.react.ReactApplication`. The identical APK and JS bundle run
> fine on API 35. Verified on this machine; don't "simplify" the script back
> to 34.

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
emulator -avd MetroDrip_Pixel_API35

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
| Expo Go dies instantly; logcat shows `Failed to create NativeModule 'UIManager'` | Running an API 34 image, or `react-native-reanimated/plugin` missing from `babel.config.js` | Use the API 35 AVD; keep the Reanimated plugin **last** in the Babel plugin list |
| "Expo Go isn't responding" (ANR) | Two emulators competing for CPU | Run one at a time: `adb -s emulator-XXXX emu kill` |
| Expo opens the *wrong* emulator | Expo CLI takes the first `adb` device and ignores `ANDROID_SERIAL` | Boot only the MetroDrip AVD, or install Expo Go manually and deep-link: `adb -s <serial> shell am start -a android.intent.action.VIEW -d 'exp://10.0.2.2:8090' host.exp.exponent` |
| `adb devices` shows `offline` forever; qemu is running and the log stops after "Windows Hypervisor Platform accelerator is operational" | `config.ini` has empty `target` / `tag.ids` — the emulator cannot resolve its own system image, and fails silently rather than erroring | Re-run `scripts/setup-android-emulator.ps1` (it now writes those keys explicitly), or set `target=android-35`, `tag.id=google_apis`, `tag.ids=google_apis` by hand and boot with `-wipe-data` |
| Emulator dies the moment the launching shell exits | The emulator is a child of that shell's process group | Launch it detached — the IDE task does this; from a script use `cmd /c start "" /MIN <batch that runs emulator.exe>` |
| *Every* AVD suddenly hangs at `offline` or exits silently right after the log line "Windows Hypervisor Platform accelerator is operational" — including AVDs that booted fine earlier | Windows Hypervisor Platform gets into a bad state, typically after an emulator process is `taskkill`/`Stop-Process -Force`ed several times. Docker Desktop's WSL2 VM shares the same hypervisor and can aggravate it | **Reboot the host.** Nothing short of that reliably clears it. Afterwards, stop emulators with `adb -s <serial> emu kill` rather than killing the process, and prefer running the emulator and Docker one at a time on a machine with limited RAM |

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

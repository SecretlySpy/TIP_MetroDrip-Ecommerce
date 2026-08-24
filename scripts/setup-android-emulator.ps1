<#
.SYNOPSIS
    Install the Android SDK pieces MetroDrip's Expo app needs and create the
    MetroDrip_Pixel_API36 emulator.

.DESCRIPTION
    Idempotent: every step checks for existing state first, so re-running it
    after a partial failure is safe. Requires JDK 17 through JAVA_HOME
    (preferred) or PATH.

    Installs into %LOCALAPPDATA%\Android\Sdk:
      * cmdline-tools;latest   - sdkmanager / avdmanager
      * platform-tools         - adb
      * emulator               - the emulator binary
      * platforms;android-36   - Android 16 SDK
      * build-tools;36.0.0     - Android build and packaging tools
      * system-images;android-36;google_apis;x86_64 - the AVD's system image

    API 36 is the emulator and target SDK; the app itself supports Android 7.0
    (API 24) and up.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\setup-android-emulator.ps1
#>

[CmdletBinding()]
param(
    [string]$AvdName = "MetroDrip_Pixel_API36",
    [string]$ApiLevel = "36",
    [string]$BuildToolsVersion = "36.0.0",
    [string]$Device = "pixel_7"
)

$ErrorActionPreference = "Stop"

$Sdk = Join-Path $env:LOCALAPPDATA "Android\Sdk"
$CmdlineBin = Join-Path $Sdk "cmdline-tools\latest\bin"
$SdkManager = Join-Path $CmdlineBin "sdkmanager.bat"
$AvdManager = Join-Path $CmdlineBin "avdmanager.bat"
$SystemImage = "system-images;android-$ApiLevel;google_apis;x86_64"

function Write-Step($message) { Write-Host "`n=== $message ===" -ForegroundColor Cyan }

# --- 0. Prerequisites ---------------------------------------------------------
Write-Step "Checking prerequisites"
# Gradle prefers JAVA_HOME over PATH, so validate the same runtime it will use.
if ($env:JAVA_HOME) {
    $JavaCommand = Join-Path $env:JAVA_HOME "bin\java.exe"
    $JavacCommand = Join-Path $env:JAVA_HOME "bin\javac.exe"
    if (-not (Test-Path $JavaCommand) -or -not (Test-Path $JavacCommand)) {
        throw "JAVA_HOME must point to a complete JDK containing bin\java.exe and bin\javac.exe."
    }
} else {
    $java = Get-Command java -ErrorAction SilentlyContinue
    $javac = Get-Command javac -ErrorAction SilentlyContinue
    if (-not $java -or -not $javac) {
        throw "JDK 17 is required on PATH (both java and javac), or set JAVA_HOME to it."
    }
    $JavaCommand = $java.Source
    $JavacCommand = $javac.Source
    if ((Split-Path $JavaCommand -Parent) -ne (Split-Path $JavacCommand -Parent)) {
        throw "PATH resolves java and javac from different directories. Set JAVA_HOME to one JDK 17 installation."
    }
}
# `java -version` prints to stderr even on success, which $ErrorActionPreference
# = "Stop" would turn into a terminating error. Read the banner with stderr
# redirection explicitly relaxed.
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$javaVersion = (& $JavaCommand -version 2>&1 | Select-Object -First 1)
$ErrorActionPreference = $previousPreference
Write-Host "Java: $javaVersion"
if ($javaVersion -notmatch 'version\s+"?(\d+)') {
    throw "Could not determine the JDK version from: $javaVersion"
}
if ([int]$Matches[1] -ne 17) {
    throw "MetroDrip's Android toolchain requires JDK 17; found JDK $($Matches[1])."
}
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$javacVersion = (& $JavacCommand -version 2>&1 | Select-Object -First 1)
$ErrorActionPreference = $previousPreference
Write-Host "Compiler: $javacVersion"
if ($javacVersion -notmatch 'javac\s+(\d+)') {
    throw "Could not determine the compiler version from: $javacVersion"
}
if ([int]$Matches[1] -ne 17) {
    throw "MetroDrip's Android toolchain requires javac 17; found javac $($Matches[1])."
}

# --- 1. Command-line tools ----------------------------------------------------
Write-Step "Android command-line tools"
if (Test-Path $SdkManager) {
    Write-Host "Already installed at $CmdlineBin"
} else {
    $zip = Join-Path $env:TEMP "commandlinetools.zip"
    $url = "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip"
    if (-not (Test-Path $zip)) {
        Write-Host "Downloading $url ..."
        Invoke-WebRequest $url -OutFile $zip -UseBasicParsing
    }
    New-Item -ItemType Directory -Force -Path (Join-Path $Sdk "cmdline-tools") | Out-Null
    Expand-Archive -Path $zip -DestinationPath (Join-Path $Sdk "cmdline-tools") -Force
    $unpacked = Join-Path $Sdk "cmdline-tools\cmdline-tools"
    if (Test-Path $unpacked) {
        # The archive nests its own cmdline-tools/ dir; sdkmanager requires it
        # to sit at cmdline-tools/latest/ or it cannot resolve its own root.
        $latest = Join-Path $Sdk "cmdline-tools\latest"
        if (Test-Path $latest) { Remove-Item $latest -Recurse -Force }
        Move-Item $unpacked $latest
    }
    Write-Host "Installed to $CmdlineBin"
}

# --- 2. Environment variables -------------------------------------------------
Write-Step "Environment variables (user scope)"
[Environment]::SetEnvironmentVariable("ANDROID_HOME", $Sdk, "User")
[Environment]::SetEnvironmentVariable("ANDROID_SDK_ROOT", $Sdk, "User")
$env:ANDROID_HOME = $Sdk
$env:ANDROID_SDK_ROOT = $Sdk

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
foreach ($dir in @("$Sdk\platform-tools", "$Sdk\emulator", $CmdlineBin)) {
    if ($userPath -notlike "*$dir*") {
        $userPath = "$userPath;$dir"
    }
}
[Environment]::SetEnvironmentVariable("Path", $userPath, "User")
$env:Path = "$env:Path;$Sdk\platform-tools;$Sdk\emulator;$CmdlineBin"
Write-Host "ANDROID_HOME = $Sdk"

# --- 3. Licenses --------------------------------------------------------------
# Piping "y" into sdkmanager.bat does not work reliably on Windows — the batch
# wrapper re-reads the console rather than stdin, so the prompt is left
# unanswered and every package silently fails to install. Writing the accepted
# licence hashes directly is what CI images do, and it is deterministic.
Write-Step "Accepting SDK licenses"
$LicenseHashes = @{
    "android-sdk-license"          = @(
        "24333f8a63b6825ea9c5514f83c2829b004d1fee",
        "8933bad161af4178b1185d1a37fbf41ea5269c55",
        "d56f5187479451eabf01fb78af6dfcb131a6481e"
    )
    "android-sdk-preview-license"  = @("84831b9409646a918e30573bab4c9c91346d8abd")
    "android-sdk-arm-dbt-license"  = @("859f317696f67ef3d7f30a50a5560e7834b43903")
    "android-googletv-license"     = @("601085b94cd77f0b54ff86406957099ebe79c4d6")
    "google-gdk-license"           = @("33b6a2b64607f11b759f320ef9dff4ae5c47d97a")
    "intel-android-extra-license"  = @("d975f751698a77b662f1254ddbeed3901e976f5a")
    "mips-android-sysimage-license" = @("e9acab5b5fbb560a72cfaecce8946896ff6aab9d")
}
$licenseDir = Join-Path $Sdk "licenses"
New-Item -ItemType Directory -Force -Path $licenseDir | Out-Null
foreach ($license in $LicenseHashes.GetEnumerator()) {
    $path = Join-Path $licenseDir $license.Key
    # sdkmanager matches on exact file content, so write LF-joined hashes with
    # no trailing newline and no BOM.
    [IO.File]::WriteAllText($path, ($license.Value -join "`n"), [Text.UTF8Encoding]::new($false))
}
Write-Host "Wrote $($LicenseHashes.Count) licence files to $licenseDir"

# --- 3b. Self-update the command-line tools ------------------------------------
# The bootstrap zip pinned above ships an avdmanager that only understands SDK
# repository XML up to version 3. Current system images publish version 4, and
# the mismatch is NOT fatal — avdmanager prints a warning and then writes an
# AVD config with `target`, `tag.ids`, and `tag.displaynames` left EMPTY. Such
# an AVD starts qemu and then hangs at `offline` forever. Upgrading the tools
# first is what actually prevents that.
Write-Step "Updating command-line tools to the current release"
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$xmlWarning = & $AvdManager list target 2>&1 | Select-String -Pattern 'only understands SDK XML'
if ($xmlWarning) {
    Write-Host "Bootstrap tools are stale; installing cmdline-tools;latest ..."
    & $SdkManager --install "cmdline-tools;latest" --sdk_root="$Sdk" 2>&1 |
        Where-Object { $_ -notmatch '^\[=*\s*\]' -and $_ -notmatch '^\s*$' } | Select-Object -Last 2
    # sdkmanager refuses to overwrite the directory it is running from and
    # drops the new build in `latest-2`; move it into place.
    $staged = Join-Path $Sdk "cmdline-tools\latest-2"
    if (Test-Path $staged) {
        Remove-Item (Join-Path $Sdk "cmdline-tools\latest") -Recurse -Force
        Move-Item $staged (Join-Path $Sdk "cmdline-tools\latest")
        Write-Host "Command-line tools updated."
    }
} else {
    Write-Host "Command-line tools are current."
}
$ErrorActionPreference = $previousPreference

# --- 4. Packages --------------------------------------------------------------
Write-Step "Installing SDK packages (this is the long part)"
# package name -> a path that must exist afterwards, so a silent failure is
# caught here instead of surfacing later as avdmanager's opaque
# "Cannot invoke SystemImage.getPackage() because img is null".
$packages = [ordered]@{
    "platform-tools"                = "platform-tools\adb.exe"
    "emulator"                      = "emulator\emulator.exe"
    "platforms;android-$ApiLevel"   = "platforms\android-$ApiLevel"
    "build-tools;$BuildToolsVersion" = "build-tools\$BuildToolsVersion\aapt2.exe"
    $SystemImage                    = "system-images\android-$ApiLevel\google_apis\x86_64"
}
foreach ($package in $packages.GetEnumerator()) {
    $marker = Join-Path $Sdk $package.Value
    if (Test-Path $marker) {
        Write-Host "-> $($package.Key) (already installed)"
        continue
    }
    Write-Host "-> $($package.Key)"
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $SdkManager --install $package.Key --sdk_root="$Sdk" 2>&1 |
        Where-Object { $_ -notmatch '^\[=*\s*\]' -and $_ -notmatch '^\s*$' } |
        Select-Object -Last 2
    $ErrorActionPreference = $previousPreference
    if (-not (Test-Path $marker)) {
        throw "Package '$($package.Key)' did not install (expected $marker). " +
              "Re-run this script; if it persists, run: `"$SdkManager`" --list"
    }
}

# --- 5. AVD -------------------------------------------------------------------
Write-Step "Creating AVD '$AvdName'"
$existing = & $AvdManager list avd 2>&1 | Select-String -Pattern "Name: $AvdName"
if ($existing) {
    Write-Host "AVD already exists."
} else {
    "no" | & $AvdManager create avd --name $AvdName --package "$SystemImage" --device $Device --force 2>&1 |
        Select-Object -Last 3
    Write-Host "Created."
}

# Repair and tune the generated config.
#
# `avdmanager create` can leave `target`, `tag.ids`, and `tag.displaynames`
# EMPTY. The emulator then cannot resolve its own system image at boot: qemu
# starts, WHPX reports "operational", and the device sits at `offline` in
# `adb devices` forever with no error. Writing them explicitly is the fix —
# do not drop this block.
#
# Sizes must carry a unit suffix ("2G", not "2048"); a bare number is
# misparsed. Values leave enough space for an Expo development build.
$avdConfig = Join-Path $env:USERPROFILE ".android\avd\$AvdName.avd\config.ini"
if (Test-Path $avdConfig) {
    $config = Get-Content $avdConfig
    $tuned = [ordered]@{
        # Identity the emulator needs to find its system image.
        "target"                  = "android-$ApiLevel"
        "tag.id"                  = "google_apis"
        "tag.ids"                 = "google_apis"
        "tag.display"             = "Google APIs"
        "tag.displaynames"        = "Google APIs"
        # Headroom for a React Native debug build.
        "hw.ramSize"              = "2G"
        "vm.heapSize"             = "228M"
        "disk.dataPartition.size" = "10G"
        "hw.keyboard"             = "yes"
        # Host GPU emulation is a common cause of a black or hung first boot
        # on Windows; the emulator picks a working renderer on its own.
        "hw.gpu.enabled"          = "no"
    }
    foreach ($key in $tuned.Keys) {
        $escaped = [regex]::Escape($key)
        if ($config -match "^$escaped=") {
            $config = $config -replace "^$escaped=.*", "$key=$($tuned[$key])"
        } else {
            $config += "$key=$($tuned[$key])"
        }
    }
    Set-Content -Path $avdConfig -Value ($config | Sort-Object) -Encoding ascii
    Write-Host "Repaired + tuned $avdConfig (target/tags set, 2 GB RAM, 10 GB data)."
}

Write-Step "Done"
Write-Host @"
Next steps:

  1. Restart Antigravity IDE so it picks up ANDROID_HOME.
  2. Run the Django API bound to all interfaces:
       .venv\Scripts\python.exe manage.py runserver 0.0.0.0:8080
  3. Boot the emulator:
       emulator -avd $AvdName
  4. Start the app:
       cd mobile && npm run android

  In Antigravity: Terminal > Run Task... > "MetroDrip: Full mobile stack"
  does steps 1-4 in one go.

  The emulator reaches the host at 10.0.2.2, which is already the default in
  mobile/.env.example (EXPO_PUBLIC_API_URL).
"@

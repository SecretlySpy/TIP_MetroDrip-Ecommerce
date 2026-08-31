#!/usr/bin/env node

/**
 * Start MetroDrip's development client on the one supported Android emulator.
 *
 * Expo's development launcher remembers previously opened URLs. A LAN launch
 * followed by a localhost-only Metro process can therefore reopen an address
 * that has no listener. This helper makes the emulator transport explicit:
 * emulator localhost:8081 is reversed to host localhost:8081 on every run,
 * and the exact loopback development-client URL is opened deliberately.
 */

import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const ANDROID_SERIAL = 'emulator-5554';
export const AVD_NAME = 'MetroDrip_Pixel_API36';
export const APP_ID = 'ph.metrodrip.app';
export const METRO_HOST = '127.0.0.1';
export const METRO_PORT = 8081;
export const METRO_ORIGIN = `http://${METRO_HOST}:${METRO_PORT}`;
export const API_HEALTH_URL = 'http://127.0.0.1:8080/healthz/ready/';

const SCRIPT_DIRECTORY = dirname(fileURLToPath(import.meta.url));
const MOBILE_ROOT = resolve(SCRIPT_DIRECTORY, '..');
const EXPO_CLI = join(MOBILE_ROOT, 'node_modules', 'expo', 'bin', 'cli');

export function developmentClientUrl(origin = METRO_ORIGIN) {
  return `exp+metrodrip://expo-development-client/?url=${encodeURIComponent(origin)}`;
}

export function findAdb({ env = process.env, platform = process.platform } = {}) {
  const executable = platform === 'win32' ? 'adb.exe' : 'adb';
  const roots = [env.ANDROID_HOME, env.ANDROID_SDK_ROOT].filter(Boolean);

  for (const root of roots) {
    const candidate = join(root, 'platform-tools', executable);
    if (existsSync(candidate)) {
      return candidate;
    }
  }

  return executable;
}

function defaultRun(command, args, options = {}) {
  return spawnSync(command, args, {
    cwd: MOBILE_ROOT,
    encoding: 'utf8',
    env: process.env,
    ...options,
  });
}

function checkedRun(run, command, args, label) {
  const result = run(command, args);
  if (result.error) {
    throw new Error(`${label}: ${result.error.message}`);
  }
  if (result.status !== 0) {
    const detail = (result.stderr || result.stdout || '').trim();
    throw new Error(`${label}${detail ? `: ${detail}` : ''}`);
  }
  return (result.stdout || '').trim();
}

export function assertDedicatedEmulator({ adb = findAdb(), run = defaultRun } = {}) {
  const state = checkedRun(
    run,
    adb,
    ['-s', ANDROID_SERIAL, 'get-state'],
    `${ANDROID_SERIAL} is unavailable`,
  );
  if (state !== 'device') {
    throw new Error(`${ANDROID_SERIAL} is in state '${state}', not 'device'.`);
  }

  const avdOutput = checkedRun(
    run,
    adb,
    ['-s', ANDROID_SERIAL, 'emu', 'avd', 'name'],
    `Could not identify the AVD on ${ANDROID_SERIAL}`,
  );
  const runningAvd = avdOutput
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find((line) => line && line !== 'OK');
  if (runningAvd !== AVD_NAME) {
    throw new Error(
      `${ANDROID_SERIAL} is running '${runningAvd || 'an unknown AVD'}', not '${AVD_NAME}'.`,
    );
  }

  const bootCompleted = checkedRun(
    run,
    adb,
    ['-s', ANDROID_SERIAL, 'shell', 'getprop', 'sys.boot_completed'],
    'Could not read Android boot status',
  );
  const bootAnimation = checkedRun(
    run,
    adb,
    ['-s', ANDROID_SERIAL, 'shell', 'getprop', 'init.svc.bootanim'],
    'Could not read Android boot-animation status',
  );
  if (bootCompleted !== '1' || bootAnimation !== 'stopped') {
    throw new Error(
      `${AVD_NAME} is not fully booted (sys.boot_completed=${bootCompleted || 'empty'}, ` +
        `bootanim=${bootAnimation || 'empty'}).`,
    );
  }

  return { adb, serial: ANDROID_SERIAL, avd: AVD_NAME };
}

export function ensureMetroReverse({ adb = findAdb(), run = defaultRun } = {}) {
  const endpoint = `tcp:${METRO_PORT}`;
  checkedRun(
    run,
    adb,
    ['-s', ANDROID_SERIAL, 'reverse', endpoint, endpoint],
    `Could not reverse emulator ${endpoint} to the host`,
  );
  const mappings = checkedRun(
    run,
    adb,
    ['-s', ANDROID_SERIAL, 'reverse', '--list'],
    'Could not verify ADB reverse mappings',
  );
  const hasMapping = mappings.split(/\r?\n/).some((line) => {
    const fields = line.trim().split(/\s+/);
    return fields.length >= 3 && fields.at(-2) === endpoint && fields.at(-1) === endpoint;
  });
  if (!hasMapping) {
    throw new Error(`ADB did not retain the required ${endpoint} reverse mapping.`);
  }
}

export function isCompatibleMetroManifest(manifest) {
  const client = manifest?.extra?.expoClient;
  if (
    client?.name !== 'MetroDrip' ||
    client?.slug !== 'metrodrip' ||
    client?.android?.package !== APP_ID ||
    client?.hostUri !== `${METRO_HOST}:${METRO_PORT}`
  ) {
    return false;
  }

  try {
    return new URL(manifest.launchAsset.url).origin === METRO_ORIGIN;
  } catch {
    return false;
  }
}

export async function inspectMetro({ fetchImpl = fetch, timeoutMs = 800 } = {}) {
  try {
    const response = await fetchImpl(`${METRO_ORIGIN}/`, {
      headers: {
        'expo-platform': 'android',
        'expo-runtime-version': 'exposdk:57.0.0',
      },
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) {
      return { state: 'conflict', reason: `HTTP ${response.status}` };
    }
    const manifest = await response.json();
    return isCompatibleMetroManifest(manifest)
      ? { state: 'compatible' }
      : { state: 'conflict', reason: 'the Expo manifest belongs to another project or host mode' };
  } catch (error) {
    if (
      error?.name === 'AbortError' ||
      error?.name === 'TimeoutError' ||
      error?.cause?.code === 'ECONNREFUSED'
    ) {
      return { state: 'absent' };
    }
    return { state: 'conflict', reason: `the listener did not return a valid Expo manifest (${error.message})` };
  }
}

export async function inspectApi({ fetchImpl = fetch, timeoutMs = 1_500 } = {}) {
  try {
    const response = await fetchImpl(API_HEALTH_URL, {
      headers: { 'User-Agent': 'MetroDrip-Android-launcher/1' },
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) {
      return { state: 'unavailable', reason: `readiness returned HTTP ${response.status}` };
    }
    const payload = await response.json().catch(() => null);
    if (payload?.status !== 'ok') {
      return { state: 'unavailable', reason: 'readiness did not return {"status":"ok"}' };
    }
    return { state: 'ready' };
  } catch (error) {
    if (error?.name === 'AbortError' || error?.name === 'TimeoutError') {
      return { state: 'unavailable', reason: `readiness timed out after ${timeoutMs}ms` };
    }
    if (error?.cause?.code === 'ECONNREFUSED') {
      return { state: 'unavailable', reason: 'nothing is listening on host port 8080' };
    }
    return {
      state: 'unavailable',
      reason: `readiness request failed (${error?.message || 'unknown network error'})`,
    };
  }
}

export async function assertApiReady(options = {}) {
  const api = await inspectApi(options);
  if (api.state === 'ready') {
    return;
  }
  throw new Error(
    `MetroDrip API is not ready at ${API_HEALTH_URL}: ${api.reason}.\n` +
      'From the repository root, start it with:\n' +
      '  docker compose up -d --wait db redis\n' +
      '  macOS/Linux: PAYMENT_PROVIDER=simulated .venv/bin/python manage.py runserver 0.0.0.0:8080\n' +
      '  Windows PowerShell: $env:PAYMENT_PROVIDER="simulated"; .venv\\Scripts\\python.exe manage.py runserver 0.0.0.0:8080\n' +
      "Use '--allow-offline' only when intentionally testing the app's offline UI.",
  );
}

function assertNoMetroConflict(metro) {
  if (metro.state === 'conflict') {
    throw new Error(
      `Port ${METRO_PORT} is already occupied, but ${metro.reason}. ` +
        'Stop that process before starting MetroDrip.',
    );
  }
}

export function shouldReuseExistingMetro(metro, { clear = false } = {}) {
  if (metro.state !== 'compatible') {
    return false;
  }
  if (clear) {
    throw new Error(
      `MetroDrip is already running on port ${METRO_PORT}. Stop it before using --clear.`,
    );
  }
  return true;
}

export function assertDevelopmentClientInstalled({ adb = findAdb(), run = defaultRun } = {}) {
  const result = run(adb, ['-s', ANDROID_SERIAL, 'shell', 'pm', 'path', APP_ID]);
  if (result.error || result.status !== 0 || !String(result.stdout || '').includes('package:')) {
    throw new Error(
      `MetroDrip is not installed on ${AVD_NAME}. Run 'npm run android:emulator' first.`,
    );
  }
}

export function openDevelopmentClient({ adb = findAdb(), run = defaultRun } = {}) {
  checkedRun(
    run,
    adb,
    [
      '-s',
      ANDROID_SERIAL,
      'shell',
      'am',
      'start',
      '-W',
      '-a',
      'android.intent.action.VIEW',
      '-d',
      developmentClientUrl(),
      APP_ID,
    ],
    'Could not open the MetroDrip development client',
  );
}

export function expoInstallArguments() {
  return ['run:android', '--device', AVD_NAME, '--no-bundler'];
}

export function expoStartArguments({ clear = false } = {}) {
  const argumentsList = [
    'start',
    '--dev-client',
    '--localhost',
    '--android',
    '--port',
    String(METRO_PORT),
  ];
  if (clear) {
    argumentsList.push('--clear');
  }
  return argumentsList;
}

export function expoEnvironment(env = process.env) {
  return {
    ...env,
    ANDROID_SERIAL,
    // `expo run:android` has no localhost flag and still opens a development
    // URL with --no-bundler. Pin that one generated URL to the reversed host.
    REACT_NATIVE_PACKAGER_HOSTNAME: METRO_HOST,
  };
}

function runExpoToCompletion(args) {
  const result = spawnSync(process.execPath, [EXPO_CLI, ...args], {
    cwd: MOBILE_ROOT,
    env: expoEnvironment(),
    stdio: 'inherit',
  });
  if (result.error) {
    throw new Error(`Expo failed to start: ${result.error.message}`);
  }
  if (result.status !== 0) {
    throw new Error(`Expo exited with status ${result.status}.`);
  }
}

function startExpo(args) {
  return spawn(process.execPath, [EXPO_CLI, ...args], {
    cwd: MOBILE_ROOT,
    env: expoEnvironment(),
    stdio: 'inherit',
  });
}

async function waitForMetro(child, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`Expo exited with status ${child.exitCode} before Metro became ready.`);
    }
    const metro = await inspectMetro({ timeoutMs: 500 });
    if (metro.state === 'compatible') {
      return;
    }
    if (metro.state === 'conflict') {
      throw new Error(`Port ${METRO_PORT} became incompatible: ${metro.reason}.`);
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 500));
  }
  throw new Error(`Timed out waiting for MetroDrip on ${METRO_ORIGIN}.`);
}

export function parseArguments(argv) {
  const allowed = new Set(['--install', '--clear', '--allow-offline']);
  const unknown = argv.filter((argument) => !allowed.has(argument));
  if (unknown.length) {
    throw new Error(
      `Unknown option(s): ${unknown.join(', ')}. ` +
        'Supported: --install, --clear, --allow-offline.',
    );
  }
  return {
    install: argv.includes('--install'),
    clear: argv.includes('--clear'),
    allowOffline: argv.includes('--allow-offline'),
  };
}

export async function main(argv = process.argv.slice(2)) {
  const { install, clear, allowOffline } = parseArguments(argv);
  if (!existsSync(EXPO_CLI)) {
    throw new Error("Expo is not installed. Run 'npm ci' inside mobile/ first.");
  }

  const { adb } = assertDedicatedEmulator();
  if (allowOffline) {
    console.warn('Skipping the Django readiness gate for an intentional offline-mode test.');
  } else {
    await assertApiReady();
    console.log(`MetroDrip API is ready at ${API_HEALTH_URL}.`);
  }
  let existingMetro = await inspectMetro();
  assertNoMetroConflict(existingMetro);

  ensureMetroReverse({ adb });

  if (install) {
    console.log(`Building and installing MetroDrip on ${AVD_NAME}...`);
    runExpoToCompletion(expoInstallArguments());
    ensureMetroReverse({ adb });
  } else {
    assertDevelopmentClientInstalled({ adb });
  }

  // A native build can take minutes, so do not trust the port state captured
  // before it. This also catches another process claiming 8081 during a build.
  existingMetro = await inspectMetro();
  assertNoMetroConflict(existingMetro);

  if (shouldReuseExistingMetro(existingMetro, { clear })) {
    openDevelopmentClient({ adb });
    console.log(`Connected ${AVD_NAME} to the existing MetroDrip server at ${METRO_ORIGIN}.`);
    return;
  }

  const child = startExpo(expoStartArguments({ clear }));
  try {
    await waitForMetro(child);
    ensureMetroReverse({ adb });
    openDevelopmentClient({ adb });
    console.log(`Connected ${AVD_NAME} to MetroDrip through ${METRO_ORIGIN}.`);
    await new Promise((resolvePromise, rejectPromise) => {
      child.once('error', rejectPromise);
      child.once('exit', (code, signal) => {
        if (signal || code === 0) {
          resolvePromise();
        } else {
          rejectPromise(new Error(`Expo exited with status ${code}.`));
        }
      });
    });
  } catch (error) {
    if (child.exitCode === null) {
      child.kill('SIGTERM');
    }
    throw error;
  }
}

const invokedDirectly = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (invokedDirectly) {
  main().catch((error) => {
    console.error(`Android development client failed: ${error.message}`);
    process.exitCode = 1;
  });
}

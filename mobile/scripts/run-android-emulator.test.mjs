import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  API_HEALTH_URL,
  APP_ID,
  assertApiReady,
  assertDedicatedEmulator,
  assertDevelopmentClientInstalled,
  developmentClientUrl,
  ensureMetroReverse,
  expoEnvironment,
  expoInstallArguments,
  expoStartArguments,
  inspectMetro,
  inspectApi,
  isCompatibleMetroManifest,
  openDevelopmentClient,
  parseArguments,
  shouldReuseExistingMetro,
} from './run-android-emulator.mjs';

function result(stdout = '', status = 0, stderr = '') {
  return { stdout, stderr, status };
}

test('package scripts separate emulator loopback from physical-device LAN mode', () => {
  const packageJson = JSON.parse(
    readFileSync(new URL('../package.json', import.meta.url), 'utf8'),
  );
  assert.equal(packageJson.scripts.start, 'expo start --dev-client');
  assert.equal(
    packageJson.scripts['android:emulator'],
    'node ./scripts/run-android-emulator.mjs --install',
  );
  assert.equal(
    packageJson.scripts['start:android:emulator'],
    'node ./scripts/run-android-emulator.mjs',
  );
});

function readyDeviceRun(command, args) {
  const joined = [command, ...args].join(' ');
  if (joined.endsWith('get-state')) return result('device\n');
  if (joined.endsWith('emu avd name')) return result('MetroDrip_Pixel_API36\nOK\n');
  if (joined.endsWith('getprop sys.boot_completed')) return result('1\n');
  if (joined.endsWith('getprop init.svc.bootanim')) return result('stopped\n');
  throw new Error(`Unexpected command: ${joined}`);
}

test('development-client URL explicitly targets reversed host loopback', () => {
  assert.equal(
    developmentClientUrl(),
    'exp+metrodrip://expo-development-client/?url=http%3A%2F%2F127.0.0.1%3A8081',
  );
});

test('start-only mode requires the installed client and opens the exact package URL', () => {
  assert.throws(
    () => assertDevelopmentClientInstalled({ adb: 'adb', run: () => result('', 1) }),
    /npm run android:emulator/,
  );

  let openArguments;
  openDevelopmentClient({
    adb: 'adb',
    run(_command, args) {
      openArguments = args;
      return result('Status: ok\n');
    },
  });
  assert.equal(openArguments.at(-1), APP_ID);
  assert.equal(openArguments.at(-2), developmentClientUrl());
});

test('first-install and JavaScript-only Expo commands stay separate', () => {
  assert.deepEqual(expoInstallArguments(), [
    'run:android',
    '--device',
    'MetroDrip_Pixel_API36',
    '--no-bundler',
  ]);
  assert.deepEqual(expoStartArguments(), [
    'start',
    '--dev-client',
    '--localhost',
    '--android',
    '--port',
    '8081',
  ]);
  assert.equal(expoStartArguments({ clear: true }).at(-1), '--clear');
  assert.deepEqual(expoEnvironment({ TEST_SENTINEL: 'kept' }), {
    TEST_SENTINEL: 'kept',
    ANDROID_SERIAL: 'emulator-5554',
    REACT_NATIVE_PACKAGER_HOSTNAME: '127.0.0.1',
  });
});

test('dedicated-emulator validation accepts only the fully booted named AVD', () => {
  assert.deepEqual(assertDedicatedEmulator({ adb: 'adb', run: readyDeviceRun }), {
    adb: 'adb',
    serial: 'emulator-5554',
    avd: 'MetroDrip_Pixel_API36',
  });
});

test('dedicated-emulator validation refuses a different AVD', () => {
  assert.throws(
    () =>
      assertDedicatedEmulator({
        adb: 'adb',
        run(command, args) {
          if (args.at(-1) === 'get-state') return result('device\n');
          if (args.slice(-3).join(' ') === 'emu avd name') return result('Personal_AVD\nOK\n');
          return readyDeviceRun(command, args);
        },
      }),
    /not 'MetroDrip_Pixel_API36'/,
  );
});

test('dedicated-emulator validation refuses an incomplete boot', () => {
  assert.throws(
    () =>
      assertDedicatedEmulator({
        adb: 'adb',
        run(command, args) {
          if (args.slice(-2).join(' ') === 'getprop sys.boot_completed') return result('0\n');
          return readyDeviceRun(command, args);
        },
      }),
    /not fully booted/,
  );
});

test('reverse setup must be visible in adb reverse --list', () => {
  const commands = [];
  ensureMetroReverse({
    adb: 'adb',
    run(_command, args) {
      commands.push(args);
      return args.at(-1) === '--list'
        ? result('host-12 tcp:8081 tcp:8081\n')
        : result('8081\n');
    },
  });
  assert.deepEqual(commands[0].slice(-3), ['reverse', 'tcp:8081', 'tcp:8081']);
});

test('reverse setup fails when adb does not retain the mapping', () => {
  assert.throws(
    () => ensureMetroReverse({ adb: 'adb', run: () => result('') }),
    /did not retain/,
  );
});

function manifest(overrides = {}) {
  return {
    launchAsset: { url: 'http://127.0.0.1:8081/node_modules/expo/AppEntry.bundle' },
    extra: {
      expoClient: {
        name: 'MetroDrip',
        slug: 'metrodrip',
        hostUri: '127.0.0.1:8081',
        android: { package: APP_ID },
        ...overrides,
      },
    },
  };
}

test('Metro reuse accepts only the MetroDrip loopback manifest', () => {
  assert.equal(isCompatibleMetroManifest(manifest()), true);
  assert.equal(isCompatibleMetroManifest(manifest({ hostUri: '192.168.31.232:8081' })), false);
  assert.equal(isCompatibleMetroManifest(manifest({ slug: 'another-project' })), false);
});

test('Metro inspection distinguishes no listener from a foreign listener', async () => {
  const refused = new TypeError('fetch failed', { cause: { code: 'ECONNREFUSED' } });
  assert.deepEqual(
    await inspectMetro({ fetchImpl: async () => Promise.reject(refused) }),
    { state: 'absent' },
  );

  const foreign = await inspectMetro({
    fetchImpl: async () => ({ ok: true, json: async () => manifest({ slug: 'foreign' }) }),
  });
  assert.equal(foreign.state, 'conflict');
});

test('API readiness accepts only the database-backed healthy response', async () => {
  let requestedUrl;
  assert.deepEqual(
    await inspectApi({
      fetchImpl: async (url) => {
        requestedUrl = url;
        return { ok: true, status: 200, json: async () => ({ status: 'ok' }) };
      },
    }),
    { state: 'ready' },
  );
  assert.equal(requestedUrl, API_HEALTH_URL);

  assert.deepEqual(
    await inspectApi({
      fetchImpl: async () => ({
        ok: false,
        status: 503,
        json: async () => ({ status: 'unavailable' }),
      }),
    }),
    { state: 'unavailable', reason: 'readiness returned HTTP 503' },
  );
});

test('API readiness failure names the server startup and intentional-offline paths', async () => {
  const refused = new TypeError('fetch failed', { cause: { code: 'ECONNREFUSED' } });
  await assert.rejects(
    () => assertApiReady({ fetchImpl: async () => Promise.reject(refused) }),
    (error) =>
      error.message.includes('nothing is listening on host port 8080') &&
      error.message.includes('docker compose up -d --wait db redis') &&
      error.message.includes('manage.py runserver 0.0.0.0:8080') &&
      error.message.includes('--allow-offline'),
  );
});

test('launcher arguments keep offline mode explicit', () => {
  assert.deepEqual(parseArguments(['--install']), {
    install: true,
    clear: false,
    allowOffline: false,
  });
  assert.deepEqual(parseArguments(['--clear', '--allow-offline']), {
    install: false,
    clear: true,
    allowOffline: true,
  });
  assert.throws(() => parseArguments(['--offline']), /Supported:.*--allow-offline/);
});

test('cache clearing never silently reuses an existing Metro process', () => {
  assert.equal(shouldReuseExistingMetro({ state: 'compatible' }), true);
  assert.equal(shouldReuseExistingMetro({ state: 'absent' }), false);
  assert.throws(
    () => shouldReuseExistingMetro({ state: 'compatible' }, { clear: true }),
    /Stop it before using --clear/,
  );
});

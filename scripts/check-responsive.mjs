/**
 * Responsive compliance harness (NFR-08).
 *
 * Measures the one thing the requirement actually states: no route may scroll
 * the *page* horizontally at 320 / 768 / 1024 / 1440px. Deliberately scrollable
 * data tables are exempt, so the check is
 * `documentElement.scrollWidth <= innerWidth` (the page) rather than a scan for
 * any overflowing descendant — a table inside `overflow-x: auto` is correct and
 * must not be reported as a failure.
 *
 * Drives headless Chrome over the DevTools Protocol using Node 22's built-in
 * `fetch` and `WebSocket`, so it adds no dependency to a repo that has
 * deliberately avoided a frontend toolchain.
 *
 * Usage:
 *   node scripts/check-responsive.mjs [baseURL]
 * Exits non-zero if any route/width fails, so it works as a gate.
 */

import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";

const BASE = process.argv[2] ?? "http://127.0.0.1:8099";
const WIDTHS = [320, 768, 1024, 1440];
const PORT = 9222;

// Public storefront routes. Console routes need a session, so they are driven
// separately below after a form login.
const PUBLIC_ROUTES = [
  ["home", "/"],
  ["shop", "/shop/"],
  ["shop-filtered", "/shop/?size=M&sort=price_asc"],
  ["product-detail", "/shop/night-route-windbreaker/"],
  ["cart", "/cart/"],
  ["checkout", "/checkout/"],
  ["contact", "/contact/"],
  ["login", "/accounts/login/"],
  ["register", "/accounts/register/"],
  ["developers", "/developers/"],
];

const CONSOLE_ROUTES = [
  ["admin-index", "/admin/"],
  ["admin-orders", "/admin/orders/order/"],
  ["merchant-index", "/merchant/"],
  ["merchant-variants", "/merchant/catalog/productvariant/"],
  ["merchant-stock", "/merchant/inventory/stockrecord/"],
];

let messageId = 0;

function rpc(socket, method, params = {}, sessionId) {
  const id = ++messageId;
  return new Promise((resolve, reject) => {
    const onMessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.id !== id) return;
      socket.removeEventListener("message", onMessage);
      data.error ? reject(new Error(`${method}: ${data.error.message}`)) : resolve(data.result);
    };
    socket.addEventListener("message", onMessage);
    socket.send(JSON.stringify({ id, method, params, sessionId }));
  });
}

/** Resolve once the page has settled, or after a ceiling — never hang the run. */
async function navigate(socket, url) {
  const loaded = new Promise((resolve) => {
    const onMessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.method === "Page.loadEventFired") {
        socket.removeEventListener("message", onMessage);
        resolve();
      }
    };
    socket.addEventListener("message", onMessage);
  });
  await rpc(socket, "Page.navigate", { url });
  await Promise.race([loaded, sleep(8000)]);
  // Let fonts and any layout-shifting web font settle before measuring.
  await sleep(350);
}

async function measure(socket, width) {
  await rpc(socket, "Emulation.setDeviceMetricsOverride", {
    width,
    height: 900,
    deviceScaleFactor: 1,
    mobile: width < 768,
  });
  await sleep(150);
  const { result } = await rpc(socket, "Runtime.evaluate", {
    returnByValue: true,
    expression: `(() => {
      const doc = document.documentElement;
      // Widest element that is NOT inside an intentionally scrollable region —
      // that is what makes a failure actionable rather than just a number.
      let worst = null;
      for (const el of document.querySelectorAll('body *')) {
        let scrollable = false;
        for (let p = el.parentElement; p; p = p.parentElement) {
          const ox = getComputedStyle(p).overflowX;
          if (ox === 'auto' || ox === 'scroll') { scrollable = true; break; }
        }
        if (scrollable) continue;
        const r = el.getBoundingClientRect();
        if (r.right > window.innerWidth + 1 && (!worst || r.right > worst.right)) {
          worst = {
            right: Math.round(r.right),
            tag: el.tagName.toLowerCase(),
            cls: (el.className && el.className.baseVal !== undefined
                   ? el.className.baseVal : String(el.className || '')).slice(0, 60),
          };
        }
      }
      // Clipped-data check. The page-scroll metric above passes trivially when
      // a wide table sits inside overflow:hidden — the page does not scroll
      // precisely *because* the columns have been cut off and made
      // unreachable. That is the P0 defect, and it is invisible to
      // scrollWidth alone, so it is measured separately.
      const clipped = [];
      for (const table of document.querySelectorAll('table')) {
        if (table.scrollWidth <= table.clientWidth + 1) continue;
        let container = table.parentElement;
        let reachable = false;
        while (container) {
          const ox = getComputedStyle(container).overflowX;
          if (ox === 'auto' || ox === 'scroll') { reachable = true; break; }
          if (ox === 'hidden') break;            // clipped before any scroller
          container = container.parentElement;
        }
        if (!reachable) {
          clipped.push({
            id: table.id || table.className || table.tagName.toLowerCase(),
            need: table.scrollWidth,
            have: table.clientWidth,
          });
        }
      }

      return {
        scrollWidth: doc.scrollWidth,
        innerWidth: window.innerWidth,
        status: document.title,
        worst,
        clipped,
      };
    })()`,
  });
  return result.value;
}

async function main() {
  const chrome = spawn(
    "google-chrome",
    [
      "--headless=new",
      `--remote-debugging-port=${PORT}`,
      "--no-sandbox",
      "--disable-gpu",
      "--disable-dev-shm-usage",
      "--hide-scrollbars", // classic false positive: scrollbar gutter reads as overflow
      "about:blank",
    ],
    { stdio: "ignore" },
  );

  let target;
  for (let attempt = 0; attempt < 40; attempt++) {
    try {
      const response = await fetch(`http://127.0.0.1:${PORT}/json/list`);
      const targets = await response.json();
      target = targets.find((t) => t.type === "page");
      if (target) break;
    } catch {
      /* chrome not up yet */
    }
    await sleep(250);
  }
  if (!target) {
    chrome.kill();
    throw new Error("headless Chrome never exposed a debugging target");
  }

  const socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  await rpc(socket, "Page.enable");
  await rpc(socket, "Runtime.enable");

  const routes = [...PUBLIC_ROUTES];

  // Console routes need a staff session. Log in through the real form so the
  // measurement reflects what a merchant actually sees.
  const user = process.env.CONSOLE_USER;
  const password = process.env.CONSOLE_PASSWORD;
  if (user && password) {
    await navigate(socket, `${BASE}/merchant/login/`);
    await rpc(socket, "Runtime.evaluate", {
      awaitPromise: true,
      returnByValue: true,
      expression: `(async () => {
        const form = document.querySelector('form');
        if (!form) return 'no form';
        form.querySelector('[name=username]').value = ${JSON.stringify(user)};
        form.querySelector('[name=password]').value = ${JSON.stringify(password)};
        form.submit();
        return 'submitted';
      })()`,
    });
    await sleep(1500);
    routes.push(...CONSOLE_ROUTES);
  }

  const rows = [];
  let failures = 0;

  for (const [name, path] of routes) {
    for (const width of WIDTHS) {
      await rpc(socket, "Emulation.setDeviceMetricsOverride", {
        width,
        height: 900,
        deviceScaleFactor: 1,
        mobile: width < 768,
      });
      await navigate(socket, `${BASE}${path}`);
      const m = await measure(socket, width);
      const noPageScroll = m.scrollWidth <= m.innerWidth;
      const noClipping = m.clipped.length === 0;
      const pass = noPageScroll && noClipping;
      if (!pass) failures++;
      rows.push({ name, width, pass, noPageScroll, noClipping, ...m });

      let detail = "";
      if (!noPageScroll) {
        detail +=
          `  scrollWidth=${m.scrollWidth} > innerWidth=${m.innerWidth}` +
          (m.worst ? `  worst=<${m.worst.tag} class="${m.worst.cls}"> right=${m.worst.right}` : "");
      }
      if (!noClipping) {
        detail += `  CLIPPED: ${m.clipped
          .map((c) => `${c.id} needs ${c.need}px has ${c.have}px`)
          .join("; ")}`;
      }
      console.log(`${pass ? "PASS" : "FAIL"}  ${name.padEnd(20)} ${String(width).padStart(5)}px${detail}`);
    }
  }

  console.log("\n=== responsive compliance ===");
  const names = [...new Set(rows.map((r) => r.name))];
  console.log(`${"route".padEnd(22)}${WIDTHS.map((w) => String(w).padStart(8)).join("")}`);
  for (const name of names) {
    const cells = WIDTHS.map((w) => {
      const row = rows.find((r) => r.name === name && r.width === w);
      return (row ? (row.pass ? "PASS" : "FAIL") : "-").padStart(8);
    }).join("");
    console.log(`${name.padEnd(22)}${cells}`);
  }
  console.log(`\n${rows.length - failures}/${rows.length} passed`);

  socket.close();
  chrome.kill();
  process.exit(failures === 0 ? 0 : 1);
}

main().catch((error) => {
  console.error("harness error:", error.message);
  process.exit(2);
});

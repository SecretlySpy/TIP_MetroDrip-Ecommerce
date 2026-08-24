# Guide images

Screenshots and diagrams used by the GitHub Pages setup guide (`/index.html` at
the repository root). All nine are captured; none are placeholders.

**Not everything visual in the guide lives here.** Four diagrams are inline
`<svg>` inside `index.html` rather than files in this directory: the local
architecture overview, the host-OS/toolchain decision tree, the app-to-API
address map, and the four-terminal run order. They are hand-authored, they carry
`role="img"` with `<title>` and `<desc>`, and they are text at any zoom level —
so they are edited in the HTML, not re-captured. `09-troubleshooting-flowchart.png`
predates that approach and stays a PNG.

## Inventory

| File | Type | Source | Shows |
|---|---|---|---|
| `01-tools-verified.png` | Rendered terminal | Real output from a Windows dev machine | `git`, `python`, `docker`, and `uv` each answering with a version. |
| `02-mysql-container-healthy.png` | Rendered terminal | Real output | `docker compose up -d db --wait` finishing at `Healthy`, then `docker compose ps`. |
| `03-storefront-homepage.png` | Screenshot | Live dev server | The New Arrivals grid, with Browse Categories in the navbar. |
| `04-category-menu.png` | Screenshot | Live dev server | The category dropdown open: main categories, All links, Men/Women counts. |
| `05-shop-category-tree.png` | Screenshot | Live dev server | Shop filtered to Hoodies → Men; sidebar tree with the active chip highlighted. |
| `06-admin-dashboard.png` | Screenshot | Live dev server, real login | MetroDrip Administration dashboard listing every app. |
| `07-cart.png` | Screenshot | Live dev server | Cart holding one real variant added through the UI. |
| `08-checkout.png` | Screenshot | Live dev server | Checkout form with the order summary carrying that line item. |
| `09-troubleshooting-flowchart.png` | Diagram | Hand-authored SVG, rendered to PNG | Four-question decision tree for "the page will not load". |

The application screenshots were captured by driving the running dev server with
Playwright — opening the category menu, filtering the shop, selecting a real
variant, adding it to the cart, and logging into the admin. Nothing is mocked or
composited, so a UI change makes them stale. Re-capture rather than retouch.

The two terminal images are the machine's real command output typeset as a
terminal, so the text stays legible at the guide's column width instead of being
a blurry crop of a console window.

## Not yet captured: the mobile app

Steps 11-12 of the guide cover the Expo app and currently illustrate it with
inline SVG only, because capturing a phone screen needs a booted Android
emulator or an iOS simulator, and the guide's own author could not run either at
the time (see the unresolved host failure documented at the end of
`mobile/EMULATOR.md`). These are the shots to add when somebody has a working
device, in guide order, following the conventions below:

| File | Shows | Where it goes |
|---|---|---|
| `10-mobile-home.png` | M02 Home with the hero and product grid, on an emulator or simulator | Step 12, after "Terminal 4 — the app itself" |
| `11-mobile-product-detail.png` | M04 Product Detail with size / colour / fit selected and Add to Cart visible | Step 12, in the purchase walkthrough |
| `12-mobile-checkout.png` | M06 Checkout with a delivery zone chosen and the server-formatted total | Step 12, in the purchase walkthrough |
| `13-mobile-order-tracking.png` | M07 Order Tracking with the timeline at *Paid* | Step 12, closing the walkthrough |

Two rules specific to these:

- **Crop to the device screen**, not the emulator window. The emulator's chrome,
  toolbar, and your desktop wallpaper add nothing and date the image.
- **A phone screenshot is tall**, so it does not want the 1600 px width the
  desktop shots use. Capture at the device's native resolution and let the
  guide's CSS size it; two side by side in one figure reads better than one
  enormous portrait image.

Until they exist, do **not** add `<img>` tags pointing at these names — a broken
image in a setup guide reads as a broken setup guide. Add the file and the markup
in the same change.

## Staleness

These have already gone stale once. Adding the category navigation changed the
navbar in every storefront shot, and rebranding the admin changed its header —
so `03`–`08` all had to be recaptured. **Any change to the navbar, the admin
header, or the shop sidebar invalidates most of this directory.** Check the
screenshots whenever you touch shared chrome.

One image is knowingly behind its caption: `02-mysql-container-healthy.png` shows
`docker compose up -d db --wait`, while the guide now starts Redis alongside MySQL
(`db redis`). The figure's caption says so explicitly rather than pretending
otherwise, because the useful part of the image — what `Healthy` looks like — did
not change. Re-capture it the next time somebody has a clean Docker state.

Numbering follows guide order, not capture order. Inserting a step means
renumbering the files after it and updating the `src` attributes in
`index.html`.

## Conventions

- **Format**: PNG. Use JPEG only for photographs, which this guide has none of.
- **Width**: 1600 px maximum. The guide column is under 1000 px, so anything
  wider is wasted bytes. App screenshots are captured at a 1280 px viewport with
  a 1.25 device scale factor, which lands exactly on 1600.
- **Size**: keep each file under roughly 400 KB — the current set totals ~560 KB
  across nine files. GitHub Pages has no image pipeline, so whatever is
  committed is what visitors download.
- **Naming**: `NN-kebab-case-description.png`, numbered in guide order.
- **Redaction**: blur or crop anything that is not demo data — real names, real
  email addresses, API keys, and the contents of `.env`. The admin shot shows
  `admin@metrodrip.test`, a throwaway local account. For mobile shots this also
  means never capturing a screen that shows a TOTP QR code or a device's
  notification shade.
- **Browser chrome**: excluded throughout. The surrounding prose already names
  the URL, so the address bar only adds noise and personal bookmarks.

## Re-capturing

The images are wired into `index.html` as plain `<img>` elements, so replacing a
file on disk with the same name is enough — no markup change needed:

```html
<figure>
  <img src="docs/images/03-storefront-homepage.png"
       alt="…describe what the image shows…"
       loading="lazy" width="1600" height="1075">
  <figcaption>…</figcaption>
</figure>
```

Keep the `width`/`height` attributes roughly accurate. They let the browser
reserve space before the image arrives, which stops the page from jumping around
as a reader scrolls.

Always write a real `alt` description. Several team members will read this guide
on a phone or with a screen reader, and an image of a terminal is useless to them
without one. Describe what the image *shows*, not that it is a screenshot.

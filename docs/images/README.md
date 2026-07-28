# Guide images

Screenshots and diagrams for the GitHub Pages setup guide (`/index.html` at the
repository root). The guide currently renders a dashed placeholder wherever one
of these files is expected, so the page is usable before any image exists.

## Capture list

| File | Type | What to capture |
|---|---|---|
| `01-docker-desktop-running.png` | Screenshot | Docker Desktop on the Containers tab, whale icon showing the green running state. Establishes the prerequisite for Step 5. |
| `02-mysql-container-healthy.png` | Screenshot | Terminal output of `docker compose up -d db --wait` ending in `metrodrip-mysql  Healthy`, or the same container green in Docker Desktop. |
| `03-storefront-homepage.png` | Screenshot | `http://127.0.0.1:8000/` with the navbar and product grid. The "it worked" payoff image. |
| `04-admin-dashboard.png` | Screenshot | Django admin after login, showing the Catalog, Inventory, and Orders sections. |
| `05-cart-and-checkout.png` | Screenshot | Two panels — cart with one item, and the checkout form. Evidence of the end-to-end purchase flow. |
| `06-troubleshooting-flowchart.png` | Diagram | Decision flowchart: page will not load → is the server terminal running? → is Docker running? → does `/healthz/ready/` respond? → likely cause. |

## Conventions

- **Format**: PNG. Use JPEG only for photographs, which this guide has none of.
- **Width**: 1600 px maximum. The guide column is under 1000 px, so anything
  wider is wasted bytes.
- **Size**: keep each file under roughly 400 KB. GitHub Pages has no image
  pipeline, so whatever is committed is what visitors download.
- **Naming**: `NN-kebab-case-description.png`, where `NN` matches the step order
  above. Keep the numbers stable so the guide's references stay valid.
- **Redaction**: blur or crop anything that is not demo data — real names, real
  email addresses, API keys, and the contents of `.env`.
- **Browser chrome**: include the address bar when the URL is part of the point
  (Steps 7 and 9); crop it out otherwise.

## Wiring an image into the guide

Find the matching `<figure>` in `index.html` and replace the placeholder `<div>`
with an `<img>`, keeping the `<figcaption>`:

```html
<figure>
  <img src="docs/images/03-storefront-homepage.png"
       alt="MetroDrip storefront homepage showing the navigation bar and a grid of products"
       loading="lazy">
  <figcaption>…keep the existing caption…</figcaption>
</figure>
```

Add this rule to the stylesheet the first time an image goes in:

```css
figure img { display: block; width: 100%; height: auto; border-radius: var(--radius-sm); }
```

Always write a real `alt` description. Several team members will read this guide
on a phone or with a screen reader, and an image of a terminal is useless to
them without one.

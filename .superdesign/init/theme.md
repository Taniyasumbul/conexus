# Theme summary

## Compact token summary

- Product style: bright, calm legal-operations workspace; CSS custom properties in `frontend/src/ui/tokens.css`.
- Base surfaces: pale blue-gray `--bg: #f3f8fa`, white `--surface: #fff`, dark ink `--fg: #0b1d26`.
- Accent: ocean teal `--accent: #0891b2`; status colors are green, amber, orange, red and should always be accompanied by text/icon.
- Type: Plus Jakarta Sans display, Inter body, JetBrains Mono machine values.
- Spacing: 4, 8, 12, 16, 24, 32, 48px; max content width 1240px.
- Corners: 6, 10, 16, 22px; shadows are intentionally subtle.
- Themes: system/light/dark plus user-selectable palette previews (ocean, sunset, emerald, mono, midnight, violet).

## Design direction for redesign

Keep the calm legal-operations base, but constrain the product to one default brand palette. Treat additional palettes as a non-primary preference or remove them from the standard product flow. Reduce gradient use to a single optional brand moment; do not use gradients, floating decorative shapes, or animated counters as default information hierarchy.

## Source

Authoritative raw theme: `frontend/src/ui/tokens.css`.

Authoritative component styles: `frontend/src/ui/styles.css`.

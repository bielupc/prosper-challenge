# Prosper — Design System Reference

> AI Voice Agents for Patient Access and RCM · getprosper.ai
> A portable token + component reference. Pair with `colors_and_type.css` (import it directly).

---

## 1. Brand in one line
Warm + clinical-but-human. **Near-black Inter display** on a **cream** page, one hot **orange**
accent, anchored by **deep medical-blue** full-bleed bands. Concrete, outcome-first copy.

---

## 2. Color tokens

### Brand accent — use sparingly (a highlighter, not a fill)
| Token | Hex | Use |
|---|---|---|
| `--prosper-orange` | `#FF421C` | CTAs, sparkle icons, italic emphasis, active states, stat underlines |
| `--prosper-orange-bright` | `#FF671D` | gradient hi-light |
| orange 8% / 12% | `rgba(255,66,28,.08)` / `.12` | tinted icon-well fill / border |

### Deep blue — hero, feature & footer bands
| Token | Hex | Use |
|---|---|---|
| Hero gradient | `#095580 → #013653` (top→bottom) | full-bleed sections, + `bg-texture.png` overlay |
| `--blue-accent` | `#0083BC` | integration accents, links |

### Ink & warm neutrals (text) — never cool grey
| Token | Hex | Use |
|---|---|---|
| `--ink` | `#141414` | headings, dark UI, footer surface |
| `--text-warm-700` | `#332E29` | strong warm text, badge label |
| `--text-warm-600` | `#514B45` | card body, stat caption |
| `--text-warm-500` | `#676059` | default body copy |

### Surfaces & hairlines
| Token | Hex | Use |
|---|---|---|
| `--white` | `#FFFFFF` | cards, buttons |
| `--cream` | `#FEF9F1` | page tint, eyebrow pills |
| `--surface-dark` | `#141414` | footer / inverted CTA |
| `--border-gray` | `#ECEBEB` | hairline on white |
| `--border-cream` | `#E3DED6` | border on cream pills |
| on-blue | `rgba(255,255,255,.20)` border · `.10` fill | translucent badges / ghost buttons |

---

## 3. Typography

| Role | Font | Weight | Size / LH | Notes |
|---|---|---|---|---|
| H1 (hero) | Inter | 500 | 57 / 69.6 | roman + *italic* phrase, italic often orange |
| H2 (section) | Inter | 500 | 46.7 / 57.6 | |
| H3 | Inter | 700 | 31.6 / 38.4 | case-study sub-heads |
| Stat number | Inter | 700 | 39.2 / 48 | big proof numbers |
| Lead / caption | Inter | 500 | 18.6 / 26 | stat captions |
| Body | Manrope | 500 | 18 / 27.9 | warm-500 color |
| Button / label | Manrope | 700 | 14–16 | Title Case |
| Eyebrow pill | Inter | 500 | 15.4, +0.32px tracking | |
| Nav | Manrope | 500 | 14 | |

- **Display = Inter**, **Body/UI = Manrope.** Italic Inter is the signature emphasis device.
- Semantic classes provided in `colors_and_type.css`: `.ds-h1 .ds-h2 .ds-h3 .ds-stat .ds-lead
  .ds-body .ds-label .ds-badge .ds-nav`. `.ds-h1 em` / `.ds-italic` handle italic emphasis.

---

## 4. Spacing, radii & elevation
- **Radii:** pill `100px` · card/tile `20px` · button `12px` · icon-well `10px`.
- **Layout:** content max-width `1200px`, centered in a `1425`-wide frame (≈112px side gutters).
- **Elevation:**
  - Card — `0 1px 2px rgba(20,20,20,.04), 0 8px 24px rgba(20,20,20,.06)` (soft, low)
  - Floating chip — `0 12px 32px rgba(1,54,83,.18)` (blue-tinted)
  - Popover — `10px 0 25px rgba(0,0,0,.25)`

---

## 5. Components

### Buttons (height 48, radius 12, Manrope Bold, label + trailing icon)
- **Primary dark** — `#141414` bg, white text/icon. (paper-plane send icon)
- **Primary white** — `#fff` bg, black text, `1px #ECEBEB` border.
- **Lite / secondary** — white bg, hairline border, ink text, up-right arrow icon.
- **Nav button** — small (37px / 14px) white pill-12.
- **Contact pill** (on blue) — radius 55, `1px rgba(255,255,255,.2)` border, phone icon + number.
- States: hover = subtle darken / lift; press = slight shrink.

### Eyebrow pills (radius 100, leading sparkle icon)
- **On cream:** `--cream` bg, `--border-cream` border, warm-700 text, **orange** sparkle.
- **On blue:** `rgba(255,255,255,.10)` bg, `.20` border, white text, `.48` white sparkle.

### Cards
- **Stat card:** white, radius 20, big Inter-Bold number (39.2) over warm-600 caption.
- **Use-case tile:** title (Inter Bold 20) + 26×3 orange underline + Manrope description + rounded
  agent photo with a cream **name pill** bottom-left.
- **Icon well:** 65px, radius 10, orange 8% fill / 12% border, 32px orange glyph centered.

### Icons
Solid-fill, rounded, geometric. Sparkle/comet (signature), paper-plane send, up-right link arrow,
phone, calendar/shield/check. No emoji, no outline sets.

---

## 6. Copy / tone cheat-sheet
- Second person ("your team"); Prosper is a capable teammate.
- **Title Case** headlines & buttons; sentence case body.
- Headline = roman phrase + *italic (often orange)* payoff.
- Lead with concrete numbers ("50% of calls resolved end-to-end").
- Healthcare nouns = credibility: patient access, RCM, payor, benefit verification, prior auth.
- No emoji. Calm punctuation, em-dashes for cause→effect. Methodology trademark: **Blueprints™**.
- CTAs: "Get Started" · "More Use Cases" · "Read Case Study" · "Explore Features".

---

## 7. Assets
**Logo (official):** `prosper-logo-dark.svg` (light bg) · `prosper-logo-white.svg` (blue/dark bg) ·
`prosper-logo-mono-white.svg` · `prosper-logo-orange.svg` · `prosper-mark.svg` (flag only).
120×38 lockup; recolor wordmark `#141414`/`#FFFFFF`, mark stays `#FF421C`.
**Other:** `hero-agent.png` · `bg-texture.png` · `banner-line-pattern.png` · `icon-sparkle-feature.svg`.
Fonts via Google Fonts (Inter, Manrope) — swap to licensed files if required.

> See `preview/*.html` for live specimen cards and `ui_kits/website/` for a full homepage build.

# Avirta design system

The design rules for this app, written down. The source of truth is `static/css/style.css`; every token below is a CSS custom property there (`surface` = `var(--surface)`). A browsable version with live previews: [Avirta Design System](https://claude.ai/artifact/M9wv6QPFCgDkx5mN6YbNsh) (private; ask the owner for access).

When you change a token or a shared component in `style.css`, update this file in the same commit.

Quiz games to play together. **Midnight and brass**: warm parchment by day, deep navy by night, with brass for the one thing that matters on each screen.

Avirta is a bilingual (English and Arabic) web app for live quiz games: Knowledge Columns, Who is the fastest and The Hive, plus admin tools for the question bank and AI question writing. One stylesheet (`static/css/style.css`) styles every page. This system documents it; token names are the CSS custom property names, so `surface` here is `var(--surface)` in code.

## Principles

1. **Depth without shadows.** Layers are tonal: `bg` < `surface` < `raised`. Edges are 1px hairlines (`line`) drawn as inset outlines so they never add size, plus a lighter top edge (`line-hi`). There are no drop shadows anywhere; the stylesheet's tests reject `box-shadow`, `text-shadow` and `drop-shadow`.
2. **Brass is for the main thing.** The brass gradient (`grad-1` → `grad-2`, 135°) marks only the primary action, chosen chips and selected states. Everything else is `raised` or `surface`.
3. **Interaction = edge colour + a soft wash.** Hover and selection change the outline to `accent-1` and add a `tint` or `tint-2` wash. Nothing darkens, insets or scales.
4. **One text size for forms.** Body text, labels, hints, inputs, buttons and chips are all 16px (`body`) with 1.6 line height. Smaller sizes are for badges, counts and the footer only.
5. **Readable everywhere.** Text is 4.5:1 or better on its background in both themes; control edges use `line-strong` (3:1). Text on brass is always `on-accent`, never grey. Text on `success` or `danger` fills is `on-status`.
6. **Game geometry is frozen.** Board sizes, spacing and radii marked `[frozen]` in the stylesheet never change; only colours may.

## Content and voice

- Plain words. "Choose the AI", not "Choose your contestant"; "Active", not "On air". No themed metaphors.
- Bilingual labels read `English | العربية` (the `bi()` macro in `templates/_bi.html`), English first, a thin bar between. Arabic text carries `lang="ar" dir="rtl"`; user text fields use `dir="auto"`.
- Buttons say what happens: "Create Game", "Generate questions", "Back to Admin Controls".
- Messages say what happened and what to do next: "Only 14 matching questions; the board needs 25. Choose more tags or point values."
- Sentence case for everything; no all-caps labels or letter-spaced eyebrows.

## Colour

Two themes, light first. The page follows the device until the visitor picks one (set on `<html data-theme>` before first paint).

| Role | Tokens |
|---|---|
| Layers | `bg`, `surface`, `raised` |
| Edges | `line` (decorative), `line-strong` (controls), `line-hi` (top edge) |
| Text | `text`, `muted` (never on brass), `accent-ink` (brass text and links) |
| Brass | `grad-1`, `grad-2` (the gradient), `accent-1` (edges, focus), `accent-2` (checkbox accent), `on-accent` (text on brass) |
| Washes | `tint`, `tint-2` |
| Status | `success`, `danger`, `on-status`, `success-tint`, `danger-tint` |
| Game | `tile`, `team-a` (Blue), `team-b` (Red), `confetti-1`, `confetti-2`, `sweep` |
| Charts | `chart-1`, `chart-2` |
| Brand | `logo-ink` (wordmark) |

Derived values (not tokens, defined in CSS): `--accent` (the brass gradient), `--hairline` (a brass rule fading out at both ends), `--edge-hi` (the 1px top edge), `--veil` and `--veil-2` (the washes as gradients, so they layer over a fill).

## Type

One family: **Cairo**, which covers Latin and Arabic. Regular (400) for text, Bold (700) for headings, step legends and badges. The scale is 12 / 14 / 16 / 18 / 22 / 28 / 36 px (`--fs-1` … `--fs-7`); page titles are 28px bold, step legends 18px bold, everything in a form 16px.

## Space, radius and motion

- Space runs on a 5px rhythm: `s-1` 5 · `s-2` 10 · `s-3` 15 · `s-4` 20 · `s-5` 30 · `s-6` 60. Card padding `s-4`; gaps between chips and tiles `s-2`.
- Radius: `r-2` (4px) buttons and tiles, `r-3` (5px) form cards, `r-4` (8px) inputs and alerts, `r-6` (14px) content cards, `r-pill` chips, tabs and badges.
- Motion: one curve, `cubic-bezier(.2, .7, .2, 1)`, three durations: 120ms (hover), 200ms (panels), 320ms (page-level). Elegant and brief: answers lift (correct) or shake once (wrong), pages cross-fade with the logo making a half turn, a win gets rays, a trophy spring and confetti. Nothing loops except the loading spin. Everything turns off under `prefers-reduced-motion`.

## Iconography and logo

- Icons are Font Awesome 6 Free (solid), inline before a label at `s-1`, in the label's colour (`accent-ink` for feature icons).
- The logo is two parts: the ribbon **mark** (a four-fold symmetric knot in magenta, orange and violet; a quarter or half turn lands where it started) and the **AVIRTA wordmark**, drawn as a mask in `logo-ink`. Stacked on wide screens, side by side on phones; the game bar uses the mark alone at 24px. See the Logos group.

## Layout patterns

- **Page head:** a secondary "← Back to …" button, then the page title (28px bold), then one muted line of description.
- **Setup forms:** a `surface` form card with numbered steps (`FormStep`), chips for small choices, checkbox tiles for lists, and one primary submit at the end.
- **Dashboards:** cards at `r-6` with a big number, a muted subline and HTML/CSS charts with a table view.

## Accessibility

- Focus: 2px `accent-1` ring, 2px out, on every control.
- Chips and tiles keep native inputs (visually hidden for chips), so keyboard and screen readers work as for checkboxes and radios. Tag filters are buttons with `aria-pressed`; tabs are ARIA tabs.
- Live changes (counters, status) use `aria-live="polite"`.
- Colours told apart by lightness as well as hue (brass vs blue charts; Blue vs Red teams also differ in edge position).

## Tokens

### Colour

| Token | Light | Dark | Use |
|---|---|---|---|
| `bg` | `#f6f3ec` | `#0d1620` | Page background. The lowest of the three tonal layers (bg < surface < raised). |
| `surface` | `#fffdf8` | `#142230` | Cards, forms, panels and inputs: the middle layer, always on bg. |
| `raised` | `#efe9dd` | `#1b2c3c` | Secondary buttons, chips, tiles and table headers: things that sit on a surface. |
| `line` | `#ddd4c3` | `#2a3d50` | 1px hairlines around cards, tiles and dividers. Decorative only: never the only edge of a control. |
| `line-strong` | `#8d8473` | `#6a7f94` | Edges of form controls (inputs, chips, checkbox tiles): at least 3:1 on surface and raised. |
| `line-hi` | `#ffffff` | `#33495e` | The 1px lighter top edge (--edge-hi) that lifts cards instead of a shadow. |
| `text` | `#1b2733` | `#ece6d8` | Body text and headings on bg, surface and raised; also descriptions inside chosen (brass-tinted) tiles. |
| `muted` | `#5f6873` | `#9aa8b5` | Hints, secondary text, placeholders and inactive tabs on bg, surface and raised (about 4.6:1 on raised). Never on brass. |
| `accent-1` | `#946823` | `#d9b26a` | Brass for edges: hover and focus outlines, selected-tile borders, the hairline rule, input focus border. |
| `accent-2` | `#7a521a` | `#b8863b` | Deeper brass: native checkbox and radio accent-color. |
| `accent-ink` | `#8a5d1c` | `#d9b26a` | Brass for text and icons on bg and surface: links, feature icons, the full-limit counter. |
| `grad-1` | `#d6ac62` | `{accent-1}` | Start of the primary brass gradient (--accent, 135deg). Lighter in light mode so dark text reads on it. |
| `grad-2` | `#bb8c42` | `{accent-2}` | End of the primary brass gradient (--accent). |
| `on-accent` | `#1f1607` | `#1a1206` | All text and icons on the brass gradient: primary buttons, chosen chips, step numbers (5.9:1 or better). Never grey on brass. |
| `tint` | `rgba(148, 104, 35, 0.08)` | `rgba(217, 178, 106, 0.08)` | Soft brass wash (--veil) for hover on secondary controls and zebra table rows. |
| `tint-2` | `rgba(148, 104, 35, 0.16)` | `rgba(217, 178, 106, 0.16)` | Stronger brass wash (--veil-2) for chosen tiles, the active tab and the input focus ring. |
| `success` | `#2f7a55` | `#5fb38a` | Correct answers, success messages, verified stamps; fill for on-status text. |
| `danger` | `#b4453b` | `#d9776c` | Wrong answers, errors, End Game and delete buttons; fill for on-status text. |
| `on-status` | `#fffaf0` | `#10140f` | Text and icons on success and danger fills. |
| `success-tint` | `rgba(47, 122, 85, 0.12)` | `rgba(95, 179, 138, 0.14)` | Background of success messages; text on it stays text. |
| `danger-tint` | `rgba(180, 69, 59, 0.12)` | `rgba(217, 119, 108, 0.14)` | Background of error messages and form alerts; text on it stays text. |
| `overlay` | `rgba(27, 39, 51, 0.45)` | `rgba(4, 8, 12, 0.62)` | Backdrop behind dialogs and the winner popup. |
| `tile` | `#8f6220` | `#8f6220` | Unclaimed Hive cell. Same in both themes; white numbers on it. |
| `team-a` | `#1f77b4` | `#1f77b4` | Hive Blue team: claimed cells, top and bottom edges, the team dot. Fixed in both themes (set in hex_game_room.py). |
| `team-b` | `#d62728` | `#d62728` | Hive Red team: claimed cells, side edges, the team dot. Fixed in both themes. |
| `confetti-1` | `#b07e2e` | `#d9b26a` | Win confetti, first colour. |
| `confetti-2` | `#8f6220` | `#b8863b` | Win confetti, second colour. |
| `sweep` | `rgba(176, 126, 46, 0.28)` | `rgba(217, 178, 106, 0.22)` | The light sweep across a newly revealed question. |
| `chart-1` | `#946823` | `#b8863b` | Charts: primary series (validated against surface in each theme). |
| `chart-2` | `#2a6cc0` | `#3f86e0` | Charts: second series. Told apart from chart-1 by lightness and hue (brass vs blue). |
| `logo-ink` | `#1b2733` | `#ffffff` | Colour of the AVIRTA wordmark (a mask): navy ink in light mode, white on the dark background. |

Derived in CSS (not tokens): `--accent` = `linear-gradient(135deg, var(--grad-1), var(--grad-2))`, `--hairline` = `linear-gradient(90deg, transparent, var(--accent-1) 50%, transparent)`, `--edge-hi` (1px `line-hi` top edge), `--veil` / `--veil-2` (`tint` / `tint-2` as gradients). `team-a` and `team-b` are set in `contents/thehive/hex_game_room.py` and `.team-dot-a/b`, not as CSS variables.

### Type

Font: **Cairo** (`static/fonts/Cairo/static/`), `--font: Cairo, sans-serif`.

| Style | CSS | Size | Line height | Weight | Use |
|---|---|---|---|---|---|
| title-xl | `--fs-7` | 36px | 1.25 | 700 | Rare: the largest heading. |
| page-title | `--fs-6` | 28px | 1.25 | 700 | Page titles (.page-title): create-room forms, AI pages. |
| section | `--fs-5` | 22px | 1.6 | 700 | Section headings (At a glance) and the Join bar label. |
| step | `--fs-4` | 18px | 1.6 | 700 | Numbered form steps (legend) and card headings. |
| body | `--fs-3` | 16px | 1.6 | 400 | All body text, labels, hints, inputs, buttons and chips. The site has no smaller text in forms. |
| meta | `--fs-2` | 14px | 1.6 | 400 | Badges, counts, chart subtitles, tag chips. |
| fine | `--fs-1` | 12px | 1.6 | 700 | Tiny badges and the footer only. |

### Spacing

| Token | Value | Use |
|---|---|---|
| `s-px` | 1px | Hairlines. |
| `s-1` | 5px | Icon-to-label gaps, the tightest padding. |
| `s-2` | 10px | Gaps between chips, tiles and form rows. |
| `s-3` | 15px | Gaps between fields; mobile card padding. |
| `s-4` | 20px | Card and form padding; gaps between cards. |
| `s-5` | 30px | Space between page sections. |
| `s-6` | 60px | Large page breaks. |

### Radius

| Token | Value | Use |
|---|---|---|
| `r-1` | 3px | Inline code. |
| `r-2` | 4px | Buttons and checkbox tiles. |
| `r-3` | 5px | Form cards and question tiles. |
| `r-4` | 8px | Inputs, alerts, panels. |
| `r-5` | 10px | Medium panels. |
| `r-6` | 14px | Dashboard cards, home game cards, AI cards. |
| `r-pill` | 999px | Chips, tag chips, tabs, badges, step numbers. |

### Motion

| Token | Value | Use |
|---|---|---|
| `--t-1` | 120ms | Hover and small state changes. |
| `--t-2` | 200ms | Panels, tabs, toggles. |
| `--t-3` | 320ms | Page-level and message enter/leave. |
| `--ease` | `cubic-bezier(.2, .7, .2, 1)` | The one curve for everything. |

## Components

### Button

Buttons start an action; primary is the brass gradient, everything else sits on raised.

**Variants**
- `button primary` — the one main action of a form or dialog (Create Game, Generate questions). Submit buttons are primary by default. Text uses `on-accent`.
- `button` (secondary) — supporting actions: Cancel, Back to Admin Controls, Load models. `raised` fill, `line` hairline.
- `button danger` — End Game, Delete. `danger` fill, `on-status` text. Always behind a confirm dialog.
- `button success` — rare positive confirmations.

**States**: hover adds the brass outline (`accent-1`) and a soft `tint` wash; focus shows a 2px `accent-1` ring 2px out; disabled turns neutral (`raised`, `muted` text, dashed `line-strong` edge). Never fade a brass button: faded brass makes its text look grey.

**Shape**: 4px corners (`r-2`), 40px tall, 16px regular text. An icon goes before the label, `s-1` apart.

**Consumer provides**: the label (bilingual where the page is: `English | العربية`) and, for links, `href`.

Source: `:where(button, .button)` in static/css/style.css.

### Chip

Chips are toggle checkboxes or radios shown as pills: point values, question types, how many questions, language.

- Unchosen: `raised` fill, `line-strong` edge (3:1). Chosen: brass gradient, `on-accent` text and a leading tick.
- Markup: a visually hidden `input.chip-input` followed by `label.chip`. The input keeps keyboard and screen-reader behaviour; focus draws a 2px `accent-1` ring.
- Group them in `.chip-group` (gap `s-2`) with a `field-label` or `aria-labelledby`.
- Everything inside a chosen chip (a note like "100–500") uses `on-accent`. Never put `muted` text on brass.

Source: `.chip`, `.chip-input` in static/css/style.css.

### Tag Filter

Tag chips filter the category list on the create-room forms; they are buttons with `aria-pressed`, not checkboxes.

- Groups: Language (English, Arabic) and Topic; a `tag-divider` separates them. Within a group chips widen the filter (any of them); across groups they narrow it (all groups must match). "All" clears.
- Smaller than form chips: 14px (`meta`) text, 3px × 12px padding. Pressed = brass gradient with `on-accent` text.
- Tags are data on each category tile (`data-tags`), never shown on the tiles.

Source: `.tag-chip`, `templates/_category_picker.html`.

### Form Step

A numbered section of a setup form: a fieldset whose legend carries a brass step number.

- Legend: 18px bold (`step` style) with `step-num` (26px brass disc, `on-accent` number). Steps are separated by a 1px `line` rule; the last has none.
- Children wrap in a flex row, gap `s-2` × `s-3`; chip groups, grids and toolbars take the full width.
- Use 1, 2, 3 … in page order. The same pattern heads the AI pages' cards (`.ai-step`).

Source: `.form-step`, `.step-num` in static/css/style.css.

### Text Field

A label above a full-width input, with an optional hint below.

- Label: 16px regular (`body`). Optional parts in the label read "(optional)" in `muted`.
- Input: `surface` fill, 1px `line-strong` border, 8px corners (`r-4`), 8px × 12px padding. Focus: `accent-1` border plus a 2px `tint-2` ring. Placeholder in `muted`.
- Hint: 16px `muted`, 4px below. Errors go in a form alert at the top of the form, not under each field.
- Use `dir="auto"` on fields that may hold Arabic.

Source: `input[type=text], select, textarea` in static/css/style.css.

### Checkbox Tile

A checkbox in a tile: category lists, and option lists that need a title and a description.

- Tile: `raised` fill, 1px `line-strong` edge, 4px corners (`r-2`). Hover: `accent-1` edge. Chosen: `accent-1` edge and the `tint-2` wash.
- The native checkbox uses `accent-color: accent-2`.
- A description inside a tile is `muted` when unchosen and `text` when chosen: grey on the brass wash is too faint.
- Unavailable (not enough questions) = half opacity with a title explaining why.

Source: `.category-checkbox`, `.ai-toggle` in static/css/style.css.

### Alert

Inline alerts sit at the top of a form or page; flash messages drop from under the header.

- Form alert: 8px corners, a 4px start border and a tinted fill. `danger` (default) for errors, `.warning` uses `accent-1` and `tint-2`, `.success` uses `success`. Text stays `text`.
- Flash message: a `surface` strip under the header with a status outline. Errors stay until dismissed; success and info leave on their own (timing in ui.js).
- Say what happened and what to do next, in plain words. Bilingual when the page is.

Source: `.form-alert`, `.flash-message` in static/css/style.css; `templates/_flash.html`.

### Tabs

Pill tabs switch panels inside a page (Admin Controls, Question Bank).

- Inactive: `muted` text, no fill. Hover: `text`. Selected: `text`, `accent-1` outline, `tint-2` wash on `surface`.
- ARIA tabs: `role="tablist"`, `role="tab"` with `aria-selected`; arrow keys move between tabs. A URL hash can open a tab (e.g. `#category-tags`).

Source: `.tab-nav`, `.tab-button` in static/css/style.css.

### Card

The panel every page builds on: `surface` on `bg`, a 1px `line` hairline and a lighter top edge instead of a shadow.

- Depth comes only from tonal layers (`bg` < `surface` < `raised`), the 1px hairline (an inset outline, so it adds no size) and the `line-hi` top edge. No drop shadows anywhere: the stylesheet's tests reject them.
- Padding `s-4`; corners `r-6` for dashboard and content cards, `r-3` for form cards.
- The brass hairline (`--hairline`, fading from the middle) separates the header from the page and marks key dividers. Use it sparingly.

Source: `form`, `.inner-section`, `.chart-card` in static/css/style.css.

### Badge

Small pills for counts and statuses.

- Default: `raised` with a `line` hairline. `.ok` = `success` on `success-tint`, `.bad` = `danger` on `danger-tint`, `.brass` = `on-accent` on the gradient (Active, Recommended).
- 14px bold (`meta`), pill radius. Keep the text to one or two words.

Source: `.badge`, `.ai-badge`, `.ai-stamp` in static/css/style.css.

### Hive Cell

A Hive board cell: a hexagon with a point value, lit from the top-left for depth.

- Unclaimed: `tile`. Claimed: `team-a` (Blue) or `team-b` (Red). White bold numbers.
- Depth uses gradient layers (a light top, a shaded bottom), never shadows. The current team's cells pulse with its edges; on a win the winner's colour holds.
- Game geometry is frozen: change colours only.

Source: `#hex_root .cell` in static/css/style.css; `templates/thehive/play.html`.

## Notes

- Static HTML previews of every component live in the design system page above; the app has no component library (Flask + Jinja templates).
- `@font-face` registers Cairo Regular at weight 300 and Cairo Bold as weight 500 *oblique*; in practice that renders Regular for normal text and Bold for `font-weight: bold`. The other Cairo weights in `static/fonts` are unused.
- Legacy aliases still read by game scripts: `--error-color` (= `danger`), `--primary-color2-dark` (= `tile`).
- Unused images: `static/images/logovtext.png`, `logovtext-light.png` (the old one-piece logo).

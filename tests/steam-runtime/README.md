# Installed Steam navigation regression harness

Run from the DAS checkout:

```sh
node scripts/test_steam_focus55.mjs
node scripts/test_steam_focus55.mjs --require-production-structure
```

Set `DAS_STEAM_ROOT` to an installed Steam `steamui` directory. The optional
`DAS_STEAM_REFERENCE` supplies only that directory path; its saved class mappings
are never reused. `DAS_TEST_BROWSER` can select the local Chromium executable.

The loader reads `library.js`, `sp.js` and their CSS without modifying Steam. It
uses TypeScript's AST to isolate the core factory object, captures the shared
chunk through its `webpackChunksteamui.push` registration, and does **not** run
the Steam application entrypoint. No Valve source, stylesheet or font is copied
into the repository. Every result identifies the exact JS/CSS SHA256 and the
host React version. The local host React dependency is authentic React, not a
replacement for Steam's navigation logic.

The browser executes installed factory74562 (`NavigationNode`) and96485 (flow
mapping), and their original dependencies. The actual unmodified methods include
`OnNavigationEvent`, `ComputeRelativeDirection`, `FindNextFocusableChild`,
`FindNextFocusableChildInGrid`, descendant selection and DOM geometry helpers.

The external tree's final transfer/focus service, event delivery and small DOM
layouts are deterministic fixtures. This is deliberately narrower than launching
Steam's complete controller/navigation tree. It does not prove native input,
text editing, focus-ring rendering, Steam CEF, actual SteamOS button hints or USB.
The topology fixtures reproduce alpha54 and compare corrected parent groupings;
they do not render the complete production React screen. The accompanying AST
audit detects the relevant groups in the actual production source. Strict mode
fails while either production toolbar is not a native ROW or Add cards remain
plain transparent divs. New component contracts require reviewing this audit.

## Reproduced alpha54 causes

1. Search and Presentation were laid out as two CSS columns inside a plain div.
   Steam's registry could only see their native descendants under the body
   `flow-children="column"`. The real COLUMN algorithm rejects LEFT/RIGHT; DOWN
   moves from Search to the visually adjacent Presentation. A native ROW group
   makes RIGHT/LEFT work in the corresponding geometry.
2. Add cards were plain divs under a native GRID. Steam therefore registered
   Select1, Customize1, Select2, Customize2 as immediate siblings. Its real grid
   algorithm returns no horizontal target when the first following sibling
   (Customize1 below Select1) does not overlap vertically; it never reaches
   Select2. A native group per card exposes cards to GRID and keeps their local
   Select/Customize controls together.

Both failures are explicitly expected in the broken-topology scenarios; a
passing demonstration is not a claim that alpha54 worked. The corrected
topologies must cross horizontally and retain access to Customize below.

## Why alpha54 browser checks missed this

- `tests/ui/decky.tsx` replaced Focusable with a div and discarded `flow-children`,
  `navEntryPreferPosition` and the real node registration. It dispatched test
  events to selected elements directly, bypassing directional target selection.
- `tests/ui/steam-decky.tsx` reused that div; adding native CSS classes did not
  create a Steam navigation tree. Fake `.gpfocus` paint is not navigation.
- Its Field implementation omitted real FieldChildrenWithIcon/FieldChildrenInner
  wrappers for below children, and several item adapters lost actual layout/
  width props. Their geometry was an approximation of production markup.
- Its Tabs implementation substituted a scrollable div for the native registered
  ScrollPanel, FocusRingGroup, context providers and focus history.
- Real native Field defaults inline and width-min; childrenWidthFixed means a
  theme-dependent minimum width (250px in the inspected current stylesheet).
  Passing a native component name does not make arbitrary surrounding geometry
  or scrolling correct.
- Old reference metadata can select a different one of Steam's multiple theme
  class maps, or come from different JS/CSS revisions. Fresh checks must record
  all asset hashes and active context. Do not equate sampled Desktop/Mac CSS with
  the user's live SteamOS DOM.

## Correction checklist outside this harness

- Align semantic navigation groups with visible rows/cards; audit every plain
  multi-control wrapper beneath a forced COLUMN/GRID, not just the toolbar.
- Make list media/text/action wrappers explicit. Remove descendant grid-column
  rules and mutually overriding grid definitions that depend on native DOM depth.
- Give Player actions bounded row dimensions; native DialogButton defaults to
  width100%, and a wrapping flex row without item widths can create full-width
  stacked controls. Keep every action reachable, not only visible by pointer.
- Keep one actual registered content scroll owner. Inspect ScrollPanel wrappers,
  DialogBody overflow and clipping with the native DOM; do not substitute one div.
- Keep the collection header concise and use a real contextual Steam menu for
  secondary actions; leave preparation/GIF evidence truthful.
- Test narrow Deck800p and TV layouts, localized long names, image loading/
  fallback, list selection, every column transition, all Player actions, Back,
  tabs and scroll return. Physical SteamOS/controller acceptance remains an
  explicit follow-up, with the supplied video as the observed failure baseline.

The separate native CSS test adapter now preserves Field child shells/layout/width props and the DialogButton default width100%. It remains an inspected DOM adapter, not the native component renderer or engine. The CSS runner refuses stale JS/CSS references, and records all four installed asset hashes. Its focused mode covers list and Add list media/text/action bounds, a long title beside its check mark, all four full Player actions and Faceplate alignment action geometry in FR/EN at800×800 and TV1280×720.

The navigation suite has eight deterministic scenarios (27 directional transitions): the two intentionally broken alpha54 topologies, their corrected versions, the three-control toolbar in both directions, list rows preserving action columns, four Player controls and wrapped2×2 gallery card groups. The current installed native menu implementation invokes the supplied cancel callback and then calls its instance Hide; the callback used only to restore focus cannot suppress native closure. The browser menu fixture does not prove that implementation.

No production code or publication is changed by this harness. The negative historical run uses a read-only Rollup source override (`DAS_NATIVE_SOURCE_REF=v0.1.0-alpha.54`), without checking out or modifying production files.

## Alpha56 toolbar and slow-response stability

The CSS runner now requires one three-column native ROW toolbar with equal widths, compact labels, aligned native control heights and no enclosing Field panels. Dropdown menuLabel is exposed only on the test select used to choose options.

`DAS_NATIVE_STABILITY56_ONLY=1` runs FR/EN1280×720 production React with350ms RPC delays. It samples the grid position across browser frames during membership selection, rejects redundant library reloads and reads the DOM immediately after changing Add to Collection so it cannot silently wait out stale content. These are data/layout checks using the documented Tabs DOM adapter, not proof of the live Steam tab transition.

Read-only inspection of current native Tabs (module10272) and Transition (module86673) establishes that animation uses the active tab id as childrenKey. New tabs/content object identities alone do not start a new transition; direction and delayed focus-history restoration track the active id. Native tab headers do activate on focus, so live controller/focus-return behavior still requires SteamOS acceptance.

The final alpha56 regression exposed one additional density-cache flash: changing density in Settings and returning to Collection lacked an exact cache entry for the new layout, briefly emptying a known page. The production fix may reuse a page0 prefix only from the same tab/source/filter/query and resize it to the target density; it must never borrow another scope. The slow-RPC test now requires all eight known Collection cards immediately after returning and on every sampled frame during650ms of refresh, with the Add-only Balatro excluded, in both languages.

## Alpha57 recovery

`DAS_NATIVE_RECOVERY57_ONLY=1 npm run test:steam-native-ui` checks 24 native stylesheet surfaces: capacity and confirmation action rows, prepared green/problem orange, French/English, 800/1280 width, classic/current. Recovery rows have a production AST contract and a ninth native movement scenario crossing the recovery/result rows. No physical controller/SteamOS acceptance is inferred.

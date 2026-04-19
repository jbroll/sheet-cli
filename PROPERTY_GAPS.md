# Property Registry Gap Analysis

Forward-looking inventory of Google Sheets + Drive API surface that
*could* be exposed through the `TARGET.property` grammar but isn't yet.
Use this as a checklist when picking the next round of work.

## Current coverage (baseline)

| Scope | Properties |
|---|---|
| spreadsheet | `title`, `locale`, `timeZone`, `autoRecalc`, `theme`, `defaultFormat`, `iterativeCalc`, `named.NAME`, `parents` / `parents.FOLDER_ID` |
| sheet | `title`, `index`, `freeze`, `color`, `hidden`, `hideGridlines`, `rightToLeft`, `rowCount`, `columnCount`, `filter`, `conditional[i]`, `protected` |
| range | `format`, `borders`, `merge`, `note`, `validation`, `protected` |
| row | `height`, `hidden`, `autofit` |
| column | `width`, `hidden`, `autofit` |

## Ranking axes

Each candidate is rated on two dimensions:

- **Shape fit**: does the Sheets API resource behave like one of our existing patterns (singleton scalar, keyed collection, indexed collection, Drive crossover, action)?
- **Wiring cost**: lines of handler + how much new plumbing is needed.

"Easy" below means shape fit is exact and no new plumbing is required.

---

## Tier A — genuinely easy (drop-in analogues)

These copy an existing handler pattern almost verbatim.

### `sheet.banding[i]` — alternating row/column colors
- **Pattern**: indexed collection, mirror of `.conditional[i]`.
- **API**: `addBanding` / `updateBanding` / `deleteBanding`. Stored in each sheet's `bandedRanges[]`.
- **Body**: `BandedRange { bandedRangeId, range, rowProperties, columnProperties }`.
- **Verbs**: all four (get/put/del supports both unkeyed = whole collection and `[i]` = one); `new` appends.
- **Estimate**: ~45 lines + tests.

### `sheet.filterView.NAME` — saved filter views
- **Pattern**: keyed collection, mirror of `.named.NAME`.
- **API**: `addFilterView` / `updateFilterView` / `deleteFilterView` / `duplicateFilterView`. Stored in each sheet's `filterViews[]`.
- **Body**: `FilterView { filterViewId, title, range, criteria, filterSpecs, sortSpecs, namedRangeId }`. Key by `title` since that's user-visible.
- **Verbs**: all four.
- **Estimate**: ~55 lines + tests.

### `SID.trashed` — Drive trash flag
- **Pattern**: Drive scalar bool crossover (like `.parents`).
- **API**: `drive.files().get(fileId, fields='trashed')` for get; `drive.files().update(fileId, body={'trashed': bool})` for put/del.
- **Plumbing**: `self.drive` is already wired on `SheetsClient`.
- **Estimate**: ~15 lines + tests.

**Combined: banding + filterView + trashed ≈ 120 lines of handler code.** Everything aligns with existing patterns so there's little design risk.

---

## Tier B — one wrinkle each

### `sheet.rowGroup[i]` / `sheet.columnGroup[i]` — outline groups
- **Pattern**: two parallel indexed collections on the sheet.
- **API**: `addDimensionGroup` / `deleteDimensionGroup` / `updateDimensionGroup`. Stored in `sheet.rowGroups[]` and `sheet.columnGroups[]`.
- **Wrinkle**: the API splits by dimension. Either (a) expose two properties (`.rowGroup[i]`, `.columnGroup[i]`) — clean but more names — or (b) unify as `.group[i]` and infer dimension from the body's `range.dimension`.
- **Recommendation**: (a). Matches how `row.height` / `column.width` split at dimension scope.
- **Estimate**: ~60 lines.

### `SID.permissions.EMAIL` — Drive sharing
- **Pattern**: keyed collection via Drive crossover.
- **API**: `drive.permissions().list/create/update/delete(fileId, permissionId, body={type, role, emailAddress, domain})`.
- **Wrinkle**: Drive keys permissions by opaque `permissionId`, not email. get/put/del keyed by email require a list-then-match step.
- **Alternate key**: could key by `permissionId` for fidelity, by `emailAddress` for ergonomics. Mixed approach: accept either (try email first, fall back to id).
- **Estimate**: ~70 lines.

---

## Tier C — bigger but mechanical

### `sheet.chart[id]` — embedded charts
- **Pattern**: keyed collection (by `chartId`).
- **API**: `addChart` / `updateChartSpec` for put; `deleteEmbeddedObject` for del. Read from each sheet's `charts[]` array.
- **Body**: `EmbeddedChart { chartId, spec, position }` — `spec` is a union (basicChart, pieChart, histogramChart, bubbleChart, candlestickChart, org, treemap, waterfall, scorecard). We pass JSON through without validating, so the complexity lives in docs not code.
- **Estimate**: ~70 lines. Users need the ChartSpec reference to compose bodies.

### `sheet.slicer[i]` — slicers (compact filter UI element)
- **Pattern**: indexed collection, shape identical to chart.
- **API**: `addSlicer` / `updateSlicer` for put; `deleteEmbeddedObject` for del.
- **Body**: `Slicer { slicerId, spec, position }`.
- **Estimate**: ~55 lines.

### `SID:Sheet!A1.pivot` — pivot tables
- **Pattern**: cell-scoped structure (not sheet-level).
- **API**: written via `updateCells` with a `pivotTable` on the anchor cell; read via grid-data `cell.pivotTable`.
- **Wrinkle**: pivot is embedded in a *single cell*, not the sheet — target must be a single-cell RANGE. Body is a `PivotTable` with `source`, `rows`, `columns`, `values`, `criteria`, `filterSpecs`, etc.
- **Estimate**: ~80 lines. Genuinely useful but the shape is one-off.

---

## Tier D — cross-scope, multi-API

### `*.metadata.KEY` — developer metadata
- **Pattern**: register the same name at 4 scopes (spreadsheet/sheet/range/dim) — analogous to how `.protected` registers at two.
- **API**: `createDeveloperMetadata` / `updateDeveloperMetadata` / `deleteDeveloperMetadata`; reads via `searchDeveloperMetadata` (separate endpoint) or grid-data.
- **Body**: `DeveloperMetadata { metadataId, metadataKey, metadataValue, location, visibility }` — location determines the scope.
- **Wrinkle**: keyed lookup needs `searchDeveloperMetadata` (the only API call in our stack that isn't a direct meta read or batchUpdate). Four scope registrations.
- **Estimate**: ~100 lines, higher design surface.

---

## Tier E — don't bother (stateless actions)

These don't fit the get/put/del model. Each is a one-shot operation, not state on a resource. Leave to the `sheets_batch_update` escape hatch.

| Request | Intent |
|---|---|
| `sortRange` | Sort a range in place |
| `findReplace` | Find/replace across sheet(s) |
| `trimWhitespace` | Strip whitespace from cells |
| `deleteDuplicates` | Remove duplicate rows |
| `textToColumns` | Split delimited text into columns |
| `insertRange` / `deleteRange` (with shift) | Structural shift, not purely dimension add/remove |
| `moveDimension` | Reorder rows/columns |
| `cutPaste` / `copyPaste` (non-server-side) | Data movement with pasteType variants |

The verb grammar doesn't have a clean "run this action" concept. `new` is the closest but implies creating a resource. Force-fitting any of these makes the grammar weirder without real payoff — the escape hatch is the right venue.

---

## Recommended rollout order

1. **Tier A as one commit**: banding + filterView + trashed. Small, direct, high-confidence.
2. **Tier B as one commit**: rowGroup/columnGroup + permissions. One real-world wrinkle each.
3. **Tier C separately**: charts, slicers, pivot — each is its own PR because the body shapes are distinct and worth thinking about individually.
4. **Tier D when someone needs it**: developer metadata is niche.
5. **Tier E stays in batch_update.**

---

## How to add a new property (reminder)

One handler set + one registration, no other changes. Pattern:

```python
def _foo_get(client, target, _data): ...
def _foo_put(client, target, data): ...
def _foo_del(client, target, _data): ...

register("foo", TargetType.SCOPE,
         get=_foo_get, put=_foo_put, del_=_foo_del)
```

Then:
- Add entries to the property table in `CLAUDE.md`, `README.md`, `llms.txt`, `mcp-server/AI_VISIBLE_GUIDANCE.md`, `mcp-server/sheet-service.py`.
- Add tests mirroring the shape (TestSheetXxx / TestRangeXxx / TestSpreadsheetXxx).
- Smoke test on a throwaway spreadsheet before calling it done.

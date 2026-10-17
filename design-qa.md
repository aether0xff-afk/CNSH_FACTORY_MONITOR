# Inventory ledger redesign QA

Selected visual truth: second displayed concept, `generated_images/exec-38fe55e4-6978-4fc4-a3de-92de9af7b969.png` (1708 × 920). Implementation: `/workspace/scratch/80885ced7b19/ledger-final.jpg` (1348 × 1036 full-page pixels). Browser CSS viewport reported 1363 × 936 including scrollbar; screenshots exclude scrollbar. These are different aspect ratios, so this is a structural visual review, not a pixel-perfect comparison at 1440 × 1024. Comparison evidence: `/workspace/scratch/80885ced7b19/comparison-final.jpg`, proportional downsampling without warping.

State: light theme, five example factories, first row selected, one-hour history. Example values and history differ from generated concept; production uses the existing API without demo fallbacks.

## Findings and comparison history

- Initial P2: detailed sidebar made the analysis region excessively tall. Reduced duplicate desktop metrics, compacted row and section spacing, bounded the recent-events scroll region. Recaptured and compared in `comparison-final.jpg`; the chart and stock/flow/details now form one compact aligned region.
- Initial P2: generic amber status for paused collection. Changed paused/waiting indicators to neutral gray; warning amber is reserved for stale data.
- Initial P2: polling replaced focused factory buttons. Restore focused selection by factory ID after list updates.
- No remaining actionable P0/P1/P2 findings in the observed desktop state.

## Required surfaces

- Typography: system sans with Korean fallbacks; headline, row name, numeric stock, and quieter metadata maintain the selected hierarchy. Actual font rendering is platform dependent; no remote font dependency.
- Spacing/layout: lavender rail, full-width selectable inventory table, lower chart with right-side stock, capacity, flow and recent events. Narrow screens stack details and horizontally scroll the table. Mobile CSS is implemented but has not been visually tested on a mobile viewport.
- Colors: white base, lavender row selection, mint chart/status, muted amber for stale collection, gray paused status. No neon or gradients.
- Assets: bundled Bootstrap Icons 1.13.2 with its license. Existing SVG chart renderer retained. No generated decorative assets required.
- Copy: labels reflect observed net inventory change, not gross production. Unknown rates are dashes. Collection status does not claim the physical farm is running. Removed unsupported generated advice and unrelated navigation.

## Interaction verification

Cloud browser with preview-only fixture API: factory selection updates detail; six-hour selector changes sample count; pause/resume calls existing PATCH route; registration form creates and selects a new fixture factory. App-origin console errors: none (browser extension messages excluded). Existing FastAPI suite: 5 tests passed. JavaScript syntax and git whitespace checks passed.

## Remaining limits

No live Minecraft/RCON end-to-end check. No pixel-perfect 1440 × 1024 or mobile screenshot validation. Demo preview is separate from production files. Brand and row content intentionally use real code semantics rather than image-generated strings.

final result: passed

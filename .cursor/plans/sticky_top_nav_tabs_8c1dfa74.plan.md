---
name: sticky top nav tabs
overview: Convert the existing Current/History/Statistics nav into a sticky top menu bar with equal-width tabs spanning the row, while preserving existing routes and active-state styling.
todos:
  - id: refactor-navitem
    content: Update nav item styles to support equal-width tab presentation
    status: completed
  - id: restructure-header
    content: Restructure App header into content row + sticky tab bar row
    status: completed
  - id: enable-sticky-grid-nav
    content: Implement sticky top menu bar with 3 equal-width tabs
    status: completed
  - id: verify-routing-states
    content: Verify routes and active-state styling remain correct
    status: completed
isProject: false
---

# Sticky Top Equal-Width Menu Bar

## Goal
Move the `Current`, `History`, and `Statistics` navigation into a dedicated sticky top menu bar and make all three tabs equal width across the available row.

## Files to update
- [c:\Users\emil_\vscode\vg_assignment\dashboard\web\src\App.tsx](c:\Users\emil_\vscode\vg_assignment\dashboard\web\src\App.tsx)

## Implementation steps
- Refactor `NavItem` in `App.tsx` so each tab can stretch equally (use full-width + centered text styles).
- Split header layout in `App.tsx` into two rows:
  - top row: title, warning text, status banner, widescreen toggle
  - second row: a dedicated `nav` container at the top level of the shell for menu tabs
- Make the menu bar sticky at the top (`sticky top-0`) with appropriate z-index and background/border so it remains visible while page content scrolls.
- Change the menu bar layout to a 3-column equal-width grid so `Current`, `History`, `Statistics` always render with identical width.
- Keep route behavior unchanged (`/`, `/history`, `/stats`) and preserve active/inactive visual state semantics.

## Validation
- Open dashboard at `http://localhost:5173/` and confirm:
  - menu bar stays pinned at top while scrolling
  - all three tabs are equal width across the row
  - clicking each tab still routes correctly and highlights active tab
  - layout remains usable in both normal and wide-screen modes.
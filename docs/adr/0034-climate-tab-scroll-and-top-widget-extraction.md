# ADR 0034: Climate Tab Scroll and Top Widget Extraction

## Status
Accepted

## Context
The Climate Chamber tab still suffered from content compression in limited
window height. The user explicitly requested:
1. a right-side scrollbar instead of shrinking the content
2. extraction of the top "SMU Relay Assignment" block into a widget
3. extraction of the top "ISOS / 環境 Recipe" block into a widget

## Decision
1. Wrap the climate tab content in a QScrollArea
2. Create `ChamberRelayAssignmentWidget`
3. Create `ChamberRecipeWidget`
4. Keep `ClimateChamberTab` as the controller that orchestrates all chamber widgets

## Consequences
- Climate tab content remains readable under shorter window heights
- Top sections become independently maintainable widgets
- ClimateChamberTab becomes a clearer composition root

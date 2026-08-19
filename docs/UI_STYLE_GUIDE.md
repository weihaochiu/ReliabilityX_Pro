# UI_STYLE_GUIDE.md — ReliabilityX Pro GUI contrast and state-color rules

## Purpose

ReliabilityX Pro is a long-duration measurement GUI. Operators may monitor it for many hours, so readability and status-color consistency are safety and usability requirements, not cosmetic details.

## Contrast rules

1. Light background must use dark text.
2. Dark background must use light text.
3. Warning yellow / amber backgrounds must use near-black text.
4. Error red backgrounds should use white or near-white text unless the red is very pale.
5. Disabled text must remain readable; do not use extremely low-contrast grey on grey.
6. Avoid arbitrary inline styles for operational status colors. Prefer shared QSS, dynamic properties, or centralized style helpers.

## Relay and diagnostics matrix rules

- Occupied / active relay cells should be obvious and readable.
- If a relay cell uses yellow, orange, or pale warning background, the foreground must be dark.
- Tooltips must show channel, environment, polarity, and owner when available.
- Manual relay controls must keep safe-mode and measurement-running constraints visible.

## Form layout rules

- Use clear section titles for task-scoped status, hardware connection, relay mapping, recipe editing, and diagnostics.
- Do not mix hardware connection fields with measurement recipes or environment/station recipes.
- Use read-only tables for summaries; use explicit edit controls for persistent configuration.

## Future maintainer note

When adding new GUI components, test in both light and dark OS themes if possible. If a status cell is readable only in one theme, treat it as a bug.

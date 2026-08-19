# ADR 0041: Use docs/OPEN_ITEMS.md as the canonical backlog and technical-debt tracker

## Status
Accepted

## Date
2026-05-14

## Context

ReliabilityX Pro has accumulated multiple sources of future-work information:

- root-level `ToDo list.txt`
- comments in `version_history.txt`
- known-gap sections in `ARCHITECTURE.md` and `CODEBASE_MAP.md`
- chat-level delivery notes
- temporary `CHANGESET_MANIFEST.md` files generated during patch delivery

This creates a maintenance risk because some files are temporary, overwritten, or not consistently updated. The project also now uses simplified patch ZIP delivery: the user performs whole-project ZIP backups independently, so patch ZIPs should not include stamped backup files or persistent manifests unless explicitly requested.

The project needs one durable, versioned, human-readable place to track actionable open items, technical debt, status, priority, evidence, and next actions.

## Decision

Create `docs/OPEN_ITEMS.md` as the canonical backlog and technical-debt tracker.

`docs/OPEN_ITEMS.md` must be updated whenever a change:

- introduces a new open item or technical debt
- completes an existing open item
- defers, cancels, or changes the priority/status of an open item
- reveals a mismatch between documentation and actual runtime code

`AI_INSTRUCTIONS.md` is updated so that AI-assisted development must review `docs/OPEN_ITEMS.md` before modifying code, and must include OPEN_ITEMS updates in the definition of done when relevant.

Root-level `ToDo list.txt` is no longer the authoritative tracker. It should only point maintainers to `docs/OPEN_ITEMS.md`.

`CHANGESET_MANIFEST.md` must not be used as a long-term backlog or change tracker because it is temporary and easily overwritten. Delivery summaries remain in the ChatGPT response, while permanent records are kept in:

- `docs/version_history.txt`
- `docs/OPEN_ITEMS.md`
- `docs/adr/*.md`
- `docs/ADR_INDEX.md`
- `docs/ARCHITECTURE.md`
- `docs/CODEBASE_MAP.md`
- `docs/README.md`


### Detailed open-item format requirement

Starting from 2026-05-15, new ReliabilityX Pro open items must be traceable enough for future AI maintainers and human developers. A new open item must not be recorded as only a title or short bullet. It must include, at minimum:

- `Priority`
- `Status`
- `Area`
- `Evidence`
- `Impact / Risk`
- `Next Action`
- `Acceptance Criteria`
- `Notes for future AI maintainers` when needed

The purpose is to preserve why the item exists, what code/module is affected, what risk it creates, what fix is expected, and how completion will be verified.

## Consequences

### Positive

- Future maintainers have one stable backlog file to inspect before planning work.
- The AI development workflow becomes less likely to forget known technical debt.
- Completed or cancelled items remain traceable without cluttering active runtime folders.
- Temporary patch delivery files no longer compete with permanent project documentation.

### Trade-offs

- Every patch that affects scope or technical debt needs one extra documentation check.
- Some historical items from `ToDo list.txt` must be normalized into the new ID/status format.
- `OPEN_ITEMS.md` must be maintained carefully to avoid becoming stale.

## Implementation Notes

The initial `docs/OPEN_ITEMS.md` includes current open items identified from the latest project ZIP and existing documentation, including:

- ChannelSettingDialog diagnostics thread-boundary risk
- MeasureEngine Phase 1 service wiring
- Telegram PDF active-scope dispatch
- Trend history continuity across stop/restart
- Environment runtime/chamber telemetry
- Relay/channel matrix synchronization
- Measurement recipe provenance
- Mock hardware GUI smoke testing
- Emergency stop separation from graceful stop
- Channel archival/draft cleanup
- Build/dependency/artifact cleanup
- Legacy snapshot organization

## Related Files

- `docs/OPEN_ITEMS.md`
- `AI_INSTRUCTIONS.md`
- `docs/ADR_INDEX.md`
- `docs/ARCHITECTURE.md`
- `docs/CODEBASE_MAP.md`
- `docs/README.md`
- `docs/version_history.txt`
- `ToDo list.txt`

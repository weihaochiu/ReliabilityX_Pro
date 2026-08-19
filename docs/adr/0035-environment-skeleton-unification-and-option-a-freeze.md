# ADR 0035: Environment Skeleton Unification and Option A Freeze

## Status
Accepted

## Context
The user confirmed:
1. Keep Option A:
   `channel_setting_dialog` lets the user choose Environment first, then constrains relay.
2. Vacuum Glovebox and Indoor tabs should adopt the same upper skeleton as Climate.
3. Hardware-facing Connection / Status / Control for glovebox and indoor are not ready yet.
4. Environment Recipe should not be applied to hardware yet; only selection / display /
   persistence should be implemented for now.

## Decision
1. Freeze Option A as the current architecture rule.
2. Promote Relay Assignment and Environment Recipe to shared environment widgets.
3. Upgrade Vacuum Glovebox and Indoor tabs to the same upper skeleton:
   - Instance
   - SMU Relay Assignment
   - ISOS / Environment Recipe
4. Use explicit `Not Ready Yet` placeholders for hardware-facing lower sections.

## Consequences
- Three environment tabs become structurally consistent
- UI can advance without pretending hardware control already exists
- Later glovebox/indoor hardware integration can attach to the same skeleton

# ADR 0036: Environment Recipe Editor Shared-Entry Skeleton

## Status
Accepted

## Context
The user decided:
1. Use SystemConfigDialog as the formal main entry for Environment Recipe editing
2. Also place a small shortcut button in Climate / Glovebox / Indoor tabs
3. The shortcut must switch to the same shared editor page, not open separate dialogs

## Decision
1. Create a dedicated `EnvironmentRecipeTab`
2. Add three editor models:
   - ClimateRecipeEditor
   - GloveboxRecipeEditor
   - IndoorRecipeEditor
3. Add shortcut-button signals from the three environment tabs
4. Let SystemConfigDialog switch to the shared tab and preselect environment type

## Consequences
- One authoritative recipe editor entry point
- Convenience shortcuts from context tabs
- No duplicated editor logic across the three environment tabs

# ADR 0040: Cycle Measurement Toggle Confirmation and Logical Label De-duplication

## Status
Accepted

## Context
Dynamic logical channels introduced environment-specific labels such as `CH_V01`, `CH_I01`, and `CH_C01`. In the main channel card, the existing checkbox was visually ambiguous because users could interpret it as "channel exists" rather than "this channel participates in cyclic measurement". The dynamic channel list also exposed legacy or draft fixed-channel records that had no complete relay path, which could result in duplicate derived labels such as two `CH_I01` cards.

## Decision
1. The channel card checkbox is retained, but its meaning is explicitly renamed:
   - checked: `開始循環量測  CH_x##`
   - unchecked: `暫停循環量測  CH_x##`
2. Changing the checkbox from the main card now requires a confirmation dialog before writing `is_enabled`.
3. The Channel Setting dialog uses the same cyclic-measurement wording and also requests confirmation when the checkbox is changed by the user.
4. Draft or legacy channel records without both `relay_pos` and `relay_neg` are hidden from the active main list.
5. Logical label generation reserves explicit labels first, then assigns derived labels to valid unlabeled legacy channels in internal-id order. This prevents duplicate visible labels when an older record did not persist `channel_label`.
6. Delivery ZIPs for this phase contain only updated overwrite files and documentation, without same-folder stamped backup files, because the operator already performs whole-project ZIP backups.

## Consequences
- Users get a double-check before accidentally starting or pausing a long-duration experiment channel.
- `結束實驗 / 移除` remains the only operation that releases the active logical channel; unchecking the cyclic measurement checkbox only pauses scheduling.
- Empty fixed-channel legacy records such as `+R-- / -R--` no longer appear as active logical channel cards.
- Future label generation will not create a new `CH_I01` if an existing valid unlabeled Indoor channel is already being displayed as `CH_I01`.

# UI_SURFACE.md — Retention Copilot
## Version: v1.0-draft · 2026-10-08
## Engineer sign-off: [ ] — date: ______

> Drafted from ARCHITECTURE.md (DEC-01, DEC-14, DEC-16, DEC-17, DEC-19) and the screen-state
> decisions (D-16, D-17, D-23–D-25, D-27, D-46). Fields that could not be inferred are marked
> **TBD — [question]**; all are collected in the Consolidated Gap List at the end.
> Gate note: this draft assumes ARCHITECTURE.md v1.0 is signed off unchanged.
>
> **Confirmed:** G-1 no login · G-2 "Retry connection" button on the crash banner · G-3 "Starting up…"
> with Start call disabled · G-4 live transcript shown · G-5 customer mood + trend shown · G-6 "End call"
> button · G-7 replay of recorded test calls from a UI control (script kept for automated eval runs) ·
> G-8 no type tag · G-9 mic-denied message with "Try again" · G-10 same message as both-lanes-failed ·
> G-11 reconnect note shown · G-12 "New call" button · G-13 "Log could not be saved" with call ID ·
> G-14 readable per-turn timeline, expandable to raw JSON · G-15 no download · G-16 toggle role buttons.
> **Speaker role (D-51, decided):** one microphone; "Sales Rep" and "Customer" buttons set who is speaking.
> **Button behaviour (G-16, confirmed):** toggle — click a role button to start speaking as
> that role; clicking the other button switches role and closes the current turn; clicking the active
> button again pauses the mic.

## Amendment Log
| Date | Screen/Section | Change | Reason |
|---|---|---|---|
| 2026-10-08 | — | Initial draft | Phase 1 UI Discovery |
| 2026-10-08 | All TBDs | Default answers applied to G-1–G-15 | Unblock Phase 2/3; engineer confirms at sign-off |
| 2026-10-08 | Global; Live Call Assist | G-1–G-4 confirmed; G-2 changed to a Retry connection button | Engineer answers |
| 2026-10-08 | Live Call Assist | G-5–G-16 confirmed; G-7 adds a Replay test call control | Engineer answers |
| 2026-10-08 | Live Call Assist; Customer Audio removed | Speaker role set by "Sales Rep" / "Customer" buttons on one mic (D-51); Customer Audio screen removed | Engineer decision on OQ-3 |

---

## Application Profile (from Interrogate)
- Surface type: UI+API (browser page plus a WebSocket backend)
- Auth: None (G-1, confirmed)
- Roles: Sales rep only (D-03)
- Data baseline: Seeded — synthetic KB documents and recorded test calls

---

## Global Elements

### Navigation
- Type: None — single working screen; the log viewer opens from the call-ended card.
- Present on: N/A
- Items: N/A
- Role-conditional items: NONE

### Authentication Shell
- None (G-1, confirmed): the page opens directly. Logout, session expiry and login redirects N/A.

### Back Navigation
- Mechanism: Explicit "Back to call screen" button on Call Log Viewer.
- Screens with explicit back controls: Call Log Viewer → Live Call Assist.

### Breadcrumbs
- Present: N

### Global Error Boundary
- Behaviour: Inline banner at the top of Live Call Assist.
- Backend silent for 5 seconds (D-25): banner with a rep-friendly crash message telling the rep to
  handle the call or call the customer back later. Cleared automatically on reconnect (D-46).
- User action available: "Retry connection" button (G-2, confirmed) — forces an immediate reconnect
  attempt; automatic reconnect continues in the background.

### App-level Loading
- Behaviour: "Starting up…" screen with Start call disabled until the backend reports the embedding
  model and KB are ready (G-3, confirmed).
- Applies to: Initial app load only.

### Toast / Notification System
- Present: N — all status messages appear inline in the suggestion panel or the top banner (D-23, D-24, D-25).

---

## Screen Inventory

| Screen | Type | Route | Journey | Roles | Auth Required |
|---|---|---|---|---|---|
| Live Call Assist | Dashboard | `/` | Handle a retention call with guidance | Sales rep | N |
| Call Ended Card | Modal | (overlay on `/`) | Close out a call and reach its log | Sales rep | N |
| Call Log Viewer | Detail | `/logs/{call_id}` | Investigate what the copilot did on a call | Sales rep | N |

Inventory checks:
- Every entity the rep needs to see (Suggestion, Call, Log record) has a screen surface.
  Turn (transcript) and Summary (mood) are shown on Live Call Assist; Offer document and Checkpoint are internal.
- Every action in the decisions has a surface: start call, role switch, replay, end call, open log.
- The rep's journey is complete without console access; recorded-call replay is available from a UI
  control (G-7). Automated eval and ablation runs still use the replay script.

---

## Screen Specifications

## Live Call Assist
**Type:** Dashboard
**Route:** `/`
**Journey:** Handle a retention call with guidance
**Roles:** Sales rep
**Trigger:** Direct navigation
**Auth required:** N

### Data Displayed

| Section | Entity / Field | Source | Notes |
|---|---|---|---|
| Status bar | Call.call_id, Call.status | WebSocket | Status: Ready / Live / Reconnecting / Ended |
| Status bar | Connection state | WebSocket heartbeat | Drives the 5-second crash banner (D-25) |
| Role controls | Active role (rep / customer / none) | Client state | Active button visibly highlighted with "Speaking as: Sales Rep / Customer" |
| Suggestion panel | Suggestion.text, Suggestion.lane | WebSocket | Lane label: "Quick tip" (fast) or "Suggested approach" (slow) (D-17) |

| Suggestion panel | Suggestion.display_state | Computed | 3 most recent shown; older fade out (D-17) |
| Suggestion panel | Status message | WebSocket | "No suggestions at the moment", "Nothing new to suggest", "Failed fetching docs", "Handle the call until this is fixed" |
| Transcript panel | Turn.speaker, Turn.text (masked) | WebSocket | Live transcript shown (G-4, confirmed) |
| Mood | Summary.mood, Summary.mood_trend | WebSocket | Customer mood and trend shown (G-5) |

### Actions

| Label | Scope | Trigger | Condition | Outcome |
|---|---|---|---|---|
| Start call | Screen | Button | Status = Ready | Browser asks for microphone permission; on grant, new Call created, WebSocket opened, status → Live; no role active yet (mic paused) |
| Replay test call | Screen | Dropdown (S1–S5) + button | Status = Ready | Starts a call and streams the selected recording's utterances, each preceded by its role message, through the same /ws/audio path as the mic (INV-10); mic and role buttons disabled while replaying (G-7) |
| Sales Rep | Screen | Toggle button | Status = Live | Mic streams tagged role=rep; if Customer was active, the customer turn closes (D-51, G-16) |
| Customer | Screen | Toggle button | Status = Live | Mic streams tagged role=customer; if Sales Rep was active, the rep turn closes (D-51, G-16) |
| End call | Screen | Button | Status = Live | Signals hang-up (G-6). Status → Ended; in-flight model calls dropped; Call Ended Card opens (D-27) |

### States

| State | Trigger | What Renders |
|---|---|---|
| Ready | Page loaded, no call | Start call enabled; panel empty |
| Starting up | Backend still loading models | "Starting up…", Start call disabled (G-3) |
| Mic denied | Browser microphone permission refused | "Microphone access is needed to start a call" with "Try again" (G-9) |
| Replaying | Replay test call running | "Replaying S{n}" label; role indicator follows the recording; role buttons and Start call disabled; End call available |
| Live, no role active | Call started, no role button pressed | Both role buttons enabled; "Choose who is speaking" hint |
| Speaking as rep / customer | Role button active | Active button highlighted; "Speaking as: …" label |
| Live, no suggestions yet | Call started, nothing surfaced | "No suggestions at the moment" (D-23 area) |
| Populated | Suggestions received | Up to 3 most recent suggestions with lane labels; older fade (D-17) |
| Nothing new | Agents chose to show nothing this turn (D-16) | Recent suggestions stay, plus "Nothing new to suggest" |
| KB fetch failed | KB search error (D-23) | "Failed fetching docs" in the panel; fast-lane tips may still show |
| Degraded — both lanes failed | Retries exhausted (D-24) | "Handle the call until this is fixed" |
| Degraded — Permission Layer error | Permission Layer fails closed (D-18) | Nothing new shown. **N0:** same message as both lanes failed, or its own? |
| Backend silent | No heartbeat for 5 s (D-25) | Top banner: rep-friendly crash message (handle the call or call back later) with "Retry connection" button (G-2) |
| Reconnected / resumed | Backend back, call resumed from checkpoint (D-46) | Banner clears; panel restores last displayed suggestions. **N1:** show a brief "Reconnected — some speech may have been missed" note (D-48)? |
| Ended | End call / hang-up | Call Ended Card opens |

### Async Behaviour
- Pattern: WebSocket (bidirectional: audio up; suggestions, status and heartbeat down)
- Scope: Whole screen

### Panels

| Panel Name | Data Source | Empty State | Refresh | Drill-down Target |
|---|---|---|---|---|
| Status bar | WebSocket | "Ready" | Real-time | NONE |
| Suggestions | WebSocket | "No suggestions at the moment" | Real-time | NONE |
| Transcript (if kept, G-4) | WebSocket | Empty | Real-time | NONE |
| Mood | WebSocket | Hidden until first summary | Real-time | NONE |

---

## Call Ended Card
**Type:** Modal
**Route:** Overlay on `/`
**Journey:** Close out a call and reach its log
**Roles:** Sales rep
**Trigger:** Live Call Assist — End call (or hang-up, G-6)
**Auth required:** N

### Data Displayed

| Section | Entity / Field | Source | Notes |
|---|---|---|---|
| Main | Call.call_id | Backend | |
| Main | "Log saved" confirmation | Backend | Shown once the log file is flushed |

### Actions

| Label | Scope | Trigger | Condition | Outcome |
|---|---|---|---|---|
| Open log | Screen | Link | Log saved | Navigate to Call Log Viewer for this call_id |
| New call | Screen | Button | Always | **N2:** return to Ready on Live Call Assist (assumed) |

### States

| State | Trigger | What Renders |
|---|---|---|
| Saving | Call ended, log still flushing | "Saving log…", Open log disabled |
| Populated | Log saved | Call ID, "Log saved", Open log, New call |
| Error | Log write failed | **N3:** message and whether the call ID is still shown |

### Async Behaviour
- Pattern: Load-once
- Scope: Whole modal

### Modal Configuration
- Opens from: Live Call Assist — End call
- Type: Info
- Confirm action: Open log → navigates to Call Log Viewer
- Cancel action: New call → dismiss (G-12)
- Parent screen behaviour on close: Reset to Ready

---

## Call Log Viewer
**Type:** Detail
**Route:** `/logs/{call_id}`
**Journey:** Investigate what the copilot did on a call
**Roles:** Sales rep (and judges during the demo)
**Trigger:** Call Ended Card — Open log
**Auth required:** N

### Data Displayed

| Section | Entity / Field | Source | Notes |
|---|---|---|---|
| Main | Log record list, by turn | JSON-lines log file | One row per step (D-28) |
| Row detail | input (masked), tool_calls, model_reasoning, retries, provider, tokens, cost, permission_outcome, shown, timestamps | Log record | **N4:** rendered as a readable per-turn timeline, or raw JSON with expand/collapse? |
| Row detail | Permission decision (outcome, reason, removed text) | Permission decision record | Highlights Mask / Deny for the attack demo (DEC-22) |

### Actions

| Label | Scope | Trigger | Condition | Outcome |
|---|---|---|---|---|
| Back to call screen | Global | Button | Always | Navigate to Live Call Assist |
| Download log | Screen | Button | Log exists | **N5:** needed, or is viewing enough? |

### States

| State | Trigger | What Renders |
|---|---|---|
| Loading | Log file read in progress | Spinner |
| Populated | Log loaded | Per-turn records |
| Error | Log missing or unreadable | "Log not found for this call" with Back |
| Record-state variant | Call resumed after crash (D-48) | Marker row: "Possible missed turns during restart" |

### Async Behaviour
- Pattern: Load-once
- Scope: Whole screen

---

## Consolidated Gap List
All UI gaps G-1 – G-16 are closed (see header).

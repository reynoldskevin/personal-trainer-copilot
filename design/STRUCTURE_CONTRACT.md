# Structure Contract — Knowledge Graph Coaching Platform

> The shared, named structure both the dev build (`tdd-ticket-loop`) and the design build
> (Claude Design) build against. **Names are the API between the two tracks — stable, do not
> rename silently.** A rename is a breaking change to both tracks.
> Token source: **neutral placeholders** (no brand source detected; Claude Design assigns values).
> Form factor: **desktop-first responsive web, landscape** (coach tool).

## Flow

```
members-list → (select member) → member-overview ─┬─ workout-generator
                                                  ├─ insights   (M2)
                                                  ├─ trends      (M2)
                                                  └─ chat        (M2)
```
The hub (`member-overview` + tabs) shares one shell: `app-header`, `member-context-rail`, and
`tab-nav` persist across all per-member tabs. Back-edge from any hub tab → `members-list`.

## Token slots
| Slot | Bound to | Used by |
|---|---|---|
| --color-bg / --color-surface | placeholder | all regions, cards |
| --color-text / --color-text-muted | placeholder | all text |
| --color-border | placeholder | regions, inputs, chips |
| --color-accent | placeholder | Button, TabNav, GenerateControl, ChatMessage |
| --color-safe / --color-warn / --color-danger / --color-info | placeholder | StatusChip, InjuryBadge, MetricStat, ExerciseRow |
| --space-xs…xl | placeholder | all layout |
| --radius-sm / md / card / pill | placeholder | cards, chips, inputs |
| --font-display / body / mono | placeholder | headings, body, labels |

## Components
| Component | Purpose | Appears in | Token slots | States |
|---|---|---|---|---|
| AppHeader | App title + coach identity | all screens (`app-header`) | surface, text, space | default |
| SearchBar | Client-side member filter (no backend) | members-list (`list-toolbar`) | surface, border, radius-md | idle, typing |
| MemberListItem | Member row → member-overview | members-list (`members-list`) | surface, border, space | default, hover |
| MemberContextRail | Persistent member identity/quick facts | hub (`member-context-rail`) | surface, space, text-muted | default, loading |
| TabNav | Hub tab navigation | hub (`tab-nav`) | accent, border, radius-sm | active, disabled(M2) |
| InjuryBadge | SNOMED-grounded injury chip | rail, overview-injuries | warn, danger, radius-pill | active, resolved |
| StatusChip | Variant chip; powers safety + risk flags | workout-plan, insight-flags | safe/warn/danger/info, radius-pill | safe, warn, danger, info |
| Button | Generic action | (shared) | accent, radius-md, space | default, hover, disabled, loading |
| GenerateControl | Goal-hint input + Generate | workout-controls | accent, border, space | idle, generating, disabled |
| WorkoutPlanCard | Renders a WorkoutPlan | workout-plan | surface, radius-card, space | result, empty |
| ExerciseRow | One prescribed exercise + SafetyFlag | inside WorkoutPlanCard | border, safe, space | safe, flagged |
| SupportingContextPanel | GraphRAG retrieved context (/retrieve) | workout / insights / chat | surface, text-muted, radius-md | collapsed, expanded, empty |
| InsightReportCard | Progress summary + notes | insight-summary | surface, radius-card, space | result, empty |
| TrendChart | Adherence/biometric time-series | trends-charts | accent, border, space | data, empty, loading |
| MetricStat | KPI tile (value + delta) | overview-metrics, trends-metrics | surface, safe, danger, radius-md | up, down, flat |
| ChatThread | Scrollable list of ChatMessage | chat-thread | bg, space | populated, empty |
| ChatMessage | Single bubble (coach / AI) | inside ChatThread | surface, accent, radius-md | coach, ai |
| ChatComposer | Ask-about-member input (context-only) | chat-composer | surface, border, radius-pill | idle, sending, disabled |
| StatusView | Shared empty / loading / error placeholder | any `*-status` region | text-muted, space-lg | empty, loading, error |

## Screens

### members-list — Members
- status: scheduled · milestone: 1 · ticket(s): 010
- states: loading, empty, error, populated
- wireframe: design/screens/members-list.html
- regions (in order):
  - `app-header` → [AppHeader]
  - `list-toolbar` → [SearchBar]
  - `members-list` → [MemberListItem × n]
  - `list-status` → [StatusView]
- flow: (entry) → this → member-overview

### member-overview — Member · Overview
- status: scheduled · milestone: 1 · ticket(s): 010 · hub default tab
- states: loading, error
- wireframe: design/screens/member-overview.html
- regions (in order):
  - `app-header` → [AppHeader]
  - `member-context-rail` → [MemberContextRail, InjuryBadge]
  - `tab-nav` → [TabNav]
  - `overview-metrics` → [MetricStat × n]
  - `overview-injuries` → [InjuryBadge × n]
  - `overview-goals` → (goal list)
  - `overview-recent-activity` → (timeline)
- flow: members-list → this → {workout-generator, insights, trends, chat}

### workout-generator — Member · Workout
- status: scheduled · milestone: 1 · ticket(s): 010
- states: idle, generating, result, error
- wireframe: design/screens/workout-generator.html
- regions (in order):
  - `app-header` → [AppHeader]
  - `member-context-rail` → [MemberContextRail, InjuryBadge]
  - `tab-nav` → [TabNav]
  - `workout-controls` → [GenerateControl]
  - `workout-plan` → [WorkoutPlanCard → ExerciseRow, StatusChip]
  - `workout-supporting-context` → [SupportingContextPanel]
- flow: member-overview ↔ this

### insights — Member · Insights
- status: scheduled · milestone: 2 · ticket(s): 015
- states: loading, result, empty, error
- wireframe: design/screens/insights.html
- regions (in order):
  - `app-header` → [AppHeader]
  - `member-context-rail` → [MemberContextRail, InjuryBadge]
  - `tab-nav` → [TabNav]
  - `insight-summary` → [InsightReportCard]
  - `insight-flags` → [StatusChip × n]
  - `insight-supporting-context` → [SupportingContextPanel]
- flow: member-overview ↔ this

### trends — Member · Trends
- status: scheduled · milestone: 2 · ticket(s): 015 · dedicated analytics tab
- states: loading, empty, error
- wireframe: design/screens/trends.html
- regions (in order):
  - `app-header` → [AppHeader]
  - `member-context-rail` → [MemberContextRail, InjuryBadge]
  - `tab-nav` → [TabNav]
  - `trends-metrics` → [MetricStat × n]
  - `trends-charts` → [TrendChart × n]
- flow: member-overview ↔ this

### chat — Member · Chat
- status: scheduled · milestone: 2 · ticket(s): 015 · context-only (no client-reply drafting)
- states: empty, loading, error
- wireframe: design/screens/chat.html
- regions (in order):
  - `app-header` → [AppHeader]
  - `member-context-rail` → [MemberContextRail, InjuryBadge]
  - `tab-nav` → [TabNav]
  - `chat-thread` → [ChatThread → ChatMessage]
  - `chat-composer` → [ChatComposer]
  - `chat-supporting-context` → [SupportingContextPanel]
- flow: member-overview ↔ this

## Sequencing note (M1 shell, M2 tabs)
The hub shell (`app-header`, `member-context-rail`, `tab-nav`) and `TabNav` ship in **M1 (ticket
010)**. The Insights / Trends / Chat tabs are **visible but disabled**, rendering a `StatusView`
"coming in M2" until **M2 (ticket 015)** activates them. No structural rework between milestones.

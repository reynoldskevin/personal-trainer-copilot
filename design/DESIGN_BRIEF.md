# Design Brief — Knowledge Graph Coaching Platform (load into Claude Design)

## How to load
Run **`/design-sync`** from this repo to push this bundle into a claude.ai/design design-system
project, one component at a time (drives the `DesignSync` tool — never a wholesale replace). Cards
are grouped **Screens** / **Components** via their first-line `<!-- @dsCard group="…" -->` markers.

## The seam (read first)
This bundle exists so the **dev track** (`tdd-ticket-loop`) and the **design track** (you, in Claude
Design) can run at the same time and merge with minimal conflict.

- **Design decides:** token *values* (`tokens.css`) and component *internals* (`components/*.html`).
- **Design does NOT change:** screen structure, region names, or component names — those are the
  contract dev is building against in parallel. Keeping the names is what lets finished designs drop
  into pre-agreed slots.

Every wireframe is greyscale and consumes **only** `var(--token-*)` — swapping token values re-themes
everything. No hardcoded colours, spacing, radii, or type anywhere.

## Brand source
**None detected** — `tokens.css` ships neutral placeholder values. Assign the real brand palette,
spacing, radii, and type here. The **safety family** (`--color-safe / --color-warn / --color-danger /
--color-info`) is load-bearing: it drives injury/safety/risk flags (`StatusChip`, `InjuryBadge`,
`ExerciseRow`, `MetricStat`) and must stay clearly differentiable and accessible.

## Form factor
Desktop-first responsive web, landscape (a coach's working tool). Hub screens use a left
`member-context-rail` + main content column.

## Screens
| Screen id | Title | Milestone | Status |
|---|---|---|---|
| members-list | Members | 1 | scheduled |
| member-overview | Member · Overview | 1 | scheduled |
| workout-generator | Member · Workout | 1 | scheduled |
| insights | Member · Insights | 2 | scheduled |
| trends | Member · Trends | 2 | scheduled |
| chat | Member · Chat | 2 | scheduled |

No backlog/structure-only screens — this is the full UI surface. Full names + regions:
`STRUCTURE_CONTRACT.md` (in this bundle).

## Components
19 shared components under `components/` (one card each): AppHeader, SearchBar, MemberListItem,
MemberContextRail, TabNav, InjuryBadge, StatusChip, Button, GenerateControl, WorkoutPlanCard,
ExerciseRow, SupportingContextPanel, InsightReportCard, TrendChart, MetricStat, ChatThread,
ChatMessage, ChatComposer, StatusView. Iterate a component once and it applies everywhere it's
referenced.

## Sync command
`/design-sync` — pushes cards one at a time. Do not wholesale-replace the project.

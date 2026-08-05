---
id: 010
title: Minimal coach dashboard (Next.js)
status: tests-authored
depends_on: [009]
branch: ticket/010-coach-dashboard
base_branch: ticket/009-fastapi-endpoints
test_command: "npm --prefix frontend test"
full_suite_command: ".venv/bin/ruff check . && .venv/bin/mypy app && .venv/bin/python -m pytest -q && npm --prefix frontend test"
attempts: 0
---

## Description
Minimal Next.js dashboard: member list → member detail → "Generate workout" → render the plan with
**safety flags** and the supporting context.

## Acceptance criteria
- [ ] Member list + detail views call the API
- [ ] "Generate workout" renders the returned `WorkoutPlan` with visible safety flags
- [ ] Loading + error states handled
- [ ] Component/smoke test passes

## Test plan (orchestrator authors these)
- unit: `frontend/__tests__/dashboard.test.tsx` — drives the top-level `Dashboard` with a mocked
  fetch; asserts the contract regions/components of the members-list + member-overview +
  workout-generator screens, client-side SearchBar filtering, the M2 tabs' StatusView, the
  generate-workout flow rendering a WorkoutPlanCard with safety flags (no contraindicated row),
  and loading/error states.

## Wireframe & contract
- screens: `members-list`, `member-overview`, `workout-generator` (design/screens/*.html)
- hub shell + TabNav now: Overview + Workout active; Insights/Trends/Chat visible but render
  `StatusView` "coming in M2" (activated in ticket 015)
- SearchBar = client-side filter over the loaded list (no backend search endpoint)
- consume token slots only (design/tokens.css): --color-*, --space-*, --radius-*, --font-*

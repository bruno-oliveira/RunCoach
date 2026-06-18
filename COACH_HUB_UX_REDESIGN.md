# Coach Hub & Surrounding-UX Redesign Proposal

> Status: **APPROVED — implementing Phases 0–2.** Decisions locked (see §8).
> This document is the agreed plan; §8 records the owner's calls.

## 0. Locked decisions

1. **Nav naming** → Two entries: **Coach** + **Progress** (§4.3).
2. **Trail meals** → Relabel to "Trail Fuel Ideas" now; real recipes later (§6 Option B).
3. **Scope** → **Phases 0–2** (IA fixes). Phase 3 (real trail recipes) deferred.
4. **Progress charts** → Proceed with the recommended ~6 keep-list (§4.2).

## 1. Diagnosis

The core loop — *generate a personalized plan* — is coherent and well-built.
The features **around** it have grown one-at-a-time, each bolted on where it was
easiest to add rather than where a runner would look for it. The result is three
concrete, observable problems:

### 1.1 The Coach Hub is two products in one menu entry

`/analytics` (`analytics.html`) is labeled **"Coach Hub"** in the nav but is
routed and structured like an analytics dashboard. It has **five tabs** — Today,
Signals, Progress, Insights, Evolution — and the **Progress tab alone holds ~15
charts/cards**.

It mixes two incompatible voices:

- A **coach persona** (Today tab, "Coach's Note", coach banner, stance/summary)
  that promises *interpretation*.
- A **raw-metrics dump** (Training Load, CTL/ATL/Form, pace-zone distribution,
  aerobic efficiency, etc.) that hands over charts without interpretation.

That split is exactly why it "feels like a foreign menu entry": the label and
the persona promise a coach; the body delivers a Strava clone.

### 1.2 Charts are duplicated across tabs

The Evolution tab is largely a re-skin of charts already on Progress:

| Chart | Appears in Progress | Appears in Evolution |
|-------|:---:|:---:|
| Aerobic Efficiency | ✓ (456–467) | ✓ (662–669) |
| Weekly Volume | ✓ (417–428) | ✓ (671–677) |
| Pace Trend | ✓ (442–453) | ✓ "Pace Evolution" (644–651) |
| VDOT / Fitness progression | (via predictions) | ✓ (653–660) |

Evolution can be removed as a top-level destination with almost no information
loss.

### 1.3 Trail content is fragmented, and "trail meals" are not meals

Trail-specific guidance is scattered across **three unrelated places**:

- **Trail fuel + trail tips** → buried inside a plan's *Nutrition* sub-tab
  (`nutrition_panel.html` 72–167).
- **Race readiness gauge** → Coach Hub → *Progress* tab, plan-scoped
  (`analytics.html` 259–271).
- **Race prep** → its own top-level page (`/race-prep`).

And the data models don't line up:

- Recipes page (`recipes.html`) has **5 categories**: breakfast, lunch, dinner,
  snack, post-workout. **No trail / trail-ready category.**
- Regular meals (`meals_*.json`) carry `instructions`, `ingredients`,
  `prep_time`, `cook_time`.
- "Trail-ready meals" inside a plan come from a *separate* generator
  (`nutrition_content.py → generate_trail_fuel_ideas()`) and only have
  `name / phase / category / carbs / note` — **no instructions, no
  ingredients.**

So a trail runner sees "trail-ready meals" they cannot make, with nowhere on the
recipes page to land.

### 1.4 Root cause

There is **no information architecture**. Features map to "where it was easy to
add," not to "what the runner is trying to do." Everything below is downstream of
fixing that.

---

## 2. Design principles

1. **One voice per surface.** A screen is either *the coach talking to you*
   (narrated, interpreted) or *a reference table* (browseable data). Never both
   pretending to be the other.
2. **No chart without a question.** Every chart must answer a question the runner
   actually asks. If two charts answer the same question, keep one.
3. **Content lives where the job is.** Trail content belongs together, mapped to
   "I'm training for a trail race," not sprinkled across nutrition/analytics/prep.
4. **Don't promise what you can't deliver.** If an item has no recipe, don't call
   it a meal.

---

## 3. Target information architecture

A runner comes to RunCoach to do **four jobs**. Every screen should map to one:

| Job | Surface | Voice |
|-----|---------|-------|
| "Build / adjust my plan" | Plan generation + My Plans | form / structured |
| "What do I do today & how am I doing?" | **Coach** (narrated) | coach persona |
| "Show me my real progress" | **Progress** (small chart set) | reference |
| "Get me ready for race day" | **Race Prep** (incl. all trail content) | coach persona |
| (support) "What do I eat / cook?" | Recipes | browseable catalog |

Net nav change: **"Coach Hub" splits into "Coach" + "Progress"**, and trail
content consolidates under **Race Prep**.

---

## 4. Coach Hub redesign: 5 tabs → 2 surfaces

### 4.1 Surface A — **Coach** (the narrated view)

Absorbs **Today** + the human-readable parts of **Insights** + the "why did the
coach decide this" parts of **Signals**.

Contains:
- Coach's Note (recognition-first voice) — *keep*
- Coach banner / stance summary — *keep*
- Today's Session card — *keep*
- Readiness & Form card — *keep*
- This Week's Execution strip — *keep*
- Coach's Assessment + key insights — *merged in from Insights, narrated*
- **"Why this call?"** expandable → the Signals radar + phase-weighting table,
  demoted from a top-level tab to an on-demand explainer.

### 4.2 Surface B — **Progress** (the reference view)

A **deliberately small** set of trend charts the coach actually references.
**[NEEDS DECISION]** on the exact keep-list; my recommended cut:

**Keep (≈5–6):**
- Race Readiness gauge + Gap analysis (when a plan is selected)
- Weekly Volume
- Fitness / Fatigue / Form (single load chart)
- Pace Trend
- Personal Records / hero stats strip
- Activity heatmap (calendar)

**Cut or fold:**
- Evolution tab entirely (duplicate — see §1.2)
- Aerobic Efficiency (niche; fold into an expandable if kept at all)
- Predicted-vs-Actual + Race Predictions (collapse into the Readiness gauge area)
- Pace Zone Distribution (niche; expandable)
- Standalone Signals tab (moved into Coach as "Why this call?")

From **5 tabs / ~25 panels** down to **2 surfaces / ~12 elements**, with the
heavy data behind progressive disclosure.

### 4.3 Naming

Rename the destination from "Coach Hub" to match its split identity.
**[NEEDS DECISION]**: nav becomes **"Coach"** and **"Progress"** as two entries,
or a single **"Coach"** entry with the two surfaces as internal tabs. I recommend
two entries — it makes the voice split explicit and removes the "hub of
everything" feeling.

---

## 5. Trail content consolidation

Move **all** trail-specific content under **Race Prep** (`/race-prep`), shown when
the runner's goal race is Trail:

- Trail fuel ideas (before / during / after)
- Trail fuelling tips (topic-filtered)
- Race readiness + gap analysis for the trail plan
- Existing race-day protocol / pacing / mental checkpoints

The plan's Nutrition tab keeps a **short summary + a link** ("See full trail
fuelling in Race Prep") rather than hosting the full content. This gives trail
runners the single "everything for my race" home that's missing today.

---

## 6. Recipe / trail-meal model fix

**[NEEDS DECISION]** — two viable directions:

**Option A — Make trail fuel real recipes (higher effort, higher payoff).**
Promote trail fuel items into the meal model with `instructions` + `ingredients`,
add a **"Trail Fuel"** category to the recipes page, and have plans link into it.
Runners can actually make the food; trail fuel becomes first-class.

**Option B — Relabel honestly (low effort).**
Rename "trail-ready meals" → **"Trail Fuel Ideas / Strategy"** everywhere, drop
the "meal" framing, and keep them as quick-reference items (name/carbs/note). No
false promise of a recipe.

Recommendation: **B now, A later.** Ship the honest relabel immediately to remove
the broken expectation, and treat full trail recipes as a follow-up content
project.

---

## 7. Phased rollout

Each phase is independently shippable and independently revertable.

1. **Phase 0 — Naming & honesty (tiny):** rename "trail-ready meals" → "Trail
   Fuel Ideas" (§6 Option B). Removes the worst false promise immediately.
2. **Phase 1 — Coach Hub collapse (biggest win):** merge to 2 surfaces (§4),
   delete the Evolution tab, demote Signals to an expandable. Pure IA — no new
   data needed.
3. **Phase 2 — Trail consolidation (§5):** move trail content under Race Prep,
   leave a summary+link in the nutrition tab.
4. **Phase 3 — Recipes (§6 Option A, optional):** trail fuel as real recipes +
   recipes-page category. Content-heavy; do only if we want trail to be a
   first-class cooking experience.

---

## 8. Decisions needed before coding

1. **Progress keep-list** (§4.2) — agree the ~5–6 charts to keep.
2. **Nav naming** (§4.3) — two entries ("Coach" + "Progress") vs one.
3. **Trail meals** (§6) — Option A (real recipes) vs B (honest relabel) now.
4. **Scope** — all four phases, or stop after Phase 1 + 2 (the IA fixes) and
   defer the recipes content work?

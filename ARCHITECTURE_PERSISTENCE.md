# Persistence Boundary (CQRS-lite)

This codebase deliberately uses **two** data-access styles. They are not
inconsistent — each has a defined place. This note records the rule so a raw
`db.query(...)` is read as *intended* in one layer and a *leak* in another.

## The rule

| Concern | Mechanism | Where |
|---------|-----------|-------|
| **Writes** (create / update / delete, ownership-guarded lookups) | Repositories implementing the `domain/repositories.py` protocols | `contexts/<x>/repositories.py`, `infrastructure/` |
| **Reads** (analytics, adaptation signals, derived metrics) | Thin query functions / query modules. Raw `db.query(...)` is allowed and expected here. | `contexts/<x>/queries.py`, the adaptation sub-modules, fitness/analytics services |
| **HTTP** | Routers delegate to services / repositories / query modules. **No raw `db.query` in routers.** | `web/routers/` |

The write side honors the repository protocols so it stays testable and
swappable. The read side is query-heavy, shape-specific, and rarely benefits
from a uniform CRUD interface — so it uses focused query functions instead of
forcing every read through a repository. This is "CQRS-lite": one write model
behind repositories, many purpose-built read paths.

## Why repositories don't cover reads

The adaptation engine and analytics paths issue bespoke aggregate / filtered
queries (effort trends, pace consistency, trail-run counts, week evolution).
Modeling each as a repository method would produce a sprawling, low-cohesion
interface. Keeping them as query functions:

- keeps the SQL next to the logic that consumes it,
- avoids a god-repository, and
- still keeps the SQL out of routers (the actual boundary we enforce).

## Enforced invariants

1. **Routers contain no raw `db.query` / `session.query`.** They use a
   repository, a service, or a query module. (CI lint + review.)
2. **Write paths go through a repository** so ownership and persistence stay in
   one place.
3. **Read query modules are named `queries.py`** (or live in a clearly-named
   analytics/adaptation service) and may use `db.query` freely — that is the
   documented read side, not a leak.

## Examples

- Write side: `SQLAlchemyPlanRepository`, `SQLAlchemyRunRepository`,
  `SQLAlchemyUserRepository`, `SQLAlchemyFavoriteRecipeRepository`.
- Read side: `app/contexts/runner/queries.py` (`count_prior_trail_runs`), the
  adaptation modules (`signal_computer`, `plan_adjuster`, …), and the fitness /
  analytics services.

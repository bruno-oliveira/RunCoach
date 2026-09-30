"""Run logging & enrichment services.

Nothing is re-exported here. This package used to lazily alias three names —
``RunEnrichmentService``, ``CompletionStats`` and ``WeekPulseGenerator`` — all
of which had been refactored into module-level functions and no longer existed
in their modules, so importing either name would fail for the first caller that
tried. Nothing imported them; callers reach the submodules directly (``from
app.contexts.runner.enrichment import completion_stats``). Removed rather than
corrected, for the same reason ``app/contexts/plan/__init__.py`` dropped its dead
aliases: a name for an abstraction nobody uses is a name waiting to disagree
with reality.
"""

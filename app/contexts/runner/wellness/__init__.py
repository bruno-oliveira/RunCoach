"""Runner wellness — the daily readiness check-in (how the runner *feels*).

Distinct from ``runner.fitness.readiness_service`` (race-readiness / VDOT). This
subpackage owns the morning check-in: capture, once-per-day upsert, scoring, and
the reads the adaptation engine and Coach's Note consume.
"""

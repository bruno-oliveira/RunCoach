"""Pure training science — no I/O, no ORM, no SQLAlchemy.

Sub-packages (read top → bottom):

    physiology/     — The runner's engine: VDOT, zones, HR, race predictions
    profiles/       — What you're training for: road, trail, backyard
    frequency/      — How many days you run (2→6): per-frequency composers
    periodization/  — Shaping the block: phases, mileage, long-run, quality caps
    workouts/       — What you do each day: builders, catalog, steps
    adaptation/     — How the plan bends: baseline recovery, envelope

Top-level modules: training_config, tuning, watch_mirror.
"""

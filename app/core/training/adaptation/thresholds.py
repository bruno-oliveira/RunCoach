"""Shared verdict thresholds: where "on target" ends, on every surface.

The same judgement — is this runner's load really changing, are they running
their sessions fast or slow — used to be re-decided with private constants in
the signal engine, the coach summary, the proactive nudge, the pattern
analyser and the pace recaliber. They drifted (a ±2% hold band here, ±5%
there), so the coach could call a week "increase" that the engine held, or a
nudge could offer a change the engine had just declined. Every surface that
renders one of these verdicts imports the boundary from here instead.

Pure constants; no I/O, importable from any layer.
"""

# Multiplier dead-zone around 1.0 that reads as "hold, stay the course". The
# signal engine snaps anything inside it to exactly 1.0 unless an overreach
# signal fired, so every surface that labels or reacts to a multiplier must
# use the same band or it will describe a change that never happened.
HOLD_DEADBAND = 0.05

# The overreach path bypasses the dead-zone; below this delta an automatic
# (unattended) adjustment is still too small to be worth churning the plan.
AUTO_ADJUST_MIN_DELTA = 0.03

# Session pace deviation, ``(actual - planned) / planned``: faster than
# FAST reads as "fitter than the plan", slower than SLOW as "target too hot".
# The slow side is wider because warm-up/cool-down dilution biases a
# session's average pace slow.
PACE_FAST_DEVIATION = -0.05
PACE_SLOW_DEVIATION = 0.08

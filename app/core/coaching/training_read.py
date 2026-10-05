"""Read a runner's training and name the one thing worth changing.

A runner opens the Coach page with two questions. *Is what I am doing enough
for my goal?* — and, goal or no goal, *what does my recent running say I should
change?* The two pull against each other: a goal almost always wants more, and
recent running quite often says less.

This module is where they are reconciled. Each question produces **findings**
(one per thing a coach would look at), and a single fixed order —
``FOCUS_ORDER`` — picks the one finding the page leads with. The order is the
coaching judgement: what could hurt the runner comes first, then what the goal
is missing, then what would merely make good training better. A runner who is
behind on distance *and* has just jumped their volume is told to hold, not to
catch up.

Two things are deliberately absent. There is no score: "73/100" answers no
question a runner has. And nothing here is scoped to "runs linked to a plan" —
a run is a run, and the goal is judged against everything the runner did in
the weeks the plan covered.

Findings carry a stable ``key`` and the figures behind it, never prose, so the
page owns the wording and can translate it.
"""

import statistics
from dataclasses import dataclass
from typing import Optional, Sequence

from app.core.coaching.intensity_split import (
    MIN_RUNS,
    MOSTLY_EASY,
    TOO_HARD,
    IntensitySplit,
)

GOOD = "good"
WATCH = "watch"
CHANGE = "change"

# -- Page states -------------------------------------------------------------
NO_RUNS = "no_runs"
EARLY_DAYS = "early_days"
READY = "ready"

# -- Goal states -------------------------------------------------------------
GOAL_TOO_EARLY = "too_early"
GOAL_ON_TRACK = "on_track"
GOAL_DRIFTING = "drifting"
GOAL_BEHIND = "behind"

# How many of the most recent complete weeks "recent" means.
RECENT_WEEKS = 4

# Days of nothing after which a runner has stopped, not paused.
_LAYOFF_DAYS = 10
# Below this many runs a week there is room for another (no plan to say so).
_LIGHT_RUNS_PER_WEEK = 2.5

# A week this much bigger than the ones before it is a jump, provided it is
# also a real number of kilometres (10 km after 7 km is not a spike).
_JUMP_RATIO = 1.3
_JUMP_MIN_KM = 5.0
_DROP_RATIO = 0.5

# The longest run barely longer than the typical one means no long run at all.
_SAME_LENGTH_RATIO = 1.25
# One run carrying more than half the week leaves too little around it.
_LONG_SHARE_CEILING = 0.5
_LONG_SHARE_MIN_WEEKLY_KM = 15.0

# Share of what the plan asked for, per goal finding: (fine from, short below).
_SESSIONS_BANDS = (0.85, 0.6)
_VOLUME_BANDS = (0.9, 0.75)
_LONG_RUN_BANDS = (0.9, 0.75)
_VOLUME_OVER_RATIO = 1.2

# How far a goal time can sit ahead of current form and still be closed: about
# half a percent a week of training left, up to a ceiling no block reliably
# beats. A rule of thumb, which is why a miss by less than the margin below is
# only a stretch.
_TIME_GAIN_PER_WEEK = 0.005
_TIME_GAIN_CEILING = 0.08
_TIME_STRETCH_MARGIN = 0.03

# The single judgement this module makes: which finding matters most. First
# match wins. Safety, then the goal, then refinements.
FOCUS_ORDER = (
    "load_jump",
    "too_hard",
    "gone_quiet",
    "sessions_missed",
    "volume_short",
    "long_short",
    "time_far",
    "sessions_slipping",
    "volume_light",
    "long_light",
    "volume_over",
    "time_stretch",
    "patchy",
    "fitness_down",
    "load_drop",
    "all_easy",
    "same_length",
    "long_too_big",
    "light",
)


@dataclass(frozen=True)
class Week:
    """One complete calendar week of logged running."""

    km: float
    runs: int


@dataclass(frozen=True)
class RecentTraining:
    """What the runner has done lately, reduced to what the read weighs."""

    # Complete weeks, oldest first, starting at the runner's first logged week
    # so a blank week is one they skipped rather than one before they began.
    weeks: Sequence[Week]
    # None when they have never logged a run.
    days_since_last_run: Optional[int]
    # Distances of the runs in the last four weeks.
    run_lengths_km: Sequence[float]
    split: Optional[IntensitySplit]
    # "improving" | "stable" | "declining", or None when unknown.
    fitness_trend: Optional[str] = None


@dataclass(frozen=True)
class GoalWindow:
    """What the plan asked for over its last few completed weeks, and what was run.

    The window is short on purpose: a week missed two months ago should not
    still brand a runner as behind.
    """

    weeks: int
    planned_sessions: int
    done_sessions: int
    planned_km: float
    actual_km: float
    planned_long_km: float
    longest_km: float


@dataclass(frozen=True)
class GoalTime:
    """The time the runner is training for, and the one their runs point to."""

    goal_seconds: int
    predicted_seconds: int
    weeks_to_go: int


@dataclass(frozen=True)
class Finding:
    """One thing a coach would look at, and how it stands."""

    area: str
    key: str
    status: str
    figures: tuple[float, ...] = ()


@dataclass(frozen=True)
class TrainingRead:
    """The whole read: both questions answered, and the one change to lead with."""

    state: str
    goal_state: Optional[str]
    goal_findings: tuple[Finding, ...]
    recent_findings: tuple[Finding, ...]
    focus: Optional[Finding]

    @property
    def headline(self) -> str:
        """Key for the page's lead sentence."""
        if self.state != READY and self.goal_state is None:
            return self.state
        if self.goal_state is not None:
            on_track_with_a_note = self.goal_state == GOAL_ON_TRACK and self.focus
            return f"goal_{self.goal_state}" + ("_but" if on_track_with_a_note else "")
        if self.focus is None:
            return "steady"
        return "attention" if self.focus.status == CHANGE else "tune"


def read_training(
    recent: RecentTraining,
    *,
    has_goal: bool,
    goal: Optional[GoalWindow] = None,
    goal_time: Optional[GoalTime] = None,
) -> TrainingRead:
    """Answer both of the runner's questions and pick the one change.

    Args:
        recent: Their recent running.
        has_goal: A plan is in progress. The plan then owns the hard sessions
            and the long run, so the recent read stops suggesting either.
        goal: Planned versus done over the plan's last completed weeks; None
            when there is a goal but no completed week to judge yet.
        goal_time: The goal time against the time their fitness predicts;
            None when the goal has no time or there is no honest prediction.
    """
    state = _state(recent)
    recent_findings = _recent_findings(recent, state, has_goal=has_goal)
    goal_findings = _goal_findings(goal, goal_time)
    return TrainingRead(
        state=state,
        goal_state=_goal_state(goal_findings) if has_goal else None,
        goal_findings=goal_findings,
        recent_findings=recent_findings,
        focus=_focus(recent_findings + goal_findings),
    )


def _state(recent: RecentTraining) -> str:
    if recent.days_since_last_run is None:
        return NO_RUNS
    if len(recent.run_lengths_km) < MIN_RUNS:
        return EARLY_DAYS
    return READY


def _focus(findings: Sequence[Finding]) -> Optional[Finding]:
    by_key = {finding.key: finding for finding in findings}
    return next((by_key[key] for key in FOCUS_ORDER if key in by_key), None)


# -- Recent running ----------------------------------------------------------


def _recent_findings(
    recent: RecentTraining, state: str, *, has_goal: bool
) -> tuple[Finding, ...]:
    if state == NO_RUNS:
        return ()
    if state == EARLY_DAYS:
        # Too few runs to read a pattern, but a layoff is still worth naming.
        quiet = _gone_quiet(recent)
        return (quiet,) if quiet else ()
    candidates = (
        _rhythm(recent, has_goal=has_goal),
        _balance(recent.split, has_goal=has_goal),
        _load(recent.weeks, has_goal=has_goal),
        # With a goal, the plan sets the long run and the goal check judges it.
        None if has_goal else _length(recent),
        _fitness(recent.fitness_trend),
    )
    return tuple(finding for finding in candidates if finding is not None)


def _gone_quiet(recent: RecentTraining) -> Optional[Finding]:
    days = recent.days_since_last_run
    if days is None or days < _LAYOFF_DAYS:
        return None
    return Finding("rhythm", "gone_quiet", CHANGE, (days,))


def _rhythm(recent: RecentTraining, *, has_goal: bool) -> Optional[Finding]:
    quiet = _gone_quiet(recent)
    if quiet is not None:
        return quiet
    weeks = recent.weeks[-RECENT_WEEKS:]
    if len(weeks) < 2:
        return None
    per_week = round(sum(week.runs for week in weeks) / len(weeks), 1)
    if any(week.runs == 0 for week in weeks):
        return Finding("rhythm", "patchy", WATCH, (per_week,))
    # A plan chose its own number of running days; only an unplanned week has
    # room for "one more".
    if not has_goal and per_week < _LIGHT_RUNS_PER_WEEK:
        return Finding("rhythm", "light", WATCH, (per_week,))
    return Finding("rhythm", "steady", GOOD, (per_week,))


def _balance(split: Optional[IntensitySplit], *, has_goal: bool) -> Optional[Finding]:
    if split is None:
        return None
    figures = (round(split.easy_share * 100),)
    if split.verdict == TOO_HARD:
        return Finding("balance", "too_hard", CHANGE, figures)
    if split.verdict == MOSTLY_EASY:
        # All-easy is a gap only for a runner nobody is scheduling quality for.
        if has_goal:
            return Finding("balance", "easy_by_plan", GOOD, figures)
        return Finding("balance", "all_easy", WATCH, figures)
    return Finding("balance", "balanced", GOOD, figures)


def _load(weeks: Sequence[Week], *, has_goal: bool) -> Optional[Finding]:
    if len(weeks) < RECENT_WEEKS:
        return None
    last = weeks[-1].km
    before = [week.km for week in weeks[-RECENT_WEEKS:-1]]
    baseline = sum(before) / len(before)
    if baseline <= 0:
        return None
    figures = (round(last, 1), round(baseline, 1))
    if last >= baseline * _JUMP_RATIO and last - baseline >= _JUMP_MIN_KM:
        return Finding("load", "load_jump", CHANGE, figures)
    # A plan drops volume on purpose (deload, taper); its own check judges that.
    if not has_goal and last <= baseline * _DROP_RATIO:
        return Finding("load", "load_drop", WATCH, figures)
    return Finding("load", "load_steady", GOOD, figures)


def _length(recent: RecentTraining) -> Optional[Finding]:
    lengths = [km for km in recent.run_lengths_km if km > 0]
    if len(lengths) < MIN_RUNS:
        return None
    longest = max(lengths)
    typical = statistics.median(lengths)
    figures = (round(longest, 1), round(typical, 1))
    if longest <= typical * _SAME_LENGTH_RATIO:
        return Finding("length", "same_length", WATCH, figures)
    weeks = recent.weeks[-RECENT_WEEKS:]
    weekly_km = sum(week.km for week in weeks) / len(weeks) if weeks else 0.0
    if (
        weekly_km >= _LONG_SHARE_MIN_WEEKLY_KM
        and longest > weekly_km * _LONG_SHARE_CEILING
    ):
        return Finding("length", "long_too_big", WATCH, figures)
    return Finding("length", "long_ok", GOOD, figures)


def _fitness(trend: Optional[str]) -> Optional[Finding]:
    # A flat trend is not news, so it gets no row.
    if trend == "improving":
        return Finding("fitness", "fitness_up", GOOD)
    if trend == "declining":
        return Finding("fitness", "fitness_down", WATCH)
    return None


# -- Against the goal --------------------------------------------------------


def _goal_findings(
    goal: Optional[GoalWindow], goal_time: Optional[GoalTime]
) -> tuple[Finding, ...]:
    done = (_sessions(goal), _volume(goal), _long_run(goal)) if goal else ()
    candidates = (*done, _race_time(goal_time) if goal_time else None)
    return tuple(finding for finding in candidates if finding is not None)


def _goal_state(findings: Sequence[Finding]) -> str:
    if not findings:
        return GOAL_TOO_EARLY
    statuses = {finding.status for finding in findings}
    if CHANGE in statuses:
        return GOAL_BEHIND
    return GOAL_DRIFTING if WATCH in statuses else GOAL_ON_TRACK


def _banded(share: float, bands: tuple[float, float]) -> str:
    fine_from, short_below = bands
    if share >= fine_from:
        return GOOD
    return WATCH if share >= short_below else CHANGE


def _sessions(goal: GoalWindow) -> Optional[Finding]:
    if goal.planned_sessions <= 0:
        return None
    status = _banded(goal.done_sessions / goal.planned_sessions, _SESSIONS_BANDS)
    key = {
        GOOD: "sessions_ok",
        WATCH: "sessions_slipping",
        CHANGE: "sessions_missed",
    }[status]
    return Finding("sessions", key, status, (goal.done_sessions, goal.planned_sessions))


def _volume(goal: GoalWindow) -> Optional[Finding]:
    if goal.planned_km <= 0:
        return None
    figures = (round(goal.actual_km), round(goal.planned_km))
    share = goal.actual_km / goal.planned_km
    if share > _VOLUME_OVER_RATIO:
        return Finding("volume", "volume_over", WATCH, figures)
    status = _banded(share, _VOLUME_BANDS)
    key = {GOOD: "volume_ok", WATCH: "volume_light", CHANGE: "volume_short"}[status]
    return Finding("volume", key, status, figures)


def _long_run(goal: GoalWindow) -> Optional[Finding]:
    if goal.planned_long_km <= 0:
        return None
    status = _banded(goal.longest_km / goal.planned_long_km, _LONG_RUN_BANDS)
    key = {GOOD: "long_on_plan", WATCH: "long_light", CHANGE: "long_short"}[status]
    return Finding(
        "long_run",
        key,
        status,
        (round(goal.longest_km, 1), round(goal.planned_long_km, 1)),
    )


def _race_time(goal_time: GoalTime) -> Optional[Finding]:
    """Whether the goal time is reachable from where the runner's fitness is."""
    if goal_time.goal_seconds <= 0 or goal_time.predicted_seconds <= 0:
        return None
    figures = (goal_time.predicted_seconds, goal_time.goal_seconds)
    # How much faster than today's prediction the goal asks them to be.
    gap = goal_time.predicted_seconds / goal_time.goal_seconds - 1
    if gap <= 0:
        return Finding("race_time", "time_ahead", GOOD, figures)
    closable = min(_TIME_GAIN_CEILING, goal_time.weeks_to_go * _TIME_GAIN_PER_WEEK)
    if gap <= closable:
        return Finding("race_time", "time_reachable", GOOD, figures)
    if gap <= closable + _TIME_STRETCH_MARGIN:
        return Finding("race_time", "time_stretch", WATCH, figures)
    return Finding("race_time", "time_far", CHANGE, figures)

"""Individual insight generator functions.

Each function takes a RunnerProfile and returns an Insight dataclass instance.
Extracted from insights_service.py for single-responsibility.
"""

from app.contexts.runner.profile.runner_profile import RunnerProfile
from app.contexts.runner.fitness.insights_service import Insight


def acwr_insight(p: RunnerProfile) -> Insight:
    acwr = p.acwr
    if p.acwr_risk == "optimal":
        return Insight(
            category="recovery",
            title="Training load is in the sweet spot",
            body=f"Your ACWR is {acwr:.2f} — right in the 0.8\u20131.3 optimal zone. "
                 "You're balancing stress and recovery well. Keep it up.",
            priority=3,
            icon="\u2705",
            sentiment="positive",
        )
    elif p.acwr_risk == "low":
        return Insight(
            category="recovery",
            title="Training load is low",
            body=f"Your ACWR is {acwr:.2f} (under 0.8). You're either in a recovery "
                 "phase or under-training. If this isn't intentional, gradually increase "
                 "volume over the next 2 weeks.",
            priority=2,
            icon="\u26A0\uFE0F",
            sentiment="warning",
        )
    elif p.acwr_risk == "high":
        return Insight(
            category="recovery",
            title="Training load is elevated",
            body=f"Your ACWR is {acwr:.2f} — above the 1.3 threshold. "
                 "Consider an easy week soon to reduce injury risk. "
                 "Replace one quality session with an easy run.",
            priority=1,
            icon="\U0001F6A8",
            sentiment="negative",
        )
    else:  # very_high
        return Insight(
            category="recovery",
            title="Training load spike — high injury risk",
            body=f"Your ACWR is {acwr:.2f} — well above 1.5. This is a danger zone. "
                 "Take 2\u20133 easy days immediately. Reduce volume by 30\u201340% this week.",
            priority=1,
            icon="\U0001F6D1",
            sentiment="negative",
        )


def volume_insight(p: RunnerProfile) -> Insight:
    if p.peak_weekly_km > 0 and p.avg_weekly_km > 0:
        ratio = p.peak_weekly_km / p.avg_weekly_km
        if ratio > 1.4:
            return Insight(
                category="volume",
                title="Large volume swings detected",
                body=f"Your peak week ({p.peak_weekly_km} km) is {ratio:.1f}x your "
                     f"average ({p.avg_weekly_km} km). Consistency matters more than "
                     "big weeks. Aim for <30% variation week to week.",
                priority=2,
                icon="\U0001F4C8",
                sentiment="warning",
            )
    return Insight(
        category="volume",
        title=f"Averaging {p.avg_weekly_km} km/week",
        body=f"Over the last {p.weeks_of_data} weeks you've averaged "
             f"{p.avg_weekly_km} km/week across {p.runs_per_week} runs/week. "
             f"Peak week: {p.peak_weekly_km} km.",
        priority=4,
        icon="\U0001F3C3",
        sentiment="neutral",
    )


def polarization_insight(p: RunnerProfile) -> Insight:
    if p.easy_pct >= 75:
        return Insight(
            category="intensity",
            title="Great polarization — mostly easy running",
            body=f"{p.easy_pct:.0f}% of your runs are at easy effort. "
                 "This follows the 80/20 principle elite runners use. "
                 "Your hard sessions can be truly hard because you recover between them.",
            priority=4,
            icon="\U0001F31F",
            sentiment="positive",
        )
    elif p.easy_pct >= 60:
        return Insight(
            category="intensity",
            title="Moderate intensity balance",
            body=f"Only {p.easy_pct:.0f}% of your runs are easy — ideally aim for 80%. "
                 f"You have {p.hard_pct:.0f}% hard sessions. Try converting 1\u20132 moderate "
                 "runs per week to truly easy pace to improve recovery.",
            priority=2,
            icon="\u26A0\uFE0F",
            sentiment="warning",
        )
    else:
        return Insight(
            category="intensity",
            title="Too much intensity",
            body=f"Only {p.easy_pct:.0f}% of your runs are easy — the recommended "
                 "target is 80%. Running too hard too often leads to stagnation and "
                 "injury. Slow down your easy runs by 30\u201360 sec/km.",
            priority=1,
            icon="\U0001F6A8",
            sentiment="negative",
        )


def fitness_insight(p: RunnerProfile) -> Insight:
    vdot = p.current_vdot
    if p.vdot_trend == "improving":
        return Insight(
            category="fitness",
            title=f"Fitness is improving (VDOT {vdot})",
            body="Your VDOT has trended upward recently. Your current training "
                 "is producing adaptations — stay the course.",
            priority=3,
            icon="\U0001F4AA",
            sentiment="positive",
        )
    elif p.vdot_trend == "declining":
        return Insight(
            category="fitness",
            title=f"Fitness dip detected (VDOT {vdot})",
            body="Your VDOT has dipped recently. This could be fatigue, illness, "
                 "or heat. If you've been training hard, a recovery week often "
                 "reverses the trend.",
            priority=2,
            icon="\U0001F4C9",
            sentiment="warning",
        )
    return Insight(
        category="fitness",
        title=f"Fitness is stable (VDOT {vdot})",
        body="Your VDOT has held steady. To push it higher, add one focused "
             "quality session per week (tempo or intervals) without increasing "
             "total volume.",
        priority=4,
        icon="\u2696\uFE0F",
        sentiment="neutral",
    )


def consistency_insight(p: RunnerProfile) -> Insight:
    rpw = p.runs_per_week
    if rpw >= 4:
        return Insight(
            category="consistency",
            title=f"Strong consistency — {rpw} runs/week",
            body="Running 4+ times per week gives your body frequent adaptation signals. "
                 "This consistency is more valuable than any single workout.",
            priority=4,
            icon="\U0001F4C5",
            sentiment="positive",
        )
    elif rpw >= 3:
        return Insight(
            category="consistency",
            title=f"Solid consistency — {rpw} runs/week",
            body="Three runs per week is a great foundation. When you're ready "
                 "to progress, adding a 4th easy run gives you more volume without "
                 "more intensity.",
            priority=4,
            icon="\U0001F4C5",
            sentiment="neutral",
        )
    else:
        return Insight(
            category="consistency",
            title=f"Low frequency — {rpw} runs/week",
            body="Fewer than 3 runs/week limits adaptation. Try to add one short, "
                 "easy run (20\u201330 min) on a non-running day to build consistency.",
            priority=2,
            icon="\u26A0\uFE0F",
            sentiment="warning",
        )


def efficiency_insight(p: RunnerProfile) -> Insight:
    trend = p.efficiency_trend_pct
    if trend is not None and trend > 3:
        return Insight(
            category="efficiency",
            title="Aerobic efficiency is improving",
            body=f"Your speed-to-heart-rate ratio improved {trend:.1f}% recently. "
                 "You're getting faster at the same effort — a sign of real fitness gains.",
            priority=3,
            icon="\u2764\uFE0F",
            sentiment="positive",
        )
    elif trend is not None and trend < -3:
        return Insight(
            category="efficiency",
            title="Aerobic efficiency has dipped",
            body=f"Your speed-to-heart-rate ratio dropped {abs(trend):.1f}%. "
                 "This may indicate fatigue, heat, or overtraining. "
                 "Consider more easy-paced runs this week.",
            priority=2,
            icon="\U0001F4C9",
            sentiment="warning",
        )
    return Insight(
        category="efficiency",
        title="Aerobic efficiency is steady",
        body="Your speed-to-heart-rate ratio is stable. Consistent easy running "
             "is the best way to push this metric higher over time.",
        priority=5,
        icon="\u2764\uFE0F",
        sentiment="neutral",
    )


def long_run_insight(p: RunnerProfile) -> Insight:
    ratio = p.longest_run_km / p.avg_weekly_km if p.avg_weekly_km > 0 else 0
    if ratio > 0.5:
        return Insight(
            category="volume",
            title="Long run is a big chunk of weekly volume",
            body=f"Your longest run ({p.longest_run_km} km) is {ratio:.0%} of your "
                 f"weekly average ({p.avg_weekly_km} km). Ideally the long run should "
                 "be 25\u201335% of weekly volume. Add more mid-week volume to balance.",
            priority=3,
            icon="\U0001F4CF",
            sentiment="warning",
        )
    return Insight(
        category="volume",
        title="Good long-run balance",
        body=f"Your longest run ({p.longest_run_km} km) is {ratio:.0%} of weekly "
             f"volume — well balanced.",
        priority=5,
        icon="\U0001F44D",
        sentiment="positive",
    )


def variety_insight(p: RunnerProfile) -> Insight:
    counts = p.workout_type_counts or {}
    total = sum(counts.values())
    if total == 0:
        return Insight(
            category="intensity",
            title="No workout type data",
            body="We couldn't determine your workout types. "
                 "Tag your runs (easy, tempo, interval) for better insights.",
            priority=5,
            icon="\U0001F3F7\uFE0F",
            sentiment="neutral",
        )

    quality_types = {"tempo", "interval", "hill", "race"}
    quality_count = sum(counts.get(t, 0) for t in quality_types)
    quality_pct = quality_count / total * 100 if total else 0

    if quality_pct < 5 and total >= 6:
        return Insight(
            category="intensity",
            title="Missing quality sessions",
            body="You've done almost no tempo, interval, or hill workouts recently. "
                 "Adding 1\u20132 quality sessions per week (while keeping total volume "
                 "the same) can unlock significant fitness gains.",
            priority=2,
            icon="\u26A1",
            sentiment="warning",
        )
    elif quality_pct > 30:
        return Insight(
            category="intensity",
            title="Heavy on quality sessions",
            body=f"{quality_pct:.0f}% of your runs are quality sessions. "
                 "Limit hard sessions to 2\u20133 per week max to ensure recovery.",
            priority=2,
            icon="\u26A0\uFE0F",
            sentiment="warning",
        )
    return Insight(
        category="intensity",
        title="Good workout mix",
        body=f"You're doing {quality_pct:.0f}% quality sessions — a healthy balance "
             "of easy and hard work.",
        priority=5,
        icon="\u2705",
        sentiment="positive",
    )


def recovery_insight(p: RunnerProfile) -> Insight:
    rest = p.rest_days_per_week
    if rest >= 3:
        return Insight(
            category="recovery",
            title=f"{rest:.0f} rest days per week",
            body="You're giving your body plenty of recovery time. "
                 "Rest is when adaptation happens — this is smart training.",
            priority=5,
            icon="\U0001F6CC",
            sentiment="positive",
        )
    elif rest >= 2:
        return Insight(
            category="recovery",
            title=f"{rest:.0f} rest days per week",
            body="Two rest days is a reasonable balance for most runners. "
                 "Make sure at least one is a full rest day with no cross-training.",
            priority=4,
            icon="\U0001F6CC",
            sentiment="neutral",
        )
    else:
        return Insight(
            category="recovery",
            title="Very few rest days",
            body=f"You're averaging only {rest:.1f} rest days per week. "
                 "Running 6\u20137 days/week increases injury risk significantly. "
                 "Consider adding at least one complete rest day.",
            priority=1,
            icon="\U0001F6D1",
            sentiment="negative",
        )


def volume_trend_insight(p: RunnerProfile) -> Insight:
    if p.volume_trend == "increasing":
        return Insight(
            category="volume",
            title="Volume is trending up",
            body=f"Your weekly mileage has been increasing over the past "
                 f"{p.weeks_of_data} weeks. Make sure you're following the 10% rule "
                 "— don't increase total volume by more than 10% per week.",
            priority=3,
            icon="\U0001F4C8",
            sentiment="neutral",
        )
    return Insight(
        category="volume",
        title="Volume is trending down",
        body=f"Your weekly mileage has decreased over the past {p.weeks_of_data} weeks. "
             "If this is a planned taper or recovery block, great. Otherwise, "
             "try to stabilize your training before adding intensity.",
        priority=3,
        icon="\U0001F4C9",
        sentiment="warning",
    )


def run_length_insight(p: RunnerProfile) -> Insight:
    avg = p.avg_run_km
    if avg < 5:
        return Insight(
            category="volume",
            title=f"Short average run ({avg} km)",
            body="Most of your runs are under 5 km. While short runs have value, "
                 "extending 1\u20132 runs per week to 6\u20138 km will build your aerobic base "
                 "more efficiently.",
            priority=3,
            icon="\U0001F4CF",
            sentiment="warning",
        )
    elif avg > 12:
        return Insight(
            category="volume",
            title=f"Long average run ({avg} km)",
            body="Your average run is quite long. Make sure your easy days are truly easy "
                 "and short. Varying run lengths helps prevent overuse injuries.",
            priority=3,
            icon="\U0001F4CF",
            sentiment="neutral",
        )
    return Insight(
        category="volume",
        title=f"Healthy average run length ({avg} km)",
        body="Your typical run distance is in a good range for building "
             "aerobic fitness without excessive fatigue.",
        priority=5,
        icon="\U0001F44D",
        sentiment="positive",
    )


def race_readiness_insight(p: RunnerProfile) -> Insight:
    vdot = p.current_vdot
    if vdot >= 55:
        level = "advanced"
        desc = "competitive"
        distances = "sub-19 5K, sub-40 10K, sub-1:28 half marathon"
    elif vdot >= 45:
        level = "intermediate"
        desc = "solid recreational"
        distances = "~21 min 5K, ~44 min 10K, ~1:38 half marathon"
    elif vdot >= 35:
        level = "developing"
        desc = "building"
        distances = "~27 min 5K, ~56 min 10K, ~2:05 half marathon"
    else:
        level = "beginner"
        desc = "early-stage"
        distances = "focus on building a consistent base before targeting times"

    body = (
        f"Your VDOT of {vdot} puts you at a {desc} fitness level. "
        f"Predicted range: {distances}. "
    )
    if p.vdot_trend == "improving":
        body += "Your fitness is trending up — consider entering a race to test yourself."
    elif p.vdot_trend == "declining":
        body += "Your fitness has dipped recently — focus on consistency before racing."
    else:
        body += "Maintain your current training to hold this level, or add a quality session to push higher."

    return Insight(
        category="fitness",
        title=f"Race fitness level: {level}",
        body=body,
        priority=4,
        icon="\U0001F3C6",
        sentiment="positive" if p.vdot_trend == "improving" else "neutral",
    )

"""Self-contained helpers for plan customization (intensity, distance, swap, AI)."""


def adjust_intensity(
    plan_data: list[dict], week_number: int, intensity_level: str
) -> list[dict]:
    """Adjust workout intensity for a specific week."""
    for week in plan_data:
        if week["week"] == week_number:
            for workout in week.get("daily_workouts", []):
                if workout["type"] != "rest":
                    workout["intensity"] = intensity_level
                    notes = workout.get("notes") or ""
                    if intensity_level == "low":
                        workout["notes"] = (
                            notes
                            .replace("threshold", "easy")
                            .replace("tempo", "easy")
                        )
                    elif intensity_level == "high":
                        workout["notes"] = (
                            notes
                            .replace("easy", "tempo")
                            .replace("recovery", "moderate")
                        )
    return plan_data


def swap_workout(
    plan_data: list[dict], week_number: int, swap_info: str
) -> list[dict]:
    """Swap workout types for a specific week."""
    try:
        day, new_type = swap_info.split(",")
        day = int(day)

        for week in plan_data:
            if week["week"] == week_number:
                for workout in week.get("daily_workouts", []):
                    if workout["day"] == day:
                        old_type = workout["type"]
                        workout["type"] = new_type

                        if new_type == "rest":
                            workout["distance"] = 0
                            workout["notes"] = "Rest day for recovery"
                        elif old_type == "rest" and new_type != "rest":
                            workout["distance"] = 5.0
                            workout["notes"] = f"Easy {new_type} run - focus on form"

                        workout["intensity"] = (
                            "low" if new_type in ["rest", "easy"] else "medium"
                        )
    except (ValueError, TypeError):
        pass

    return plan_data


def swap_days(
    plan_data: list[dict], week_number: int, source_day: int, target_day: int
) -> list[dict]:
    """Swap two workouts within a week by exchanging their day assignments."""
    for week in plan_data:
        if week["week"] == week_number:
            workouts = week.get("daily_workouts", [])
            src = next((w for w in workouts if w.get("day") == source_day), None)
            tgt = next((w for w in workouts if w.get("day") == target_day), None)
            if src and tgt:
                src["day"], tgt["day"] = tgt["day"], src["day"]
                week["daily_workouts"] = sorted(workouts, key=lambda w: w.get("day", 0))
            break
    return plan_data


def adjust_distance(
    plan_data: list[dict], week_number: int, distance_change: float
) -> list[dict]:
    """Adjust distances for all workouts in a week."""
    for week in plan_data:
        if week["week"] == week_number:
            current_total = sum(
                w.get("distance", 0) for w in week.get("daily_workouts", [])
            )

            if current_total > 0:
                ratio = max(0.0, (current_total + distance_change) / current_total)

                for workout in week.get("daily_workouts", []):
                    if workout["distance"] > 0:
                        workout["distance"] = round(workout["distance"] * ratio, 1)

                week["total_km"] = round(
                    sum(w.get("distance", 0) for w in week.get("daily_workouts", [])), 1
                )

    return plan_data


def apply_ai_suggestions(
    plan_data: list[dict], week_number: int, preference: str
) -> list[dict]:
    """Apply AI-powered suggestions based on user preferences."""
    for week in plan_data:
        if week["week"] == week_number:
            if preference == "more_rest":
                for workout in week.get("daily_workouts", []):
                    if workout["type"] == "easy":
                        removed_distance = workout.get("distance", 0)
                        workout["type"] = "rest"
                        workout["distance"] = 0
                        workout["notes"] = "Additional rest day for recovery"
                        week["total_km"] = round(
                            week["total_km"] - removed_distance, 1
                        )
                        break

            elif preference == "more_speed":
                for workout in week.get("daily_workouts", []):
                    if workout["type"] == "easy":
                        workout["type"] = "interval"
                        workout["intensity"] = "high"
                        workout["notes"] = (
                            "Speed work: 6x400m at 5K pace with 400m recovery"
                        )
                        break

            elif preference == "more_endurance":
                for workout in week.get("daily_workouts", []):
                    if workout["type"] == "long":
                        workout["distance"] = round(workout["distance"] * 1.2, 1)
                        workout["notes"] = (
                            f'Extended long run: {workout["distance"]}km at '
                            "conversational pace"
                        )
                        break

            # Recompute total_km from actual workout distances to avoid drift
            week["total_km"] = round(
                sum(w.get("distance", 0) for w in week.get("daily_workouts", [])), 1
            )

    return plan_data

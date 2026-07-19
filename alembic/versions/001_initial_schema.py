"""Initial migration - capture current schema state.

This migration consolidates all previously ad-hoc ALTER TABLE statements
that were run in main.py into a proper Alembic migration.
"""

import sqlalchemy as sa

from alembic import op

revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("google_id", sa.String(), unique=True, nullable=True),
        sa.Column("email", sa.String(), unique=True, nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("picture", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("last_activity", sa.DateTime(), nullable=True),
        sa.Column("plans_generated", sa.Integer(), default=0),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("strava_athlete_id", sa.String(), unique=True, nullable=True),
        sa.Column("strava_access_token", sa.String(), nullable=True),
        sa.Column("strava_refresh_token", sa.String(), nullable=True),
        sa.Column("strava_token_expires_at", sa.Integer(), nullable=True),
        sa.Column("strava_last_synced_at", sa.Integer(), nullable=True),
    )
    op.create_index("ix_users_google_id", "users", ["google_id"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_strava_athlete_id", "users", ["strava_athlete_id"])

    op.create_table(
        "training_plans",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("current_weekly_km", sa.Float(), nullable=True),
        sa.Column("target_distance", sa.String(), nullable=True),
        sa.Column("weeks_duration", sa.Integer(), nullable=True),
        sa.Column("max_runs_per_week", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("plan_data", sa.Text(), nullable=True),
        sa.Column("nutrition_plan_data", sa.Text(), nullable=True),
        sa.Column("plan_type", sa.String(), nullable=True),
        sa.Column("current_pace", sa.Float(), nullable=True),
        sa.Column("goal_pace", sa.Float(), nullable=True),
        sa.Column("current_time", sa.String(), nullable=True),
        sa.Column("goal_time", sa.String(), nullable=True),
        sa.Column("max_heart_rate", sa.Integer(), nullable=True),
        sa.Column("start_date", sa.DateTime(), nullable=True),
        sa.Column("adjustment_multiplier", sa.Float(), nullable=True),
        sa.Column("body_weight_kg", sa.Float(), nullable=True),
        sa.Column("recent_race_distance_km", sa.Float(), nullable=True),
        sa.Column("recent_race_time_seconds", sa.Integer(), nullable=True),
        sa.Column("vdot", sa.Float(), nullable=True),
        sa.Column("hr_zones_data", sa.Text(), nullable=True),
        sa.Column("nutrition_phases_data", sa.Text(), nullable=True),
        sa.Column("race_protocol_data", sa.Text(), nullable=True),
        sa.Column("plan_data_version", sa.Integer(), nullable=True),
        sa.Column("adaptation_alert", sa.Text(), nullable=True),
        sa.Column("last_adjusted_at", sa.DateTime(), nullable=True),
        sa.Column("last_recalibrated_at", sa.DateTime(), nullable=True),
        sa.Column("share_token", sa.String(), unique=True, nullable=True),
    )
    op.create_index("idx_training_plan_user_id", "training_plans", ["user_id"])
    op.create_index("idx_training_plan_created_at", "training_plans", ["created_at"])
    op.create_index(
        "idx_training_plan_share_token", "training_plans", ["share_token"], unique=True
    )

    op.create_table(
        "weekly_plans",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "training_plan_id",
            sa.String(),
            sa.ForeignKey("training_plans.id"),
            nullable=False,
        ),
        sa.Column("week_number", sa.Integer(), nullable=True),
        sa.Column("total_km", sa.Float(), nullable=True),
        sa.Column("workout_types", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_weekly_plan_training_plan_id", "weekly_plans", ["training_plan_id"]
    )

    op.create_table(
        "daily_workouts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "weekly_plan_id",
            sa.String(),
            sa.ForeignKey("weekly_plans.id"),
            nullable=False,
        ),
        sa.Column("day_of_week", sa.Integer(), nullable=True),
        sa.Column("workout_type", sa.String(), nullable=True),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column("intensity", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("coaching_rationale", sa.Text(), nullable=True),
        sa.Column("baseline_distance_km", sa.Float(), nullable=True),
        sa.Column("hr_zone_target", sa.Integer(), nullable=True),
        sa.Column("key_workout_id", sa.String(), nullable=True),
    )
    op.create_index(
        "idx_daily_workout_weekly_plan_id", "daily_workouts", ["weekly_plan_id"]
    )

    op.create_table(
        "plan_customizations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "training_plan_id",
            sa.String(),
            sa.ForeignKey("training_plans.id"),
            nullable=False,
        ),
        sa.Column("week_number", sa.Integer(), nullable=False),
        sa.Column("adjustment_type", sa.String(), nullable=False),
        sa.Column("adjustment_value", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_plan_customizations_training_plan_id",
        "plan_customizations",
        ["training_plan_id"],
    )

    op.create_table(
        "run_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "training_plan_id",
            sa.String(),
            sa.ForeignKey("training_plans.id"),
            nullable=True,
        ),
        sa.Column(
            "daily_workout_id",
            sa.String(),
            sa.ForeignKey("daily_workouts.id"),
            nullable=True,
        ),
        sa.Column("date", sa.DateTime(), nullable=True),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column("duration_minutes", sa.Float(), nullable=True),
        sa.Column("avg_pace_min_km", sa.Float(), nullable=True),
        sa.Column("avg_heart_rate", sa.Integer(), nullable=True),
        sa.Column("max_heart_rate", sa.Integer(), nullable=True),
        sa.Column("avg_cadence", sa.Integer(), nullable=True),
        sa.Column("elevation_gain_m", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("workout_type", sa.String(), nullable=True),
        sa.Column("perceived_effort", sa.Integer(), nullable=True),
        sa.Column("strava_activity_id", sa.String(), unique=True, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("effort_quality_score", sa.Float(), nullable=True),
        sa.Column("quality_label", sa.String(20), nullable=True),
        sa.Column("planned_pace_min_km", sa.Float(), nullable=True),
        sa.Column("vdot", sa.Float(), nullable=True),
        sa.Column("predicted_time_seconds", sa.Float(), nullable=True),
    )
    op.create_index("idx_run_log_user_id", "run_logs", ["user_id"])
    op.create_index("idx_run_log_date", "run_logs", ["date"])
    op.create_index("idx_run_log_user_date", "run_logs", ["user_id", "date"])
    op.create_index("idx_run_log_training_plan", "run_logs", ["training_plan_id"])
    op.create_index(
        "ix_run_logs_strava_activity_id", "run_logs", ["strava_activity_id"]
    )

    op.create_table(
        "run_feedback",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "run_log_id", sa.String(), sa.ForeignKey("run_logs.id"), nullable=False
        ),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("pace_feedback", sa.Text(), nullable=True),
        sa.Column("hr_zone_feedback", sa.Text(), nullable=True),
        sa.Column("effort_feedback", sa.Text(), nullable=True),
        sa.Column("volume_feedback", sa.Text(), nullable=True),
        sa.Column("pattern_feedback", sa.Text(), nullable=True),
        sa.Column("overall_sentiment", sa.String(10), nullable=False),
        sa.Column(
            "planned_workout_id",
            sa.String(),
            sa.ForeignKey("daily_workouts.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_run_feedback_run_log_id", "run_feedback", ["run_log_id"])
    op.create_index("idx_run_feedback_user_id", "run_feedback", ["user_id"])

    op.create_table(
        "favorite_recipes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recipe_name", sa.String(), nullable=False),
        sa.Column("meal_type", sa.String(), nullable=False),
        sa.Column("recipe_data", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")
        ),
    )

    op.create_table(
        "triathlon_plans",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("distance", sa.String(), nullable=True),
        sa.Column("weeks_duration", sa.Integer(), nullable=True),
        sa.Column("plan_data", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_triathlon_plans_user_id", "triathlon_plans", ["user_id"])

    op.create_table(
        "readiness_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("sleep", sa.Integer(), nullable=False),
        sa.Column("soreness", sa.Integer(), nullable=False),
        sa.Column("energy", sa.Integer(), nullable=False),
        sa.Column("stress", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "idx_readiness_user_date",
        "readiness_logs",
        ["user_id", "log_date"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("readiness_logs")
    op.drop_table("triathlon_plans")
    op.drop_table("favorite_recipes")
    op.drop_table("run_feedback")
    op.drop_table("run_logs")
    op.drop_table("plan_customizations")
    op.drop_table("daily_workouts")
    op.drop_table("weekly_plans")
    op.drop_table("training_plans")
    op.drop_table("users")

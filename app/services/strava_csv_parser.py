"""Service for parsing Strava activities.csv files."""

import csv
import io
import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class StravaCSVParser:
    """Parser for Strava activities.csv export files."""

    # Minimal required columns for memory-constrained environment
    REQUIRED_COLUMNS = {
        "Activity Date",
        "Activity Type",
        "Distance",
    }

    # Only essential optional columns: heart rate and moving time for performance analytics
    OPTIONAL_COLUMNS = {
        "Average Heart Rate",
        "Moving Time",
    }

    COLUMN_ALIASES = {
        "Activity Date": ["Activity Date", "Date", "date", "activity_date"],
        "Activity Type": ["Activity Type", "Type", "type", "activity_type"],
        "Distance": ["Distance", "distance", "dist"],
        "Average Heart Rate": ["Average Heart Rate", "Avg Heart Rate", "average heart rate", "Avg HR", "avg_hr"],
        "Moving Time": ["Moving Time", "moving_time", "Time", "Duration"],
    }

    @staticmethod
    def parse_csv(csv_content: str) -> Dict[str, Any]:
        """
        Parse Strava activities.csv content.

        Args:
            csv_content: Raw CSV content as string

        Returns:
            Dictionary containing parsed activities and summary data
        """
        csv_reader = csv.DictReader(io.StringIO(csv_content))
        all_columns = csv_reader.fieldnames or []

        logger.info(f"Parsing CSV with columns: {all_columns}")

        columns_lower = {col.lower(): col for col in all_columns}

        column_mapping = {}
        for required_col in StravaCSVParser.REQUIRED_COLUMNS:
            aliases = StravaCSVParser.COLUMN_ALIASES.get(required_col, [required_col])
            for alias in aliases:
                alias_lower = alias.lower()
                if alias_lower in columns_lower:
                    column_mapping[required_col] = columns_lower[alias_lower]
                    break

        missing_required = [
            col for col in StravaCSVParser.REQUIRED_COLUMNS
            if col not in column_mapping
        ]

        if missing_required:
            raise ValueError(
                f"CSV is missing required columns: {missing_required}. "
                f"Found columns: {all_columns}"
            )

        # Map all optional columns as well
        for optional_col in StravaCSVParser.OPTIONAL_COLUMNS:
            aliases = StravaCSVParser.COLUMN_ALIASES.get(optional_col, [optional_col])
            for alias in aliases:
                alias_lower = alias.lower()
                if alias_lower in columns_lower:
                    column_mapping[optional_col] = columns_lower[alias_lower]
                    break

        activities = []
        for row in csv_reader:
            try:
                mapped_row = {col: row.get(col_map) for col, col_map in column_mapping.items()}
                activity = StravaCSVParser._parse_activity(mapped_row)
                activities.append(activity)
            except Exception as e:
                logger.warning(f"Skipping invalid activity row: {e}")
                continue

        summary = StravaCSVParser._calculate_summary(activities)

        return {
            "activities": activities,
            "summary": summary,
            "total_activities": len(activities),
        }

    @staticmethod
    def _parse_activity(row: Dict[str, str]) -> Dict[str, Any]:
        """Parse a single activity row from CSV - minimal data for memory efficiency."""

        date_str = (row.get("Activity Date") or "").strip()
        activity_type = (row.get("Activity Type") or "").strip()
        distance_str = (row.get("Distance") or "").strip()

        date = StravaCSVParser._parse_date(date_str)
        
        distance_km = 0
        if distance_str:
            try:
                # Strava exports distance in meters, convert to km
                distance_meters = float(distance_str)
                distance_km = distance_meters / 1000.0
            except ValueError:
                pass

        avg_heart_rate = None
        hr_key = "Average Heart Rate"
        if row.get(hr_key):
            try:
                hr_value = float(row.get(hr_key, "0").replace(",", ""))
                if hr_value > 0:
                    avg_heart_rate = int(hr_value)
            except ValueError:
                pass

        moving_time_seconds = None
        time_key = "Moving Time"
        if row.get(time_key):
            try:
                moving_time_seconds = int(float(row.get(time_key, "0")))
            except ValueError:
                pass

        # Calculate pace (min/km) if we have both distance and time
        pace_min_km = None
        if distance_km and distance_km > 0 and moving_time_seconds and moving_time_seconds > 0:
            pace_min_km = moving_time_seconds / 60.0 / distance_km

        return {
            "id": str(uuid.uuid4()),
            "date": date.isoformat() if date else None,
            "activity_type": activity_type,
            "distance_km": distance_km,
            "avg_heart_rate": avg_heart_rate,
            "moving_time_seconds": moving_time_seconds,
            "pace_min_km": pace_min_km,
        }

    @staticmethod
    def _parse_date(date_str: str) -> datetime:
        """Parse Strava date format - supports ISO format with T or space separator."""
        if not date_str:
            return None

        date_str_clean = date_str.strip()

        # Try ISO format with 'T' or space (e.g., "2024-01-15T10:30:00" or "2024-01-15 10:30:00")
        try:
            # Replace space with T for ISO parsing
            if ' ' in date_str_clean and 'T' not in date_str_clean:
                date_str_clean = date_str_clean.replace(' ', 'T')
            if date_str_clean.endswith('Z'):
                date_str_clean = date_str_clean[:-1]
            return datetime.fromisoformat(date_str_clean)
        except (ValueError, AttributeError):
            pass

        # Try simple date format (e.g., "2024-01-01")
        try:
            parts = date_str_clean.split('-')
            if len(parts) == 3 and len(parts[0]) == 4:
                year, month, day = map(int, parts)
                return datetime(year, month, day)
        except (ValueError, AttributeError):
            pass

        # Try Strava's human-readable format: "Oct 20, 2024, 5:30:00 PM"
        month_map = {
            "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
            "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
        }

        try:
            parts = date_str.split(", ")
            date_part = parts[0].split(" ")
            month = month_map.get(date_part[0], 1)
            day = int(date_part[1])
            year = int(parts[1])

            time_part = parts[2].split(" ")
            time_parts = time_part[0].split(":")
            am_pm = time_part[1].upper()
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            second = int(time_parts[2])

            if am_pm == "PM" and hour != 12:
                hour += 12
            elif am_pm == "AM" and hour == 12:
                hour = 0

            return datetime(year, month, day, hour, minute, second)
        except Exception as e:
            logger.warning(f"Failed to parse date '{date_str}': {e}")
            return None

    @staticmethod
    def _parse_time(time_str: str) -> int:
        """Parse time duration format (e.g., '1:30:45' or '45:00')."""
        if not time_str:
            return 0
        try:
            parts = time_str.split(":")
            total_seconds = 0
            if len(parts) == 3:
                hours, minutes, seconds = map(int, parts)
                total_seconds = hours * 3600 + minutes * 60 + seconds
            elif len(parts) == 2:
                minutes, seconds = map(int, parts)
                total_seconds = minutes * 60 + seconds
            else:
                total_seconds = int(parts[0])
            return total_seconds
        except Exception:
            return 0

    @staticmethod
    def _calculate_summary(activities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate summary statistics from parsed activities - minimal memory footprint."""
        if not activities:
            return {}

        run_activities = [a for a in activities if a.get("activity_type") == "Run"]

        total_distance = sum(a.get("distance_km", 0) for a in run_activities)

        dates = [a.get("date") for a in run_activities if a.get("date")]
        date_span_days = 0
        if dates:
            from datetime import datetime
            parsed_dates = [datetime.fromisoformat(d) for d in dates]
            date_span_days = (max(parsed_dates) - min(parsed_dates)).days

        avg_heart_rates = [a.get("avg_heart_rate") for a in run_activities if a.get("avg_heart_rate")]
        avg_heart_rate = sum(avg_heart_rates) / len(avg_heart_rates) if avg_heart_rates else 0

        return {
            "total_distance_km": round(total_distance, 2),
            "total_runs": len(run_activities),
            "date_span_days": date_span_days,
            "avg_heart_rate": round(avg_heart_rate, 1) if avg_heart_rate else None,
        }
"""Local-only FIT file validation using Garmin's FitCSVTool.jar.

This tool is intended for local development use only and is NOT used
on the production server. It validates that generated FIT files are
correctly structured according to the Garmin FIT protocol.

Usage:
    python -m app.services.fit_validation_local
    python -m app.services.fit_validation_local --generate-test
"""

import argparse
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

FITCSV_TOOL = Path(__file__).parent.parent.parent / "tools" / "fit-sdk" / "FitCSVTool.jar"


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]
    csv_output: str | None = None


def validate_fit_bytes(fit_bytes: bytes) -> ValidationResult:
    """Validate FIT file bytes using FitCSVTool.jar.

    Returns ValidationResult with pass/fail status and any issues found.
    """
    if not FITCSV_TOOL.exists():
        return ValidationResult(
            valid=False,
            errors=[f"FitCSVTool.jar not found at {FITCSV_TOOL}"],
            warnings=[],
        )

    with tempfile.NamedTemporaryFile(suffix=".fit", delete=False) as tmp:
        tmp.write(fit_bytes)
        tmp_fit = tmp.name

    csv_out = tmp_fit.replace(".fit", ".csv")

    try:
        result = subprocess.run(
            ["java", "-jar", str(FITCSV_TOOL), "-i", "-t", "-b", tmp_fit, csv_out],
            capture_output=True,
            text=True,
            timeout=30,
        )

        stdout = result.stdout
        csv_content = None
        if os.path.exists(csv_out):
            with open(csv_out) as f:
                csv_content = f.read()

        errors = []
        warnings = []

        for line in stdout.splitlines():
            if line.startswith("Error:"):
                errors.append(line)
            elif line.startswith("Warning:"):
                warnings.append(line)

        is_valid = result.returncode == 0 and len(errors) == 0

        return ValidationResult(
            valid=is_valid,
            errors=errors,
            warnings=warnings,
            csv_output=csv_content,
        )
    finally:
        if os.path.exists(tmp_fit):
            os.unlink(tmp_fit)
        if os.path.exists(csv_out):
            os.unlink(csv_out)


def generate_test_fit() -> bytes:
    """Generate a sample FIT workout file for testing."""
    from app.infrastructure.integrations.fit_service import FITService

    segments = [
        {"start_km": 0, "end_km": 1, "target_pace_min_km": 5.0, "grade_pct": 0.0},
        {"start_km": 1, "end_km": 2, "target_pace_min_km": 5.0, "grade_pct": 0.0},
        {"start_km": 2, "end_km": 3, "target_pace_min_km": 4.9, "grade_pct": 0.5},
        {"start_km": 3, "end_km": 4, "target_pace_min_km": 4.8, "grade_pct": -0.5},
        {"start_km": 4, "end_km": 5, "target_pace_min_km": 4.7, "grade_pct": 0.0},
    ]

    return FITService.generate_race_workout(
        segments=segments,
        target_time_seconds=1470,
        target_time_str="24:30",
        race_name="5K Test Plan",
    )


def main():
    parser = argparse.ArgumentParser(description="Local FIT file validation tool")
    parser.add_argument("--generate-test", action="store_true", help="Generate a test FIT file and validate it")
    parser.add_argument("--file", type=str, help="Validate an existing .fit file")
    args = parser.parse_args()

    if args.generate_test:
        print("Generating test FIT file...")
        fit_bytes = generate_test_fit()
        print(f"Generated {len(fit_bytes)} bytes")

        output_path = Path(__file__).parent.parent.parent / "test_output" / "race_plan_test.fit"
        output_path.parent.mkdir(exist_ok=True)
        output_path.write_bytes(fit_bytes)
        print(f"Saved to: {output_path}")
        print()

        print("Validating with FitCSVTool...")
        result = validate_fit_bytes(fit_bytes)

        if result.valid:
            print("PASS: FIT file is valid")
        else:
            print("FAIL: FIT file has issues")
            for err in result.errors:
                print(f"  ERROR: {err}")
            for warn in result.warnings:
                print(f"  WARNING: {warn}")

        if result.csv_output:
            print()
            print("CSV representation:")
            print(result.csv_output)

    elif args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"File not found: {file_path}")
            sys.exit(1)

        print(f"Validating: {file_path}")
        fit_bytes = file_path.read_bytes()
        result = validate_fit_bytes(fit_bytes)

        if result.valid:
            print("PASS: FIT file is valid")
        else:
            print("FAIL: FIT file has issues")
            for err in result.errors:
                print(f"  ERROR: {err}")
            for warn in result.warnings:
                print(f"  WARNING: {warn}")

        if result.csv_output:
            print()
            print("CSV representation:")
            print(result.csv_output)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

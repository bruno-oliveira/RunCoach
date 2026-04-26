#!/usr/bin/env bash
# Download Garmin FIT SDK tools for local FIT file validation.
# These tools are NOT used in production - only for local development testing.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FIT_SDK_DIR="$PROJECT_DIR/tools/fit-sdk"

FIT_SDK_VERSION="21.201.0"
BASE_URL="https://github.com/garmin/fit-sdk-tools/releases/download/${FIT_SDK_VERSION}"

mkdir -p "$FIT_SDK_DIR"

echo "Downloading Garmin FIT SDK tools v${FIT_SDK_VERSION}..."

curl -L -o "$FIT_SDK_DIR/FitCSVTool.jar" \
  "${BASE_URL}/FitCSVTool.jar"

echo "Downloaded FitCSVTool.jar ($(du -h "$FIT_SDK_DIR/FitCSVTool.jar" | cut -f1))"

echo ""
echo "Verifying..."
java -jar "$FIT_SDK_DIR/FitCSVTool.jar" 2>&1 | head -1

echo ""
echo "FIT SDK tools ready at: $FIT_SDK_DIR"
echo "Usage: python -m app.services.fit_validation_local --generate-test"

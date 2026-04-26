# Garmin FIT File Format Reference

## FIT File Binary Structure

### File Header (14 bytes - preferred)

| Byte | Purpose |
|------|---------|
| 0 | Header size (12 or 14) |
| 1 | Protocol version (0x10=v1, 0x20=v2) |
| 2-3 | Profile version (e.g., 21.40 * 100 = 0x0843) |
| 4-7 | Data size (little-endian uint32) |
| 8-11 | ASCII `.FIT` (0x2E, 0x46, 0x49, 0x54) |
| 12-13 | Header CRC (optional, present in 14-byte header) |

### File Footer

- 2-byte CRC16 checksum of entire file

### Message Structure

Each message consists of:

1. **Definition Message** - describes the data fields
2. **Data Message(s)** - actual data using the definition

### File Types for Watch Import

| Type | Value | Directory on Watch |
|------|-------|-------------------|
| Activity | 4 | `GARMIN/Activity/` |
| Workout | 5 | `GARMIN/NewFiles/` -> `GARMIN/Workout/` |
| Course | 6 | `GARMIN/NewFiles/` -> `GARMIN/Courses/` |

### Required Messages by File Type

**Workout Files** (for structured training):

- `file_id` (required first message)
- `workout` (sport, sub_sport, num_valid_steps, wkt_name)
- `workout_step` (one per step: step_type, target_type, target_value, duration_type, duration_value)

**Activity Files** (for recorded runs):

- `file_id`
- `device_info` (best practice)
- `event` (timer start/stop)
- `record` (GPS, HR, pace data points)
- `lap`
- `session`
- `activity` (required last message)

### Import Methods to Watch

1. **USB Transfer**: Copy `.fit` to `GARMIN/NewFiles/` on device
2. **Garmin Connect Web**: Training -> Workouts -> Import (for workouts)
3. **Garmin Connect Mobile**: Training & Planning -> Workouts -> Import

### Python SDK Example

```python
from datetime import datetime, timezone
from garmin_fit_sdk import Encoder, Profile

encoder = Encoder()
encoder.on_mesg(Profile['mesg_num']['FILE_ID'], {
    'type': 'workout',
    'manufacturer': 'development',
    'product': 1,
    'time_created': datetime.now(tz=timezone.utc),
})
encoder.on_mesg(Profile['mesg_num']['WORKOUT'], {
    'sport': 'running',
    'sub_sport': 'generic',
    'num_valid_steps': 1,
    'wkt_name': 'Easy Run',
})
encoder.on_mesg(Profile['mesg_num']['WORKOUT_STEP'], {
    'message_index': 0,
    'step_type': 'active',
    'target_type': 'speed',
    'target_value': 300,  # 5:00/km in cm/s
    'duration_type': 'time',
    'duration_value': 1800,  # 30 minutes
})
data = encoder.close()
with open('workout.fit', 'wb') as f:
    f.write(data)
```

### Validation

- Use `FitCSVTool.jar` from FIT SDK to validate: `java -jar FitCSVTool.jar workout.fit`
- Or use `fitdecode` library: `python -m fitdecode workout.fit`

### Resources

- Official FIT SDK: https://developer.garmin.com/fit
- FIT Protocol: https://developer.garmin.com/fit/protocol/
- File Types: https://developer.garmin.com/fit/file-types/
- Cookbook: https://developer.garmin.com/fit/cookbook/
- Python SDK: https://github.com/garmin/fit-python-sdk

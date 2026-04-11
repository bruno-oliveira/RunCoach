"""Pre-encoded triathlon training plan data: Half Ironman (70.3) distance.

Data sourced from:
  IRONMAN/10-training-plan-70-3.md

Swim volumes converted from yards (1 yd ~ 0.914 m).
"""

from typing import Dict, List

# ---------------------------------------------------------------------------
# Half Ironman (70.3) plan  (20 weeks)   source: 10-training-plan-70-3.md
# Note: swim volumes converted from yards (1 yd ~ 0.914 m)
# ---------------------------------------------------------------------------

HALF_IRONMAN_PLAN: List[Dict] = [
    # --- Base Phase: Weeks 1-8 ---
    {
        "week": 1, "phase": "base", "is_recovery": False,
        "swim_volume": "2,195m", "bike_volume": "2 hrs 45 min", "run_volume": "1 hr 45 min", "total_hours": "5.5",
        "key_sessions": [
            {"type": "bike", "name": "Power Intervals", "description": "45 min: WU, MS 4\u00d720 sec sprint in high gear, CD"},
            {"type": "swim", "name": "Base Swim", "description": "1200 yd (1,097m): WU 300, 8\u00d725 drill, MS 2\u00d7100 moderate, 8\u00d725 kick, CD 300"},
            {"type": "run", "name": "Fartlek Run", "description": "30 min: WU 5 min, MS 6\u00d730 sec VO2max, CD 5 min"},
            {"type": "run", "name": "Foundation Run", "description": "35\u201340 min easy aerobic \u2014 Sunday long run to build base"},
        ],
        "weekly_schedule": {
            "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
            "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["run"],
        },
        "coaching_note": "Base phase begins. The primary goal is developing aerobic capacity and injury resistance across all three disciplines.",
    },
    {
        "week": 2, "phase": "base", "is_recovery": False,
        "swim_volume": "3,840m", "bike_volume": "2 hrs", "run_volume": "1 hr 45 min", "total_hours": "5",
        "key_sessions": [
            {"type": "bike", "name": "Power Intervals", "description": "50 min: WU, MS 5\u00d720 sec sprint in high gear, CD"},
            {"type": "swim", "name": "Fartlek + Sprint Swim", "description": "1300 yd (1,189m): WU 300, 8\u00d725 drill, MS 4\u00d7100 build/descend, 4\u00d725 kick, CD 300"},
            {"type": "brick", "name": "Brick Workout", "description": "Bike 45 min \u2192 Run 10 min moderate aerobic"},
            {"type": "swim", "name": "Long Base Swim", "description": "1600 yd (1,463m): WU 300, MS 1000 moderate, CD 300"},
        ],
        "weekly_schedule": {
            "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
            "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["brick"], "sunday": ["swim", "run"],
        },
        "coaching_note": "First brick workout. Weeks 2, 6 and so on include a Saturday bike-run brick.",
    },
    {
        "week": 3, "phase": "base", "is_recovery": False,
        "swim_volume": "4,025m", "bike_volume": "3 hrs 25 min", "run_volume": "2 hrs", "total_hours": "6.5",
        "key_sessions": [
            {"type": "bike", "name": "Power Intervals", "description": "50 min: WU, MS 5\u00d720 sec sprint in high gear, CD"},
            {"type": "swim", "name": "Base Swim", "description": "1400 yd (1,280m): WU 300, 8\u00d725 drill, MS 4\u00d7100 moderate, 8\u00d725 kick, CD 300"},
            {"type": "run", "name": "Fartlek Run", "description": "35 min: WU 5 min, MS 8\u00d730 sec VO2max, CD 5 min"},
            {"type": "bike", "name": "Long Foundation Bike", "description": "1 hr 15 min: WU, MS 55 min moderate, CD"},
        ],
        "weekly_schedule": {
            "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
            "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim", "run"],
        },
        "coaching_note": "Volume continues to build steadily. Three bikes and three swims this week \u2014 a full multi-sport load.",
    },
    {
        "week": 4, "phase": "base", "is_recovery": True,
        "swim_volume": "2,926m", "bike_volume": "1 hr 45 min", "run_volume": "1 hr 30 min", "total_hours": "4",
        "key_sessions": [
            {"type": "bike", "name": "Recovery Power Intervals", "description": "45 min: WU, MS 4\u00d720 sec sprint, CD \u2014 keep effort easy"},
            {"type": "swim", "name": "Easy Base Swim", "description": "1000 yd (914m): WU 300, 8\u00d725 drill, MS 2\u00d7100 moderate, CD 300"},
            {"type": "run", "name": "Easy Fartlek Run", "description": "30 min easy with 6\u00d730 sec light pickups"},
            {"type": "brick", "name": "Recovery Brick", "description": "Bike 45 min \u2192 Run 10 min moderate \u2014 keep effort controlled"},
        ],
        "weekly_schedule": {
            "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
            "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim", "brick"],
        },
        "coaching_note": "Recovery week: every fourth week is reduced to allow your body to fully absorb the training.",
    },
    {
        "week": 5, "phase": "base", "is_recovery": False,
        "swim_volume": "3,705m", "bike_volume": "3 hrs 30 min", "run_volume": "2 hrs 10 min", "total_hours": "6.5",
        "key_sessions": [
            {"type": "bike", "name": "Short Hill Climbs", "description": "55 min: WU, MS 6\u00d71 min hill climbs at speed, CD"},
            {"type": "swim", "name": "Base + Speed Swim", "description": "1450 yd (1,326m): WU 300, 8\u00d725 drill, MS 3\u00d7100 + 6\u00d725 speed, 8\u00d725 kick, CD 300"},
            {"type": "run", "name": "Speed Intervals", "description": "39 min: WU 10 min, MS 8\u00d730 sec with 2 min recovery, CD 9 min"},
            {"type": "bike", "name": "Long Foundation Bike", "description": "Two 90 min foundation rides \u2014 Saturday and Sunday"},
        ],
        "weekly_schedule": {
            "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
            "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["bike", "run"],
        },
        "coaching_note": "Hill climbing and speed work build power. Two long Saturday/Sunday bikes is a key load this week.",
    },
    {
        "week": 6, "phase": "base", "is_recovery": False,
        "swim_volume": "4,275m", "bike_volume": "2 hrs 25 min", "run_volume": "1 hr 25 min", "total_hours": "5",
        "key_sessions": [
            {"type": "bike", "name": "Hill Climbs", "description": "1 hr: WU, MS 7\u00d71 min hill climbs at speed, CD"},
            {"type": "swim", "name": "Fartlek + Sprint Swim", "description": "1700 yd (1,555m): WU 300, 6\u00d750 drill, MS 4\u00d7150 build/descend, 8\u00d725 kick, CD 300"},
            {"type": "swim", "name": "Swim Time Trial", "description": "1400 yd (1,280m): WU 200, MS 1000 maximum effort, CD 200 \u2014 race simulation!"},
            {"type": "brick", "name": "Brick Workout", "description": "Bike 45 min \u2192 Run 15 min moderate"},
        ],
        "weekly_schedule": {
            "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
            "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["brick"], "sunday": ["swim", "run"],
        },
        "coaching_note": "Your first swim time trial this Sunday \u2014 swim 1000 yards at maximum effort to measure baseline fitness.",
    },
    {
        "week": 7, "phase": "base", "is_recovery": False,
        "swim_volume": "4,985m", "bike_volume": "3 hrs", "run_volume": "1 hr 40 min", "total_hours": "6.5",
        "key_sessions": [
            {"type": "bike", "name": "Short Climbs", "description": "1 hr 5 min: WU, MS 8\u00d71 min hill climbs at speed, CD"},
            {"type": "swim", "name": "Base + Speed Swim", "description": "1700 yd (1,555m): WU 300, 8\u00d725 drill, MS 5\u00d7100 + 8\u00d725 speed, 8\u00d725 kick, CD 300"},
            {"type": "run", "name": "Speed Intervals", "description": "42 min: WU 10 min, MS 10\u00d730 sec VO2max with 2 min recovery, CD 10 min"},
            {"type": "bike", "name": "Long Foundation Bike", "description": "1 hr 45 min: WU, MS 1 hr 25 min moderate, CD \u2014 longest bike of base phase"},
        ],
        "weekly_schedule": {
            "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
            "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim"],
        },
        "coaching_note": "Final big base week. The 1h45 bike on Saturday is your longest ride so far \u2014 keep effort moderate.",
    },
    {
        "week": 8, "phase": "base", "is_recovery": True,
        "swim_volume": "4,070m", "bike_volume": "2 hrs 40 min", "run_volume": "1 hr 30 min", "total_hours": "5",
        "key_sessions": [
            {"type": "bike", "name": "Recovery Hill Climbs", "description": "55 min: WU, MS 6\u00d71 min hill climbs, CD \u2014 reduced intensity"},
            {"type": "swim", "name": "Recovery Base Swim", "description": "1250 yd (1,143m): WU 300, 8\u00d725 drill, MS 3\u00d7100 + 6\u00d725 speed, CD 300"},
            {"type": "swim", "name": "Fartlek + Sprint Swim", "description": "1600 yd (1,463m): WU 300, 8\u00d725 drill, MS 4\u00d7150 build, 8\u00d725 kick, CD 300"},
            {"type": "brick", "name": "Recovery Brick", "description": "Bike 45 min \u2192 Run 15 min moderate"},
        ],
        "weekly_schedule": {
            "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
            "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim", "brick"],
        },
        "coaching_note": "Second recovery week. The base phase ends here. Rest up \u2014 the build phase brings harder work.",
    },
    # --- Build Phase: Weeks 9-14 ---
    {
        "week": 9, "phase": "build", "is_recovery": False,
        "swim_volume": "5,350m", "bike_volume": "3 hrs 15 min", "run_volume": "2 hrs 30 min", "total_hours": "7",
        "key_sessions": [
            {"type": "bike", "name": "Long Hill Climbs", "description": "1 hr: WU, MS 2\u00d75 min hill climbs at VO2max, CD"},
            {"type": "swim", "name": "Base + VO2max Swim", "description": "1750 yd (1,600m): WU 300, 8\u00d725 drill, MS 3\u00d7100 + 4\u00d775 VO2max + 6\u00d725 speed, 8\u00d725 kick, CD 300"},
            {"type": "run", "name": "Lactate Intervals", "description": "32 min: WU 10 min, MS 12\u00d730 sec VO2max with 30 sec recovery, CD 10 min"},
            {"type": "bike", "name": "Long Ride", "description": "2 hrs easy-moderate. Build phase long ride begins \u2014 stay aerobic"},
        ],
        "weekly_schedule": {
            "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
            "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim", "run"],
        },
        "coaching_note": "Build phase: lactate intervals in all three disciplines will maximize aerobic capacity and faster speeds.",
    },
    {
        "week": 10, "phase": "build", "is_recovery": False,
        "swim_volume": "5,510m", "bike_volume": "2 hrs 50 min", "run_volume": "1 hr 45 min", "total_hours": "6.5",
        "key_sessions": [
            {"type": "bike", "name": "Lactate Intervals", "description": "1 hr: WU, MS 2\u00d73 min VO2max intervals on flat/rolling terrain, CD"},
            {"type": "swim", "name": "Base + VO2max Swim", "description": "1825 yd (1,669m): WU 300, 8\u00d725 drill, MS 3\u00d7100 + 5\u00d775 VO2max + 6\u00d725 speed, 8\u00d725 kick, CD 300"},
            {"type": "run", "name": "Lactate Intervals", "description": "34 min: WU 10 min, MS 14\u00d730 sec VO2max, CD 10 min + strides"},
            {"type": "brick", "name": "Long Brick", "description": "Bike 1 hr \u2192 Run 20 min moderate"},
        ],
        "weekly_schedule": {
            "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
            "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["brick"], "sunday": ["swim", "run"],
        },
        "coaching_note": "Saturday brick week. Lactate intervals are demanding \u2014 take full recoveries between efforts.",
    },
    {
        "week": 11, "phase": "build", "is_recovery": False,
        "swim_volume": "5,530m", "bike_volume": "3 hrs 45 min", "run_volume": "2 hrs 50 min", "total_hours": "8",
        "key_sessions": [
            {"type": "bike", "name": "Long Hill Climbs", "description": "1 hr 5 min: WU, MS 3\u00d75 min hill climbs at VO2max, CD"},
            {"type": "swim", "name": "Base + VO2max Swim", "description": "1900 yd (1,738m): WU 300, 8\u00d725 drill, MS 3\u00d7100 + 6\u00d775 VO2max + 6\u00d725 speed, 8\u00d725 kick, CD 300"},
            {"type": "swim", "name": "Swim Time Trial", "description": "2150 yd (1,966m): WU 250, MS 1650 maximum effort (1 mile), CD 250"},
            {"type": "run", "name": "Long Run", "description": "1 hr 5 min: WU 10 min, MS 45 min moderate, CD 10 min"},
        ],
        "weekly_schedule": {
            "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
            "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim", "run"],
        },
        "coaching_note": "Sunday swim time trial \u2014 1650 yards at max effort measures your fitness before the final build weeks.",
    },
    {
        "week": 12, "phase": "build", "is_recovery": True,
        "swim_volume": "4,025m", "bike_volume": "2 hrs 35 min", "run_volume": "1 hr 45 min", "total_hours": "5.5",
        "key_sessions": [
            {"type": "bike", "name": "Lactate Intervals", "description": "1 hr: WU, MS 2\u00d73 min VO2max, CD \u2014 recovery intensity"},
            {"type": "swim", "name": "Recovery Swim", "description": "1400 yd (1,280m): WU 300, 8\u00d725 drill, MS 3\u00d7100 + 4\u00d775 VO2max, CD 300"},
            {"type": "run", "name": "Lactate Intervals", "description": "32 min: WU 10 min, MS 12\u00d730 sec VO2max, CD 10 min"},
            {"type": "swim", "name": "Optional Sprint Triathlon", "description": "Race day: Swim 800m, Bike 12 miles, Run 3 miles \u2014 or do a time trial on your own"},
        ],
        "weekly_schedule": {
            "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
            "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["race"],
        },
        "coaching_note": "Recovery week with an optional sprint triathlon tune-up. Even if you don't race, keep effort easy.",
    },
    {
        "week": 13, "phase": "build", "is_recovery": False,
        "swim_volume": "5,760m", "bike_volume": "4 hrs", "run_volume": "2 hrs 55 min", "total_hours": "8.5",
        "key_sessions": [
            {"type": "bike", "name": "Long Hill Climbs", "description": "1 hr 10 min: WU, MS 4\u00d75 min hill climbs at VO2max, CD"},
            {"type": "swim", "name": "Base + VO2max Swim", "description": "1900 yd (1,738m): WU 300, 8\u00d725 drill, MS 5\u00d7100 + 4\u00d7100 VO2max, 8\u00d725 kick, CD 300"},
            {"type": "bike", "name": "Long Ride", "description": "2 hrs 30 min: WU, MS 2 hrs 10 min moderate, CD \u2014 your longest ride to date"},
            {"type": "run", "name": "Long Run", "description": "1 hr 10 min: WU 10 min, MS 50 min moderate, CD 10 min"},
        ],
        "weekly_schedule": {
            "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
            "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim", "run"],
        },
        "coaching_note": "Biggest build week yet \u2014 2h30 long bike and 1h10 long run. These long efforts build race-day endurance.",
    },
    {
        "week": 14, "phase": "build", "is_recovery": False,
        "swim_volume": "5,945m", "bike_volume": "3 hrs 15 min", "run_volume": "2 hrs 50 min", "total_hours": "8",
        "key_sessions": [
            {"type": "bike", "name": "Lactate Intervals", "description": "1 hr 15 min: WU, MS 4\u00d73 min VO2max on flat/rolling terrain, CD"},
            {"type": "swim", "name": "Base + VO2max Swim", "description": "2000 yd (1,829m): WU 300, 8\u00d725 drill, MS 6\u00d7100 + 4\u00d7100 VO2max, 8\u00d725 kick, CD 300"},
            {"type": "run", "name": "Long Lactate Run", "description": "40 min: WU 10 min, MS 20\u00d730 sec VO2max with 30 sec recovery, CD 10 min"},
            {"type": "brick", "name": "Long Brick", "description": "Bike 1 hr 15 min \u2192 Run 30 min moderate"},
        ],
        "weekly_schedule": {
            "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
            "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim", "brick"],
        },
        "coaching_note": "Final build week. The long brick on Sunday is race-specific preparation \u2014 aim for even pacing.",
    },
    # --- Peak Phase: Weeks 15-18 ---
    {
        "week": 15, "phase": "peak", "is_recovery": False,
        "swim_volume": "6,125m", "bike_volume": "4 hrs 15 min", "run_volume": "3 hrs", "total_hours": "9",
        "key_sessions": [
            {"type": "bike", "name": "Tempo Bike", "description": "1 hr: WU 13 min, MS 2\u00d712 min threshold with 10 min recovery, CD 13 min"},
            {"type": "swim", "name": "Base + VO2max Swim", "description": "2100 yd (1,920m): WU 300, 8\u00d725 drill, MS 6\u00d7100 + 5\u00d7100 VO2max, 8\u00d725 kick, CD 300"},
            {"type": "bike", "name": "Long Ride", "description": "2 hrs 45 min: WU, MS 2 hrs 25 min moderate, CD \u2014 your longest ride"},
            {"type": "run", "name": "Long Run", "description": "1 hr 20 min: WU 10 min, MS 1 hr moderate, CD 10 min \u2014 your longest run"},
        ],
        "weekly_schedule": {
            "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
            "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim", "run"],
        },
        "coaching_note": "Peak phase begins. Longest endurance work of the plan: 2h45 bike and 1h20 run. Stay aerobic.",
    },
    {
        "week": 16, "phase": "peak", "is_recovery": True,
        "swim_volume": "4,665m", "bike_volume": "2 hrs 20 min", "run_volume": "2 hrs 15 min", "total_hours": "6",
        "key_sessions": [
            {"type": "bike", "name": "Tempo Bike", "description": "55 min: WU 17 min, MS 22 min threshold, CD 16 min"},
            {"type": "swim", "name": "Recovery Swim", "description": "1600 yd (1,463m): WU 300, 8\u00d725 drill, MS 4\u00d7100 + 4\u00d7100 VO2max, CD 300"},
            {"type": "run", "name": "Tempo Run", "description": "34 min: WU 10 min, MS 14 min threshold, CD 10 min"},
            {"type": "swim", "name": "Olympic-Distance Tune-Up", "description": "Optional: Swim 1.5km \u2192 Bike 40km \u2192 Run 10km \u2014 or a time trial"},
        ],
        "weekly_schedule": {
            "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
            "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["race"],
        },
        "coaching_note": "Recovery week with an optional Olympic-distance tune-up race. A great fitness check before the final push.",
    },
    {
        "week": 17, "phase": "peak", "is_recovery": False,
        "swim_volume": "6,125m", "bike_volume": "4 hrs 30 min", "run_volume": "3 hrs 10 min", "total_hours": "9.5",
        "key_sessions": [
            {"type": "bike", "name": "Tempo Bike", "description": "1 hr 5 min: WU 21 min, MS 24 min threshold, CD 20 min"},
            {"type": "swim", "name": "Base + VO2max Swim", "description": "2100 yd (1,920m): WU 300, 8\u00d725 drill, MS 5\u00d7100 + 6\u00d7100 VO2max, 8\u00d725 kick, CD 300"},
            {"type": "bike", "name": "Peak Long Ride", "description": "3 hrs: WU, MS 2 hrs 40 min moderate, CD \u2014 longest ride of the plan"},
            {"type": "run", "name": "Peak Long Run", "description": "1 hr 30 min: WU 10 min, MS 1 hr 10 min moderate, CD 10 min \u2014 your longest run"},
        ],
        "weekly_schedule": {
            "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
            "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim", "run"],
        },
        "coaching_note": "Your peak training week: 3 hr bike and 1h30 run. Peak volume at ~9.5 hrs total \u2014 you are ready.",
    },
    {
        "week": 18, "phase": "peak", "is_recovery": False,
        "swim_volume": "6,138m", "bike_volume": "3 hrs 45 min", "run_volume": "2 hrs 30 min", "total_hours": "8.5",
        "key_sessions": [
            {"type": "bike", "name": "Tempo Bike", "description": "1 hr 10 min: WU 22 min, MS 26 min threshold, CD 22 min"},
            {"type": "swim", "name": "Base + VO2max Swim", "description": "2100 yd (1,920m): WU 300, 8\u00d725 drill, MS 5\u00d7100 + 6\u00d7100 VO2max, 8\u00d725 kick, CD 300"},
            {"type": "swim", "name": "Swim Time Trial", "description": "2512 yd (2,297m): WU 200, MS 2112 yd (1.2 miles) maximum effort, CD 200 \u2014 final time trial!"},
            {"type": "brick", "name": "Long Race-Simulation Brick", "description": "Bike 1 hr 45 min \u2192 Run 45 min moderate \u2014 your final major brick workout"},
        ],
        "weekly_schedule": {
            "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
            "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["brick"], "sunday": ["swim", "run"],
        },
        "coaching_note": "Final peak week: 1.2-mile swim time trial and a 1h45+45min brick. Confidence-building before the taper.",
    },
    # --- Taper Phase: Weeks 19-20 ---
    {
        "week": 19, "phase": "taper", "is_recovery": False,
        "swim_volume": "5,670m", "bike_volume": "3 hrs 45 min", "run_volume": "2 hrs 50 min", "total_hours": "8.5",
        "key_sessions": [
            {"type": "bike", "name": "Tempo Bike", "description": "1 hr 15 min: WU 19 min, MS 2\u00d714 min threshold with 10 min recovery, CD 18 min"},
            {"type": "swim", "name": "Base + VO2max Swim", "description": "2100 yd (1,920m): WU 300, MS 5\u00d7100 + 6\u00d7100 VO2max, CD 300"},
            {"type": "run", "name": "Tempo Run", "description": "40 min: WU 10 min, MS 20 min threshold, CD 10 min"},
            {"type": "run", "name": "Long Run", "description": "1 hr 5 min: WU 10 min, MS 45 min moderate, CD 10 min \u2014 taper long run"},
        ],
        "weekly_schedule": {
            "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
            "thursday": ["bike"], "friday": ["swim", "run"], "saturday": ["bike"], "sunday": ["swim", "run"],
        },
        "coaching_note": "Taper begins Thursday. Volume will steadily decrease to ensure you arrive to the start line fresh.",
    },
    {
        "week": 20, "phase": "taper", "is_recovery": True,
        "swim_volume": "2,560m", "bike_volume": "1 hr 45 min", "run_volume": "1 hr", "total_hours": "4",
        "key_sessions": [
            {"type": "bike", "name": "Tempo Bike", "description": "1 hr: WU 13 min, MS 2\u00d712 min threshold with 10 min recovery, CD 13 min"},
            {"type": "swim", "name": "Race-Week Swim", "description": "1700 yd (1,555m): WU 300, 8\u00d725 drill, MS 3\u00d7100 + 6\u00d7100 VO2max, CD 300"},
            {"type": "run", "name": "Tempo Run", "description": "32 min: WU 10 min, MS 12 min threshold, CD 10 min"},
            {"type": "swim", "name": "Pre-Race Swim", "description": "1100 yd (1,006m): WU 300, MS 2\u00d7200 threshold, 4\u00d725 speed, CD 300"},
        ],
        "weekly_schedule": {
            "monday": ["rest"], "tuesday": ["bike"], "wednesday": ["swim", "run"],
            "thursday": ["bike"], "friday": ["swim"], "saturday": ["swim"], "sunday": ["race"],
        },
        "coaching_note": "Race week! Minimal training \u2014 trust your 20 weeks of preparation. Race day is Sunday: Swim 1.2mi \u2192 Bike 56mi \u2192 Run 13.1mi.",
    },
]

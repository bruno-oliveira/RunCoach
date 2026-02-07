# RunCoach Training Philosophy

This document explains the core training science and principles behind RunCoach's training plan generation algorithm.

---

## Table of Contents

1. [Foundational Training Principles](#1-foundational-training-principles)
2. [Periodization Model](#2-periodization-model)
3. [Progressive Overload Strategy](#3-progressive-overload-strategy)
4. [Recovery Week Strategy](#4-recovery-week-strategy)
5. [Mileage Progression System](#5-mileage-progression-system)
6. [Workout Distribution Philosophy](#6-workout-distribution-philosophy)
7. [Long Run Strategy](#7-long-run-strategy)
8. [Training Intensity Principles](#8-training-intensity-principles)
9. [Distance-Specific Adaptations](#9-distance-specific-adaptations)
10. [Training Tips Philosophy](#10-training-tips-philosophy)

---

## 1. Foundational Training Principles

### Core Training Beliefs

**1. Training Principle: Long Run is King**
- The long run is always the longest distance of the week
- Easy runs are capped at 95% of long run distance
- Quality workouts are capped at 85% of long run distance
- This ensures the long run remains the primary endurance builder

**2. Training Principle: Recovery is Training Too**
- Every 4th week in Base and Build phases is a recovery week
- Recovery reduces weekly mileage by 25%
- Active recovery (swimming/light walking) promotes blood flow without impact
- Recovery prevents overtraining and allows adaptation

**3. Training Principle: Specificity Adaptation**
- Training plans adapt to race distance
- Long run percentages increase with race distance
- Quality workout intensity and frequency scale appropriately
- Nutrition and fueling tips are distance-specific

**4. Training Principle: Progressive Consistency > Intensity**
- Plans prioritize consistent weekly mileage over sporadic high-intensity efforts
- Mileage increases are gradual (10% rule)
- Recovery weeks allow adaptation before loading again
- Consistency builds the aerobic base; intensity builds on that base

**5. Training Principle: Balance is Essential**
- Hard/easy balance built into every week
- Rest days are mandatory (at least 1-2 per week)
- Active recovery day (Tuesday) is separate from rest days
- Strength training integrated into easy runs

---

## 2. Periodization Model

Training plans are divided into four phases based on the [periodization](https://en.wikipedia.org/wiki/Periodization) concept:

### Phase Structure

```python
# Phase calculation based on total weeks
if weeks <= 10:
    base = round(weeks * 0.40)    # 40% base building
    build = round(weeks * 0.30)   # 30% quality work
    peak = 1                      # 1 week peak
    taper = remainder             # ~10% taper
elif weeks <= 14:
    base = round(weeks * 0.45)    # 45% base
    build = round(weeks * 0.30)   # 30% build
    peak = 1
    taper = remainder
elif weeks <= 18:
    base = round(weeks * 0.50)    # 50% base
    build = round(weeks * 0.25)   # 25% build
    peak = round(weeks * 0.10)    # 10% peak
    taper = remainder
else:
    base = round(weeks * 0.50)    # 50% base
    build = round(weeks * 0.25)   # 25% build
    peak = round(weeks * 0.10)    # 10% peak
    taper = remainder
```

### Phase Objectives

#### Base Phase (40-50% of training)
- **Goal:** Build aerobic capacity and foundation
- **Key Workouts:** Easy runs and long runs only
- **Mileage:** Progressive increase to 70% of peak
- **Quality Workouts:** 0 quality workouts per week
- **Intensity Focus:** Low-moderate, conversational pace

*Rationale:* Strengthens the cardiovascular system and soft tissues, prepares body for higher intensity work. Without base, high-intensity training leads to injury before adaptation.

#### Build Phase (25-30% of training)
- **Goal:** Increase lactate threshold and sport-specific fitness
- **Key Workouts:** Easy runs + long run + 1-2 quality workouts/week
- **Mileage:** Progressive increase from 70% to 100% of peak
- **Quality Workouts:** 1-2 per week (tempo, interval, or hill)
- **Intensity Focus:** Medium-high intensity on quality days

*Rationale:* Once aerobic base is established, add quality work to improve running economy and lactate threshold. This is where race-pace fitness is built.

#### Peak Phase (1-10% of training)
- **Goal:** Maintain peak fitness and race specificity
- **Key Workouts:** All workout types at peak volume
- **Mileage:** Maintain at 95-100% of peak
- **Quality Workouts:** 1-2 per week
- **Intensity Focus:** High-intensity, race-pace work

*Rationale:* Short phase to sharpen and refine. Don't seek further gains, but maintain peak fitness while allowing final adaptations.

#### Taper Phase (10-15% of training)
- **Goal:** Freshen up and race day readiness
- **Key Workouts:** Reduced volume, some quality maintained
- **Mileage:** Progressive reduction to 60% of peak
- **Quality Workouts:** 0-1 per week
- **Intensity Focus:** Some intensity but lower volume

*Rationale:* Tapering improves performance by 2-8%. Body adapts to accumulated training during reduction. Race day should feel "easy compared to recent training."

---

## 3. Progressive Overload Strategy

### The 10% Rule

RunCoach applies a conservative progressive overload principle:

**Maximum weekly increase: 10%**
- Week-to-week mileage increase is capped at ~10%
- Applied across non-recovery weeks only
- Recovery weeks reset to 75% of previous non-recovery week

### Linear Progression Calculation

```python
# Calculate needed increase across remaining non-recovery weeks
weeks_passed = count_non_recovery_weeks_completed
total_non_recovery = count_non_recovery_weeks_in_phase
weeks_remaining = total_non_recovery - weeks_passed

needed_increase = phase_end_target - current_week_km
weekly_increase = needed_increase / weeks_remaining
```

**Example:**
- Phase start: 20km/week
- Phase end goal: 35km/week
- Remaining non-recovery weeks: 5
- Weekly increase: (35 - 20) / 5 = **3km per week**

### Why Conservative Progression?

1. **Prevents Injury:** Running injuries are cumulative. Rapid increases strain tissues faster they can strengthen.

2. **Improves Adaptation:** Muscles, tendons, and cardiovascular system need 3-4 weeks to adapt to each load increase.

3. **Ensures Consistency:** Overly aggressive progressions lead to burnout or forced rest weeks.

4. **Builds Mental Consistency:** Achievable weekly goals build confidence. Constant "too hard" weeks break mental toughness.

---

## 4. Recovery Week Strategy

### Recovery Week Pattern

**Every 4th week is a recovery week in Base and Build phases**

```python
if week_number % 4 == 0:
    is_recovery_week = True
```

**Recovery reduction: 25%**
```python
week_km = current_week_km * 0.75
```

**What changes during recovery weeks?**
- Weekly mileage: 75% of previous week
- Quality workouts: 0 (no tempo/interval/hill)
- Long run: Still present but reduced
- Easy runs: Still present, reduced

**What stays the same?**
- Frequency of runs
- Active recovery day on Tuesday
- Rest day(s)
- Strength training on easy days

### Why Recovery Weeks?

**1. Physiological Adaptation**
- Fitness gains happen during recovery, not training
- Muscles need 24-72 hours to repair after hard training
- Tendons, ligaments, and bones need 1-2 weeks to strengthen

**2. Psychological Refresh**
- Prevents mental burnout
- Breaks the "always increasing" pattern
- Allows for planned lighter weeks while maintaining consistency

**3. Injury Prevention**
- Cumulative fatigue from hard training makes runners vulnerable
- Recovery weeks clear accumulated fatigue
- Reduces risk of overuse injuries

**4. Strategic Tapering Practice**
- Teaches body what reduced training feels like
- Pre-race taper won't feel "weird" if body is used to reduced weeks

### Recovery Week Schedule

| Day | Normal Week | Recovery Week |
|-----|-------------|----------------|
| Monday | Easy Run | Easy Run (shorter) |
| Tuesday | Active Recovery | Active Recovery |
| Wednesday | Quality + Easy | Easy Run only |
| Thursday | Easy Run | Easy Run |
| Friday | Rest | Rest or Light Activity |
| Saturday | Long Run | Long Run (reduced) |
| Sunday | Easy/Rest | Easy/Rest |

**Example:**
- Normal week: 30km total
- Recovery week: 30km × 0.75 = **22.5km total**

---

## 5. Mileage Progression System

### Peak Mileage Calculation

Peak mileage is based on race distance and current fitness level:

```python
# Ideal peaks by distance
5K:     max(25km, current_km × 2.0)
10K:    max(30km, current_km × 2.2)
Half:   max(40km, current_km × 2.3)
Trail 30K: 50km (trail running has higher base requirement)
Marathon: max(50km, current_km × 2.0)
```

**Length-based Multiplier:**
- Shorter plans (6-8 weeks): Less room to increase, modest gains
- Standard plans (10-16 weeks): Balanced progression
- Extended plans (17-20+ weeks): Aggressive potential for improvement

### Phase-Specific Progression

#### Base Phase: 70% of Peak
```python
base_end_target = peak_km * 0.70
```

**Progression:**
- Start at current mileage
- Linear increase to 70% of peak across non-recovery weeks
- Recovery weeks reset to 75% of last hard week

#### Build Phase: 100% of Peak
```python
build_end_target = peak_km
```

**Progression:**
- Start from 70% of peak (or where Base ended)
- Linear increase to 100% of peak across non-recovery weeks
- Every 3rd week is recovery (25% reduction)

#### Peak Phase: 95-100% of Peak
```python
week_km = peak_km * (0.97 + (week % 3) * 0.01)
```

**Progression:**
- Maintain 95-100% of peak
- Slight variation (±3%) to feel fresh but fit
- No recovery weeks in peak

#### Taper Phase: 60-100% of Peak
```python
if taper_weeks == 1:
    week_km = peak_km * 0.60          # Final week: 60% of peak
elif taper_weeks == 2:
    week_km = [0.80, 0.60]           # -20%, then -40%
elif taper_weeks == 3:
    week_km = [0.80, 0.70, 0.60]     # -20%, -30%, -40%
```

**Progression:**
- Gradual reduction from peak to 60%
- Last week is 60% of peak (maintains fitness, reduces fatigue)
- Maintains some intensity with less volume

### Example 10K Progression (8-week plan)

| Phase | Weeks | Mileage Range | Pattern |
|-------|-------|---------------|---------|
| Base | 1-3 | 20km → 27km (→ 22km recovery) | +3km, +3km, recovery |
| Build | 4-7 | 22km → 36km | +3-5km per week |
| Peak | 8 | **36km** | Peak week |
| Taper | 9-10 | 36km → 22km | -20%, -40% |

---

## 6. Workout Distribution Philosophy

### Weekly Structure

Every week follows this pattern:

```
Day 1 (Monday):   Easy Run
Day 2 (Tuesday):  Active Recovery (cross-training)
Day 3 (Wednesday): Quality Workout + Easy (if applicable)
Day 4 (Thursday):  Easy Run or Quality
Day 5 (Friday):   Rest Day
Day 6 (Saturday):  Long Run (always)
Day 7 (Sunday):   Rest or Easy Run
```

### Workout Types

#### Easy Runs
**Purpose:** Build aerobic base, recovery between quality workouts

**Intensity:** Low (conversational pace)

**Distribution:**
- Fills remaining days after quality and long run
- Capped at 95% of long run distance
- No cap in recovery weeks (since long run is reduced anyway)

**Example:** 8km easy run on 30km week with 12km long run

#### Active Recovery (Tuesday)
**Purpose:** Promote blood flow without impact, aid muscle repair

**Intensity:** Very low (walking, swimming, cycling)

**Note:** This is different from rest day. Active recovery is cross-training (swimming, easy walking) and doesn't count toward `max_runs_per_week`.

**Examples:**
- 30-45 min swimming
- 20-30 min easy walking
- Light cycling

#### Quality Workouts
**Purpose:** Build lactate threshold, running economy, sport-specific fitness

**Types:**
- **Tempo:** Sustained threshold effort (medium intensity)
- **Interval:** High-intensity repeats with recovery (high intensity)
- **Hill:** Hill repeats for power and strength (high intensity)

**Distribution by Phase:**
- **Base:** 0 quality workouts (all easy + long run)
- **Build:** 1-2 quality workouts/week (max_runs dependent)
- **Peak:** 1-2 quality workouts/week
- **Taper:** 0-1 quality workout/week

**Distribution Logic:**
```python
if phase == 'base' or is_recovery_week:
    quality_workouts = 0
elif max_runs >= 5:
    quality_workouts = 2  # Standard: tempo + interval
else:
    quality_workouts = 1  # Minimal: tempo or interval
```

**Trail Running Special Case:**
- Alternates between hill and interval weeks
- Hill weeks: 2 hill workouts
- Interval weeks: 2 interval workouts
- Builds leg strength and downhill technique for trail racing

#### Long Run
**Purpose:** Build endurance, mental toughness, race-day simulation

**Intensity:** Medium (conversational for most, race pace finish possible)

**Schedule:** Always Day 6 (Saturday)

**Distance Rationale (see Section 7)**

#### Rest Days
**Purpose:** Complete rest for tissue repair

**Intensity:** None

**Minimum:** 1-2 per week (based on max_runs)

**Examples:** Complete rest, light stretching, mobility work

### Workout Distribution Formulas

**Base Phase:**
```
Easy Runs: remaining days after long run
 Quality: 0
 Rest: 7 - (max_runs + 1)
```

**Build/Peak Phases:**
```
Long Run: 1 always
Quality: 1 (if max_runs >= 4) or 2 (if max_runs >= 5)
Easy: remaining days after long run + quality
Rest: 7 - (max_runs + 1)
```

**Taper Phase:**
```
Similar to build but quality reduced to 0-1
```

---

## 7. Long Run Strategy

### Long Run Ratios by Race Distance

The long run distance is calculated as a percentage of weekly mileage, with the percentage increasing for longer races:

```python
ratio_ranges = {
    '5K': {
        'base':  (0.25, 0.30),   # 25-30% of weekly mileage
        'build': (0.28, 0.32),
        'peak':  (0.30, 0.35),
        'taper': (0.25, 0.30)
    },
    '10K': {
        'base':  (0.28, 0.33),   # 28-33%
        'build': (0.31, 0.36),
        'peak':  (0.35, 0.40),
        'taper': (0.28, 0.33)
    },
    'Half': {
        'base':  (0.30, 0.35),   # 30-35%
        'build': (0.33, 0.38),
        'peak':  (0.38, 0.43),
        'taper': (0.30, 0.35)
    },
    'Trail': {
        'base':  (0.30, 0.35),   # 30-35% (trail needs endurance)
        'build': (0.35, 0.40),
        'peak':  (0.40, 0.45),
        'taper': (0.35, 0.40)
    },
    'Marathon': {
        'base':  (0.32, 0.38),   # 32-38%
        'build': (0.35, 0.42),
        'peak':  (0.40, 0.45),
        'taper': (0.32, 0.38)
    }
}
```

**Why Increasing Ratios?**

- **5K:** 25-30% of weekly distance. Sprint events benefit from speed, so long run is shorter relative to total.
- **10K:** 28-33%. Balance needed between speed and endurance.
- **Half/Marathon:** 38-45%. Primary focus is endurance capacity.
- **Trail 30K:** 40-45%. Trail running is demanding, long runs build trail-specific endurance.

### Long Run Caps

Maximum long run distances prevent over-accumulation and ensure safety:

```python
long_run_cap = {
    5.0:  8.0km,
    10.0: 15.0km,
    21.1: 20.0km,
    30.0: 24.0km,
    42.2: 32.0km
}.get(target_distance, target_distance * 0.77)
```

**Rationale:**
- 5K training doesn't need >8km long runs (event is short)
- 10K training doesn't need >15km long runs
- Training long runs longer than 30km (for marathon) increases injury risk
- Marathon long run caps at 32km (~80% of race distance)

### Long Run Minimums

Minimum race-specific to ensure race readiness:

```python
min_long_run = target_distance * 0.25  # 25% of race distance
```

**Examples:**
- 10K race → minimum 2.5km long run
- Half marathon → minimum 5.3km long run
- Marathon → minimum 10.5km long run (though marathon runners will do 20-30km in practice)

### Long Run Progression

Within each phase, the long run ratio progressively increases:

```python
# Calculate progression within phase
week_in_phase = current_week - phase_start_week
total_in_phase = phase_duration

if total_in_phase > 1:
    progression = week_in_phase / (total_in_phase - 1)

# Apply progression to ratio range
ratio = min_ratio + (max_ratio - min_ratio) * progression
```

**Example (10K, Build Phase):**
- Week 1: 31% of weekly distance
- Week 2: 33% of weekly distance
- Week 3: 35% of weekly distance
- Week 4: 36% of weekly distance

### Long Run Reduction on Recovery Weeks

**Recovery reduction: 8-12%**

```python
if is_recovery_week:
    reduction = random.uniform(0.08, 0.12)
    ratio = ratio * (1.0 - reduction)
```

**Rationale:** Long run is the most stressful weekly workout. Even on recovery weeks, it remains but is reduced.

### Long Run Descriptions

Varied long run descriptions serve race-specific purposes:

1. **Conversational Pace:** Base building, endurance, mental toughness
2. **Race Pace Finish:** Teaches race pace execution fatigued
3. **Varied Terrain Nutrition Practice:** Prepares fueling and pacing strategies

---

## 8. Training Intensity Principles

### Intensity Zones

| Workout Type | Intensity Zone | Description | Purpose |
|--------------|----------------|-------------|---------|
| Rest | None | Complete rest | Tissue repair |
| Recovery | Very Low | Swimming/Walking | Blood flow, no impact |
| Easy | Low | Conversational pace | Aerobic base, adaptation |
| Tempo | Medium | Threshold (~race pace) | Lactate threshold |
| Long | Medium | Conversational to race pace | Endurance capacity |
| Interval | High | Vo2 max (5K pace) | Speed, running economy |
| Hill | High | Explosive power | Leg strength, power |

### Quality Workout Distribution

**By Phase:**

| Phase | Quality Workouts | Rationale |
|-------|----------------|-----------|
| Base | 0 | Develop aerobic base without intensity |
| Build | 1-2 | Build lactate threshold gradually |
| Peak | 1-2 | Maintain threshold, sharpen race pace |
| Taper | 0-1 | Maintain some intensity, reduce volume |

**By Max Runs:**

```python
if max_runs >= 5:
    quality_workouts = 2  # Tempo + Interval
elif max_runs >= 4:
    quality_workouts = 1  # Tempo or Interval
else:
    quality_workouts = 1  # One quality only
```

**Rationale:**
- Runners with higher max_runs can handle more quality
- Less frequent runners should prioritize easy volume over quality intensity
- Two quality workouts/week is standard for intermediate+ runners

### Quality Workout Examples

#### Tempo Runs (Medium Intensity)
```
Variation 1: 2km warmup, [X-X-2]km at threshold, 2km cooldown
Variation 2: 3x[ (distance-2)/3 ]km at tempo with 3min recovery
Variation 3: Tempo with 4x30sec faster surges
```

**Purpose:** Sustain race-pace effort for extended periods.

#### Interval Runs (High Intensity)
```
Variation 1: 6x400m at 5K pace, 400m recovery
Variation 2: 400m-800m-1200m-800m-400m pyramid
Variation 3: 8x45sec hill repeats
Variation 4: [distance/0.8]x800m at marathon goal pace
```

**Purpose:** Improve running economy, VO2 max, speed.

#### Hill Workouts (High Intensity)
```
Variation 1: 10x30sec steep hill repeats
Variation 2: 5x2min moderate grade at threshold
Variation 3: 8x20sec explosive bounding
```

**Purpose:** Leg strength, power, running form.

---

## 9. Distance-Specific Adaptations

### 5K Training

**Mileage:** 25-40km/week peak

**Long Run:** 25-30% of weekly, capped at 8km

**Focus:** Speed, economy, explosive power

**Quality:** Tempo + Interval (or Hill)

**Tips:**
- Practice race starts with controlled acceleration
- Include strides after easy runs
- Focus on explosive leg turnover

### 10K Training

**Mileage:** 30-64km/week peak

**Long Run:** 28-36% of weekly, capped at 15km

**Focus:** Speed endurance, lactate threshold

**Quality:** Tempo + Interval

**Tips:**
- Practice fast finishes on easy runs
- Tempo runs at goal race pace (3-5km total)
- Practice fueling at 5-6km mark

### Half Marathon Training

**Mileage:** 40-72km/week peak

**Long Run:** 30-38% of weekly, capped at 20km

**Focus:** Endurance capacity, fueling, mental toughness

**Quality:** Tempo + Interval

**Tips:**
- Fuel every 45-60min during long runs
- Include race-pace efforts in long runs
- Practice running on tired legs

### Trail 30K Training

**Mileage:** 40-80+km/week peak (lower overall but higher easy miles due to terrain)

**Long Run:** 35-40% of weekly, capped at 24km

**Focus:** Hills, technical terrain, leg strength, power hiking

**Quality:** Alternates Hill + Interval weeks

**Tips:**
- Practice power hiking steep sections
- Test trail shoes on technical terrain
- Practice fueling with handheld bottles
- Include downhill running practice

### Marathon Training

**Mileage:** 50-96km/week peak

**Long Run:** 32-38% of weekly, capped at 32km

**Focus:** Endurance, fueling mastery, mental preparation

**Quality:** Tempo + Interval

**Tips:**
- Comprehensive fueling strategy
- Very long runs (75-90% race distance)
- Practice marathon pace during long runs
- Wall training: push through fatigue

---

## 10. Training Tips Philosophy

Training tips are strategically distributed to guide runners through each phase:

### Tip Rotation System

**12-week rotation cycle (repeats for longer plans):**

| Week | Focus Categories |
|------|------------------|
| 1 | Foundation, Routine, Equipment |
| 2 | Form, Consistency, Recovery |
| 3 | Endurance, Mental, Nutrition |
| 4 | Pace, Strength, Injury Prevention |
| 5 | Race Simulation, Strategy, Gear |
| 6 | Confidence, Taper Prep, Mental Training |
| 7 | Final Prep, Logistics, Race Day |
| 8 | Taper, Visualization, Recovery Focus |
| 9 | Sharpening, Final Workouts, Race Ready |
| 10 | Peak Performance, Race Execution, Post-Race |
| 11 | Advanced Strategy, Course-Specific, Conditions |
| 12 | Marathon Focus, Fueling Mastery, Mental Toughness |

**Why this order?**
- **Weeks 1-3:** Foundation building
- **Weeks 4-6:** Advancing training quality
- **Weeks 7-8:** Peaking and tapering guidance
- **Weeks 9-10:** Race-specific strategy
- **Weeks 11-12:** Advanced race execution

### Tip Selection

**4 tips per week:**

1. **3 technical tips** from the current week's focus category
2. **1 motivational tip** that rotates weekly

**Technical tip sources:**
- Module-level tip database grouped by 24 categories
- Rotated based on week number to ensure variety
- Distance-specific tips added for race distance focus

### Motivational Tips

Sample motivational tip rotation:
```
Week 1: Every mile in training pays dividends on race day
Week 2: Trust the process - you're stronger than last week
Week 3: Consistency is the secret weapon of successful runners
Week 4: Embrace the challenge - that's where growth happens
Week 5: Your future race self is thanking you for this work
Week 6: One day at a time, one workout at a time
Week 7: The pain of training is temporary, the pride is forever
Week 8: You've already committed - now execute with confidence
```

**Purpose:** Running is ~70% mental. Motivational tips counter training burnout and maintain perspective.

---

## Summary: Training Philosophy Core Tenets

### 1. Build Before You Build Up
Establish aerobic base with easy mileage before adding intensity. Without base, intensity doesn't improve fitness, it creates injury.

### 2. Recover as You Train
Recovery weeks aren't optional—they're where gains happen. Every 4th week, reduce by 25% and let your body adapt.

### 3. Long Run is Primary
The long run is always your longest workout. Everything else (easy runs, quality workouts) is structured around it.

### 4. Progress Conservative, Not Aggressive
Cap weekly increases at ~10%. Train slow, race fast. Over-training is more common than under-training.

### 5. Hard/Easy Balance
Hard days push adaptation. Easy days build aerobic capacity and allow recovery. Don't make easy days hard—hard days become easy days.

### 6. Specificity Matters
Training for a marathon is different than training for 5K. Workouts, long run ratios, and tips adapt to race distance.

### 7. Rest is Training Too
At least 1 rest day per week plus active recovery. Tissue repair happens during rest, not running.

### 8. Mental Training is Physical Training
Runners hit the wall mentally before they hit it physically. Mental toughness is trained, not innate.

---

## References

- Lydiard, Arthur (*Running to the Top*)
- Daniels, Jack (*Daniels' Running Formula*)
- Pfitzinger, Pete & Scott Douglas (*Road Racing for Serious Runners*)
- Noakes, Tim (*The Lore of Running*)
- Higdon, Hal (*Hal Higdon's Marathon Training*)

---

**Last Updated:** 2024-02-07
**Version:** 1.0
**Purpose:** Internal documentation for RunCoach training algorithm design decisions
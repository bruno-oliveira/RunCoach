# Training Plan Logic Documentation

## Overview

This document details all decisions and logic encoded in the RunCoach training plan generator (`app/core/plan_generator.py`). The generator creates structured training plans following evidence-based training principles while respecting runner safety and progressive overload.

## Core Training Philosophy

### Guiding Principles

1. **Progressive Overload**: Gradually increase training load to build fitness
2. **Specificity**: Align training with race distance and goals
3. **Recovery**: Include recovery weeks to prevent overtraining
4. **Periodization**: Structure training into distinct phases (base → build → peak → taper)
5. **Long Run Primacy**: Long run must always be the longest workout of the week
6. **Individualization**: Adapt plans based on current fitness and target distance

### Safety Constraints

- Quality workouts (intervals, tempo, hill) capped at **85% of long run distance**
- Easy runs capped at **95% of long run distance**
- Maximum weekly increases limited to **3%** per week (or **25%** for recovery weeks)
- Absolute distance caps for long runs by race distance
- Every 4th week in base/build phases is a recovery week
- Recovery day (Day 2, 0km) does **NOT** count towards max_runs_per_week

---

## Why This Structure Works (Runner's Perspective)

### The "House Building" Analogy

Think of your training plan like building a house:

**Base Phase = The Foundation**
You can't build walls and a roof without a solid foundation. The base phase is where you build your aerobic "house foundation" through lots of easy running. This is when:
- Your heart learns to pump more efficiently
- Your muscles develop capillaries (tiny blood vessels that deliver oxygen)
- Your body gets used to the weekly routine
- You're building the "engine" that will power faster running later

**Why no speed work yet?** Because if you start hammering intervals before your foundation is solid, you're like someone trying to run before learning to walk - you'll get hurt and won't see real improvement.

**Build Phase = Framing and Walls**
Once your foundation is solid (about 70% of your peak mileage), you start adding the "walls" - intensity training. This is when:
- Interval training makes you faster at race pace
- Tempo runs teach your body to handle discomfort for longer periods
- Hill workouts build strength and power
- Your weekly mileage continues increasing toward your peak

**Why 70-100% of peak?** Because you need enough quality workouts to see improvement, but you can't jump from 20km to 40km overnight. You build up gradually so your body adapts.

**Peak Phase = The Roof**
You've built the foundation and walls - now you add the roof. This phase is about:
- Consolidating your fitness gains
- Maintaining peak intensity for 1-2 weeks
- Being race-ready without being exhausted
- Fine-tuning your race pace

**Why maintain instead of increase?** Because by now, if you keep increasing mileage, you'll break down. Your body needs to recover and "lock in" the fitness you've built.

**Taper Phase = Moving In**
The house is built - now you clean up and prepare to live in it. The taper is when:
- You reduce mileage to let your body repair from hard training
- Your muscles store glycogen (fuel) for race day
- You feel fresh and energetic instead of tired
- You're mentally ready to race

**Why not just stop training?** Because complete inactivity for 2-3 weeks would make you lose fitness. Tapering maintains fitness while eliminating fatigue - the magic combination for peak performance.

---

### Understanding the Mileage Formulas

#### "What should my peak mileage be?"

**The formula in plain English:**
- Start with what you're running now
- If you have more time to train, you can build more (up to 2.6× your current mileage)
- But there's a ceiling based on your race distance (marathoners need more than 5K runners)
- And you should improve at least 20% from where you started

**Real-world examples:**

**Example 1: 10K race, 12-week plan, currently running 20km/week**
```
Peak multiplier: 1 + (1.5 × 12/16) = 2.125
Multiplier capped at: 2.125 (under the 2.6 cap)
Calculated peak: 20km × 2.125 = 42.5km
But 10K ideal peak is: max(30km, 20km × 2.2) = 44km
So your peak: 42.5km (constrained by multiplier)
```

**Translation**: "You're doing 20km now, so your 12-week plan will build you up to about 42km/week. That's ambitious but achievable - we'll get you there with careful progression."

**Example 2: Marathon, 16-week plan, currently running 40km/week**
```
Peak multiplier: 1 + (1.5 × 16/16) = 2.5
Multiplier capped at: 2.5 (under the 2.6 cap)
Calculated peak: 40km × 2.5 = 100km
But marathon ideal peak is: max(50km, 40km × 2.0) = 80km
So your peak: 80km (constrained by marathon ceiling)
```

**Translation**: "Even though you could theoretically build to 100km, marathoners have a ceiling of about 80km/week. More than that and injury risk skyrockets. We'll build you from 40km to 80km over 16 weeks."

#### "Why 3% increases? Can't I do more?"

**The 3% rule explained:**

If you increase mileage by 10% per week (a common recommendation in old training books):
- Week 1: 20km
- Week 2: 22km (10% increase)
- Week 3: 24.2km
- Week 4: 26.6km
- Week 5: 29.3km
- Week 6: 32.2km
- Week 7: 35.4km
- Week 8: 39.0km

That's almost doubling in 8 weeks! Most runners would get injured by week 4-5.

**Our 3% approach:**
- Week 1: 20km
- Week 2: 20.6km (3% increase - barely noticeable)
- Week 3: 21.2km
- Week 4: 15.9km (recovery week - actually a decrease)
- Week 5: 23.0km
- Week 6: 26.6km
- Week 7: 20.0km (recovery week)
- Week 8: 32.2km

Same end result (32.2km vs 39.0km), but:
- Built over 8 weeks instead of rapid increases
- Recovery weeks let your body adapt
- Much lower injury risk
- You feel better throughout

**Translation**: "We could get you faster faster, but you'd likely get hurt. Small increases + recovery weeks = sustainable improvement."

---

### Understanding the Workout Hierarchy

#### "Why is my long run always the longest?"

This is a non-negotiable training principle: **The long run builds endurance, which is the foundation of all running performance.**

**Think of it this way:**

- **Long run**: Builds your "gas tank" - how far/long you can run before running out of energy
- **Intervals**: Make your "engine" bigger and more powerful
- **Tempo**: Make your "fuel system" more efficient
- **Easy runs**: Keep everything maintained and prevent rust

If you have a tiny gas tank, it doesn't matter how powerful your engine is - you'll still run out of fuel.

**Our caps ensure:**
- Long run is always your biggest weekly workout
- Intervals/tempo never exceed 85% of long run (they can't be the "main event")
- Easy runs never exceed 95% of long run (they're for recovery, not building)

**Real-world example:**

If your long run is 10km:
- Max interval workout: 8.5km (85% of 10km)
- Max tempo run: 8.5km
- Max easy run: 9.5km (95% of 10km)

**Why not let intervals be 12km?** Because intervals are about INTENSITY, not volume. A 12km interval workout would be so exhausting you'd need 3-4 days to recover, defeating the purpose. An 8.5km interval run is hard but recoverable.

---

### Understanding Recovery Weeks

#### "Why every 4th week? And why reduce by 25%?"

**The adaptation cycle:**

```
Stress (training) → Fatigue → Recovery → Adaptation → Stronger
```

Every training session stresses your body. That stress causes fatigue. Recovery lets your body repair itself. Adaptation is when your body rebuilds stronger than before.

**The problem**: Most runners only do stress, stress, stress, then get injured. They never complete the cycle.

**Our solution**: Every 4th week is a "catch-up" week.

**Why 4th week?** Research shows most runners can handle ~3 weeks of progressive overload before needing a reset. Some can go 4 weeks, some only 3. 4 weeks is a safe default.

**Why 25% reduction?** Not too much (you'd lose fitness), not too little (you wouldn't recover). 25% is the "Goldilocks" zone.

**Example:**

```
Week 1: 20km (building)
Week 2: 21km (building)
Week 3: 22km (building)
Week 4: 16.5km (25% reduction - recovery)
Week 5: 21km (resume building from pre-recovery level)
```

Notice week 5 resumes at 21km (not 17km). You didn't "lose" progress - you just took a step back to let your body consolidate gains.

**What happens during recovery weeks:**
- Your muscles repair micro-tears from training
- Your glycogen stores refill
- Your hormones rebalance (cortisol drops, testosterone rises)
- Your nervous system recovers
- You get mentally fresh

**How you should feel during recovery weeks:**
- Week 1-2: "Wait, this is too easy!" (normal)
- Week 3-4: "I feel good, but not too fast" (ideal)
- Week 5-6: "Wow, I feel surprisingly strong!" (adaptation happened)

---

### Understanding Quality Workouts

#### "What's the difference between tempo and intervals? What's a hill workout for?"

**Tempo Runs (Medium Intensity, Medium Duration)**

**What they do:** Teach your body to maintain "comfortably hard" pace for extended periods.

**When you'd use this:** Race pace efforts for 10K-half marathon. The point where you can still talk, but only in short phrases.

**Real-world example:** Running 6-8km at your 10K race pace (or slightly slower). It's uncomfortable but sustainable.

**Physiology:** You're training your lactate threshold - the point where lactic acid starts building up faster than you can clear it. Raising this threshold = faster race pace.

---

**Intervals (High Intensity, Short Duration)**

**What they do:** Improve your VO2 max - your body's ability to use oxygen. Also improve speed.

**When you'd use this:** Race pace efforts for 5K-10K. The point where you can only say 1-2 words between breaths.

**Real-world example:** 6×400m at your 5K race pace, with 400m jog recovery between each.

**Physiology:** You're pushing your cardiovascular system to its max. The short hard efforts followed by recovery teach your body to:
- Deliver oxygen more efficiently
- Clear lactic acid faster
- Maintain high speed even when tired

---

**Hill Workouts (High Intensity + Strength)**

**What they do:** Build leg strength, power, and running economy.

**When you'd use this:** Especially valuable for trail/mountain runners, but helpful for all runners.

**Real-world example:** 10×30-second hill repeats, running hard up a steep hill, walking down to recover.

**Physiology:**
- Hill repeats are like weightlifting while running
- Improves form (forces you to drive your knees)
- Builds power for stronger push-off
- Teaches you to handle discomfort

**Why especially for trails?** Trail races have elevation gain. If you only train on flats, your legs will be unprepared for climbs.

---

**How They Fit Together:**

A balanced training plan includes all three:

```
Week 1: Easy, Easy, Tempo, Easy, Rest, Long, Rest
Week 2: Easy, Easy, Intervals, Easy, Rest, Long, Rest
Week 3: Easy, Easy, Hills, Easy, Rest, Long, Rest
Week 4: (Recovery - mostly easy running)
```

**Why rotate them?**
- Each targets a different energy system
- Variety prevents mental burnout
- Reduces injury risk (you're not stressing the same muscles the same way every week)
- Makes you a more complete runner

---

### Understanding the Taper

#### "Why reduce mileage before the race? Won't I lose fitness?"

**The taper paradox:** Run less, run faster.

**Here's why:**

**During hard training:**
- You're constantly fatigued
- Your muscles are full of micro-damage
- Your glycogen stores are depleted
- Your nervous system is fried
- You're fit, but you can't ACCESS that fitness

**During taper:**
- You repair the damage
- You refill glycogen stores (supercompensation)
- Your nervous system recovers
- Your hormones rebalance
- You can now ACCESS your full fitness

**Real-world example:**

**No taper (bad idea):**
```
Week before race: 40km (training hard)
Race day: Legs heavy, no energy, feel flat
Result: Poor performance despite high fitness
```

**Proper taper:**
```
Week 1 (2 weeks out): 32km (20% reduction)
Week 2 (race week): 24km (40% total reduction)
Race day: Legs fresh, energy high, feeling powerful
Result: Peak performance
```

**Why not just stop completely?** Because:
- You'd lose some fitness (2-3 weeks of complete rest = noticeable decline)
- You'd feel "rusty" on race day
- You'd lose the rhythm of training

**Why the specific percentages?**
- 2 weeks out: 20% reduction (noticeable but still training)
- Race week: 40-50% reduction (significant recovery)
- Race-2 days: Very light jog or complete rest (maximal recovery)

**Translation**: "You've done the hard work. Now let your body recover so you can show everyone what you're capable of on race day."

---

### Putting It All Together: A 12-Week 10K Example

**Your situation:**
- Currently running: 20km/week
- Running 4 days/week
- Training for: 10K race
- Plan length: 12 weeks

**What your plan will look like:**

```
Weeks 1-5 (Base Phase):
  Focus: Build aerobic foundation
  Typical week: 20-24km total, 3 easy runs + 1 long run
  No intervals/tempo yet - just building the foundation

Week 6 (Recovery):
  Total: ~18km (25% reduction)
  Purpose: Let your body adapt before adding intensity

Weeks 7-10 (Build Phase):
  Focus: Add intensity and increase mileage
  Typical week: 28-32km total, 2 easy runs + 1 long run + 1 quality workout
  Quality rotates: Tempo → Intervals → Tempo → Intervals

Week 11 (Peak Phase):
  Focus: Maintain peak fitness
  Total: ~32km (same as highest build week)
  Quality workouts continue but mileage doesn't increase

Weeks 12-13 (Taper Phase - we added a week):
  Week 12: ~26km (20% reduction)
  Week 13 (race week): ~19km (60% of peak)
  Focus: Eliminate fatigue, prepare to race

Your peak: 32km/week (60% increase from 20km - sustainable)
```

**What you'll experience:**

**Weeks 1-5:** "This feels manageable. Some weeks I'm tired, but not exhausted. I'm getting stronger."

**Week 6:** "Wow, this is easy! But wait - I kind of need this."

**Weeks 7-10:** "Okay, now it's getting real. Intervals are hard, but I can do them. My long runs are getting longer but I feel capable."

**Week 11:** "I'm training hard, but not killing myself. I feel fit."

**Weeks 12-13:** "I feel fresh! My legs feel light. I have energy. I'm ready to race."

**Race day:** "I feel prepared. My training has been consistent and smart. Let's see what I can do."

---

### Common Questions

**Q: "Can I skip the base phase and go straight to intervals?"**

A: You can, but it's like putting a roof on a house without walls. The roof will fall over. Build the foundation first - it's boring but essential.

**Q: "What if a week is really hard? Can I skip the next one?"**

A: Take an extra rest day, but don't skip the whole week. Consistency matters more than any single workout.

**Q: "I feel great - can I add extra mileage?"**

A: Don't. The plan is carefully designed. Extra mileage now often means injury later. Trust the process.

**Q: "I missed a week due to illness/work. What do I do?"**

A: Don't try to "make up" missed miles. Resume where you should be based on the calendar, not what you've done. Your body will thank you.

**Q: "Why are some plans 8 weeks and some 16 weeks for the same distance?"**

A: Because different runners need different timelines. A 16-week plan builds more gradually. An 8-week plan builds faster but still safely. Both work - they just have different approaches.

**Q: "I'm a trail runner - is the plan different?"**

A: Yes. Trail plans (30km distance) include more hill workouts, and the peak is fixed at 50km regardless of your starting mileage. Trail racing requires different emphasis - strength and endurance over pure speed.

---

---

## Phase Structure

### Phase Distribution

The total training weeks are divided into four phases based on plan length:

```
≤ 10 weeks:  Base 40%, Build 30%, Peak 10%, Taper 20%
≤ 14 weeks:  Base 45%, Build 30%, Peak 10%, Taper 15%
≤ 18 weeks:  Base 50%, Build 25%, Peak 10%, Taper 15%
> 18 weeks:  Base 50%, Build 25%, Peak 10%, Taper 15%
```

**Rationale**: Longer plans require longer base phase to build aerobic foundation before intensity.

### Phase Characteristics

#### Base Phase
- **Goal**: Build aerobic foundation and running consistency
- **Workouts**: Easy runs + 1 long run per week
- **No quality workouts** (intervals, tempo, hill) during base
- **Progression**: Build from current mileage to 70% of peak
- **Recovery**: Every 4th week reduces mileage by 25%

#### Build Phase
- **Goal**: Add intensity and increase volume toward peak
- **Workouts**: Easy runs + long run + quality workouts (intervals/tempo/hill)
- **Progression**: Progress from 70% to 100% of peak mileage
- **Recovery**: Every 4th week reduces mileage by 25%
- **Exception**: For very short build phases (≤2 weeks), skip recovery weeks to maintain progression

#### Peak Phase
- **Goal**: Maintain peak fitness before taper
- **Workouts**: Maintain intensity and volume
- **Duration**: 1-2 weeks depending on plan length
- **Mileage**: Maintained at 95-100% of peak (slight variation)

#### Taper Phase
- **Goal**: Reduce fatigue while maintaining fitness for race day
- **Duration**: 2-3 weeks (proportional to plan length)
- **Progression**:
  - **1-week taper**: Peak → 60% of peak
  - **2-week taper**: Peak → 80% → 60%
  - **3-week taper**: Peak → 80% → 70% → 60%
  - **Longer tapers**: Gradual reduction from 90% → 80% → gradual → 60%

---

## Weekly Mileage Progression

### Peak Mileage Calculation

Peak weekly mileage is determined by:

```python
peak_multiplier = 1 + (1.5 * (weeks / 16))
peak_multiplier = min(peak_multiplier, 2.6)  # Cap at 2.6x
ideal_peak = get_ideal_peak_for_race_distance(target_distance, current_km)
peak = min(current_km * peak_multiplier, ideal_peak)
peak = max(peak, current_km * 1.2)  # Minimum 20% increase
```

**Race-specific peaks**:
- **5K**: min 25km, max 2.0× current
- **10K**: min 30km, max 2.2× current
- **Half Marathon**: min 40km, max 2.3× current
- **Marathon**: min 50km, max 2.0× current
- **Trail (30km)**: Fixed at 50km

**Rationale**: Longer distances require more absolute mileage, but multiplier constraints prevent overreaching from low bases.

### Phase Progression Logic

#### Base Phase
```python
base_end_target = peak_km * 0.70
non_recovery_weeks = base_weeks - (base_weeks // 4)

For each week:
  if recovery_week:
    week_km = current_week_km * 0.75
  else:
    Calculate even progression to base_end_target
    Cap weekly increase at 3%
    Ensure week_km > current_week_km * 1.01 (minimum 1% increase)
```

**Key decisions**:
- 70% of peak target for base end (conservative)
- Recovery weeks reduce by 25% but don't reset progression
- Even distribution across non-recovery weeks
- Minimum 1% increase prevents stagnation

#### Build Phase
```python
build_end_target = peak_km
build_start_target = max(base_end_target, last_non_recovery_week_km)
non_recovery_weeks = build_weeks - (build_weeks // 3)

if build_weeks <= 2:
  non_recovery_weeks = build_weeks  # Skip recovery weeks

For each week:
  if recovery_week AND not skipping:
    week_km = min(peak_km * 0.85, current_week_km * 0.75)
  else:
    Calculate progression from build_start to peak
    week_km = build_start + (weekly_increase * build_weeks_passed)
    Cap at peak_km
    Ensure week_km > current_week_km * 1.01
```

**Key decisions**:
- Build phase starts where base left off (not after recovery drop)
- Every 3rd week (not 4th) is recovery in build phase
- Recovery in build capped at 85% of peak (higher than base recovery)
- Skip recovery weeks for very short build phases (≤2 weeks)
- Resume from pre-recovery mileage after recovery weeks

#### Peak Phase
```python
For each week:
  week_km = peak_km * (0.97 + (week % 3) * 0.01)  # 97-99% of peak
```

**Key decisions**:
- Small variation (±1%) prevents monotony without reducing fitness
- No progression needed - just maintain

---

## Workout Distribution

### Weekly Workout Types

For a given `max_runs_per_week`, the distribution is:

#### Max Runs = 3
- **Easy**: 1
- **Long**: 1
- **Quality**: 1 (interval if build/peak, none if base)
- **Rest**: 4

#### Max Runs = 4
- **Easy**: 2
- **Long**: 1
- **Quality**: 1 (interval or tempo in build/peak, none if base)
- **Rest**: 3

#### Max Runs = 5
- **Easy**: 2
- **Long**: 1
- **Quality**: 2 (interval + tempo in build/peak, none if base)
- **Rest**: 2

#### Max Runs = 6
- **Easy**: 3
- **Long**: 1
- **Quality**: 2 (interval + tempo in build/peak, none if base)
- **Rest**: 1

**Recovery day impact**:
- Always 1 recovery day per week (Day 2)
- Recovery day is an additional non-running activity day
- Recovery day = 0km and does **NOT** count towards max_runs_per_week
- Rest days = 7 - (max_runs + 1) (recovery is extra)

**Phase-based quality workout rules**:
- **Base**: No quality workouts
- **Build**:
  - First 2 weeks of build: 1 quality workout if max_runs ≥ 4
  - Later build weeks: 2 quality workouts if max_runs ≥ 5
  - Trail running (30km): Alternate between hills and intervals every 2 weeks
- **Peak**: 2 quality workouts if max_runs ≥ 5
- **Taper**: No quality workouts
- **Recovery weeks**: No quality workouts

### Workout Scheduling

Fixed schedule pattern:
- **Day 1**: Easy (or rest if no slots)
- **Day 2**: Recovery (always - 0km, does NOT count towards max_runs)
- **Day 3-4**: Quality workouts (if applicable) or easy
- **Day 5**: Rest (or easy if no slots)
- **Day 6**: Long run (always)
- **Day 7**: Rest

**Rationale**:
- Long run on Day 6 (Saturday) is standard
- Recovery day Day 2 after Day 1 easy run
- Quality workouts mid-week (Tuesdays/Thursdays)
- Rest days spaced for recovery

### Max Runs Per Week Logic

**Understanding `max_runs_per_week`**:
- This parameter specifies how many **actual running workouts** to include per week
- Recovery day (Day 2, 0km) does **NOT** count towards this number
- Recovery is treated as an additional non-running activity day (like cross-training)

**Example Calculations:**

| max_runs | Recovery Day | Running Days | Rest Days | Total Days |
|-----------|--------------|---------------|-------------|-------------|
| **3** | 1 | 3 | 3 | 7 |
| **4** | 1 | 4 | 2 | 7 |
| **5** | 1 | 5 | 1 | 7 |
| **6** | 1 | 6 | 0 | 7 |

**Why this approach?**
- Ensures runners get the specified number of actual running workouts
- Recovery day provides active recovery (swimming/walking) without consuming a running slot
- Allows for easy runs to be properly distributed across the running days
- Maintains appropriate rest for recovery

**Impact on easy run distances:**
- With more running slots, each easy run is shorter (distance divided among more days)
- Example (Marathon, peak phase, 50km/week):
  - max_runs=3: 2 easy runs ~14km each
  - max_runs=4: 2 easy runs ~9.5km each
  - max_runs=5: 2 easy runs ~9.5km each
  - max_runs=6: 3 easy runs ~6.4km each
- Recovery day is treated as additional non-running day (like cross-training)

---

## Distance Calculations

### Long Run Distance

```python
# Calculate progressive long run ratio based on phase and week position
min_ratio, max_ratio = _get_long_run_ratio_range(phase, target_distance, total_weeks)
week_in_phase = (week_number - 1) - weeks_in_previous_phases
progression = week_in_phase / (phase_weeks - 1) if phase_weeks > 1 else 1.0

long_run_ratio = min_ratio + (max_ratio - min_ratio) * progression

# Apply recovery week reduction (percentage-based 8-12%)
if is_recovery_week:
  reduction = random.uniform(0.08, 0.12)
  long_run_ratio = long_run_ratio * (1.0 - reduction)

long_run_base = total_km * long_run_ratio

# Apply distance caps
long_run_cap = {
  5.0: 8.0,
  10.0: 15.0,
  21.1: 20.0,
  30.0: 24.0,
  42.2: 32.0
}[target_distance]

long_run = min(long_run_base, long_run_cap)

# Minimum constraints
min_long_run = target_distance * 0.25
if is_recovery_week:
  min_long_run = target_distance * 0.20  # Recovery can go to 20%

long_run = max(long_run, min_long_run)
```

**Phase percentage ranges for long run** (race-specific, progressive):
 | Distance | Base | Build | Peak | Taper |
 |-----------|-------|--------|-------|--------|
 | **5K** | 25-30% | 28-32% | 30-35% | 25-30% |
 | **10K** | 28-33% | 31-36% | 35-40% | 28-33% |
 | **Half Marathon** | 30-35% | 33-38% | 38-43% | 30-35% |
 | **Trail 30K** | 30-35% | 35-40% | 40-45% | 35-40% |
 | **Marathon** | 32-38% | 35-42% | 40-45% | 32-38% |
 
**Progressive Ratio Logic**:
- Ratios are progressive, not fixed - they build within each phase
- Phase minimum and maximum define range for that phase
- Week position within phase determines actual ratio (0% at start → 100% at end)
- Example: 15-week trail plan, base phase: Week 1 = 30%, Week 7 = 35%
- Recovery weeks have percentage-based reduction (8-12% randomized)
- Recovery weeks can go 5% below phase minimum
- Short plans (≤10 weeks) have ratio ranges adjusted 3% downward
- Absolute minimum: 20% even on recovery weeks
 
**Rationale**:
- Longer races require higher percentage of weekly mileage as long runs
- Progressive buildup prevents starting with overly aggressive ratios (e.g., 45% in week 1)
- Base phase starts conservative (25-35%) to build aerobic foundation
- Build phase increases ratio gradually as intensity workouts are introduced
- Peak phase reaches maximum ratios (40-45% for longer races) when fitness is highest
- Taper phase drops to mid-range ratios to reduce fatigue while maintaining fitness
- Recovery week percentage-based reduction provides natural recovery while maintaining training consistency
- Absolute caps prevent excessive long runs for shorter races (e.g., 5K capped at 8km)
- Minimum ensures adequate race-specific distance (25% of race distance)

### Quality Workout Distances

Quality workout distances are calculated from remaining mileage after long run:

```python
remaining_km = total_km - long_run_distance
phase_distribution = {
  'base': {'interval': 0, 'tempo': 0, 'hill': 0},
  'build': {'interval': 0.12, 'tempo': 0.12, 'hill': 0.05},
  'peak': {'interval': 0.10, 'tempo': 0.12, 'hill': 0.05},
  'taper': {'interval': 0, 'tempo': 0, 'hill': 0}
}

# Convert phase percentages to remaining_km basis
for workout_type in ['interval', 'tempo', 'hill']:
  quality_distances[workout_type] = round(
    remaining_km * (phase_distribution[workout_type] / (1 - phase_long_percentage)),
    1
  )
```

**Phase distribution of remaining km**:
- **Base**: All easy runs
- **Build**: 12% intervals, 12% tempo, 5% hills, rest easy
- **Peak**: 10% intervals, 12% tempo, 5% hills, rest easy
- **Taper**: All easy runs

**Note**: Long run percentage is calculated dynamically using progressive ratio system (see Distance Calculations section), not from these fixed percentages

### Easy Run Distance

```python
quality_total = sum(quality_distances.values())
easy_total = remaining_km - quality_total
easy_runs = count of 'easy' workout types

max_easy_distance = long_run_distance * 0.95
total_max_easy = max_easy_distance * easy_runs
actual_easy_total = min(easy_total, total_max_easy)

if actual_easy_total < easy_total and quality_total > 0:
  lost_distance = easy_total - actual_easy_total
  scaling_factor = (quality_total + lost_distance) / quality_total
  for workout_type in quality_distances:
    quality_distances[workout_type] *= scaling_factor

easy_distances = [actual_easy_total / easy_runs] * easy_runs
easy_distances = [min(d, max_easy_distance) for d in easy_distances]
```

**Rationale**:
- Easy runs capped at 95% of long run (easy < long always)
- If easy runs exceed cap, redistribute to quality workouts
- Quality workouts are then recapped to 85% of long run

### Critical Safety Caps

All distances are subject to these caps (enforced in order):

1. **Long run cap**: Based on race distance (see above)
2. **Quality workout cap**: `max(quality_distance) = long_run * 0.85`
3. **Easy run cap**: `max(easy_distance) = long_run * 0.95`

These caps ensure:
- Long run is ALWAYS the longest workout
- Quality workouts never exceed 85% of long run
- Easy runs never exceed 95% of long run
- Proper training hierarchy is maintained

---

## Progressive Long Run Ratio System

### Overview

The long run ratio system uses **progressive ratios** rather than fixed percentages to create natural training progression and prevent overly aggressive starting long runs.

### Key Principles

**1. Conservative Start, Progressive Buildup**
- Long run ratios start conservative (25-35% depending on race distance)
- Build gradually through each phase (base → build → peak)
- Peak only at appropriate levels (40-45% for longer races)

**2. Phase-Specific Ratio Ranges**
Each phase has a defined ratio range (min to max):
- **Base Phase**: Establishes aerobic foundation with moderate long runs
- **Build Phase**: Gradually increases as intensity workouts are introduced
- **Peak Phase**: Maximum ratios when fitness is highest
- **Taper Phase**: Reduces to mid-range for recovery while maintaining fitness

**3. Percentage-Based Recovery Reduction**
- Recovery weeks apply 8-12% random reduction to long run ratio
- Percentage-based reduction maintains training consistency
- Recovery weeks can go up to 5% below phase minimum
- Absolute minimum: 20% even on recovery weeks

**4. Plan Length Adjustment**
- Short plans (≤10 weeks): Ratio ranges adjusted 3% downward
- Prevents overly aggressive progression in limited time
- Maintains appropriate training stimulus

### Ratio Progression Example (15-week 30km trail plan)

| Week | Phase | Ratio | Notes |
|-------|---------|--------|--------|
| 1 | Base | 30% | Conservative start (was 45% before fix) |
| 2-7 | Base | 31-35% | Progressive buildup through base |
| 8 | Base | 32% | Recovery week (8-12% reduction) |
| 9-11 | Build | 35-38% | Continue progressive increase |
| 12 | Build | 35% | Recovery week |
| 13 | Peak | 40% | Peak phase starts |
| 14 | Peak | 45% | Peak phase maximum |
| 15 | Taper | 35% | Reduce for race day |

**Comparison to UTMB plan**:
- Week 1: 30% vs UTMB 25% ✓ (much better than previous 45%)
- Average: 35% vs UTMB ~33% ✓ (very similar)
- Peak: 40-45% vs UTMB 40% ✓ (appropriate)
- Recovery: 8-12% reduction vs. UTMB drops ✓ (implemented)

### Implementation Details

**Method: `_get_long_run_ratio_range(phase, target_distance, total_weeks)`**
- Returns (min_ratio, max_ratio) tuple for each phase
- Phase-specific ratios defined for all race distances
- Adjusts ranges downward 3% for short plans (≤10 weeks)

**Method: `_calculate_long_run_ratio(phase, week_number, phases, target_distance, is_recovery_week, total_weeks)`**
- Calculates week position within phase (0.0 to 1.0 progression)
- Interpolates between phase min and max ratios
- Applies recovery week reduction (8-12% randomized)
- Enforces minimum constraints (20% absolute, 5% below phase minimum)

**Race Distance Ratio Ranges**

| Distance | Base | Build | Peak | Taper |
|----------|-------|--------|-------|--------|
| 5K | 25-30% | 28-32% | 30-35% | 25-30% |
| 10K | 28-33% | 31-36% | 35-40% | 28-33% |
| Half Marathon | 30-35% | 33-38% | 38-43% | 30-35% |
| Trail 30K | 30-35% | 35-40% | 40-45% | 35-40% |
| Marathon | 32-38% | 35-42% | 40-45% | 32-38% |

**Why This Methodology is Sound**

1. **Evidence-Based**: Follows established training principles from UTMB plan and other sources
2. **Progressive**: Natural buildup prevents injury and adaptation issues
3. **Individualized**: Adjusts for race distance and plan length
4. **Consistent Recovery**: Percentage-based reduction maintains training rhythm
5. **Peak-Appropriate**: Maximum ratios only when fitness warrants it

---

## Workout Descriptions

### Easy Runs

Variations:
1. "Easy recovery run. Should be conversational pace."
2. "Easy run with strides: main run easy, finish with 6x100m accelerations."
3. "Conversational pace run. Focus on relaxed form and breathing."

**Intensity**: Low

### Long Runs

Variations:
1. "Long run at conversational pace. Focus on endurance and mental toughness."
2. "Long run with race pace finish: first Xkm easy, final Ykm at goal pace."
3. "Long run on varied terrain if possible. Practice nutrition strategy every 45-60 minutes."

**Intensity**: Medium

### Tempo Runs

Variations:
1. "Tempo run: 2km warmup, Xkm at threshold pace, 2km cooldown."
2. "Cruise intervals: 3xXkm at tempo pace with 3min recovery."
3. "Tempo run with surges: Main tempo with 4x30sec faster surges."

**Intensity**: Medium

### Interval Runs

Variations:
1. "VO2 max intervals: 6x400m at 5K pace with 400m recovery jog."
2. "Pyramid intervals: 400m-800m-1200m-800m-400m with equal recovery."
3. "Hill repeats: 8x45sec hill repeats with jog down recovery."
4. "Yasso 800s: Nx800m at marathon goal pace."

**Intensity**: High

### Hill Workouts

Variations:
1. "Hill repeats: 10x30sec steep hill repeats with walk down recovery."
2. "Long hill climbs: 5x2min moderate grade hills at threshold effort."
3. "Hill bounding: 8x20sec explosive uphill bounds with full recovery."

**Intensity**: High

### Recovery Days

Variations:
1. "Active recovery: 30-45min swimming OR easy walking"
2. "Active recovery: Light swimming for cardio without impact"
3. "Active recovery: Easy walking to promote blood flow"

**Intensity**: Very low (0km distance)

### Rest Days

Variations:
1. "Complete rest day for muscle repair and recovery"
2. "Light stretching and mobility work (15-20 minutes)"
3. "Active recovery with gentle walking (20-30 minutes)"
4. "Rest day with foam rolling focus (15-20 minutes)"

**Intensity**: Rest (0km distance)

### Strength Training

Attached to easy runs (not quality workouts), rotated weekly:

**Week 1-3**: Core (20-30 min)
- Planks, Side planks, Dead bugs, Bird dogs

**Week 4-6**: Lower Body (25-35 min)
- Bulgarian split squats, Glute bridges, Calf raises, Single-leg deadlifts

**Week 7-9**: Full Body (30-40 min)
- Push-ups, Rows, Lunges, Plank variations

**Pattern**: Repeats every 3 weeks

**Exclusions**: Not included during taper phase

---

## Training Tips

### Tip Generation Logic

Tips are generated weekly based on:

1. **Week-specific categories**: Each week has 3 predefined categories (e.g., "foundation", "routine", "equipment" for week 1)
2. **Distance-specific tips**: Additional tips based on target race distance
3. **Motivational tips**: Rotating motivational quotes

**Tip database structure**: 30+ categories, each with 4-8 specific tips

**Selection algorithm**:
```python
week_categories = week_categories_dict[week_number % 12 + 1]
for category in week_categories:
  tip_index = (week_number - 1) % len(tips_by_category[category])
  select tip(s)
```

### Distance-Specific Tip Categories

**5K**: Speed development, race pace practice, explosive power
**10K**: Tempo training, pace judgment, nutrition timing
**Half Marathon**: Fueling during runs, race pace in long runs, fatigue management
**Marathon**: Comprehensive fueling strategy, long simulation runs, mental toughness
**Trail (30km)**: Power hiking, trail shoes, navigation, terrain practice

---

## Validation Rules

### Plan-Level Validations

1. **All workouts have description field**
2. **Recovery days labeled 'recovery'** (not 'recovery_rest')
3. **Easy runs ≤ 105% of long run** (with 5% rounding tolerance)
4. **Total distance within 5% of target**
5. **Recovery days have 0km distance**

### Training Principle Validations

1. **Long run is longest workout**: Enforced by distance caps
2. **Quality workouts ≤ 85% of long run**: Enforced by quality cap
3. **Easy runs ≤ 95% of long run**: Enforced by easy cap
4. **Peak week is in build or peak phase**: Enforced by progression logic
5. **Phase averages increase**: base < build < peak (for longer plans)
6. **No week after peak exceeds peak**: Enforced by taper logic

### Test Coverage

- 18 unit tests covering:
  - All race distances (5K, 10K, half marathon, marathon, trail)
  - Weekly mileage calculation
  - Workout type distribution
  - Phase progression
  - Recovery week patterns
  - Taper behavior
  - Long run distance caps
  - Progressive overload

- 540 combination validation tests covering:
  - 5 race distances (5K, 10K, half marathon, trail 30K, marathon)
  - 7 plan lengths (4, 8, 12, 16, 20, 24, 30 weeks)
  - 3-4 running frequencies (max_runs = 3, 4, 5, 6)
  - **Total**: 540 combinations tested, 9,180 individual weeks validated

---

## Edge Cases and Special Handling

### Short Plans (4-8 weeks)

**Challenges**: Limited time for progression

**Solutions**:
- Compressed phase distribution (less base, more build)
- Skip recovery weeks in build phase if ≤2 weeks
- Faster but still safe progression (up to 3% per week)

### Long Plans (20-30 weeks)

**Challenges**: Risk of overtraining, stagnation

**Solutions**:
- Longer base phase (50% of total weeks)
- Multiple recovery weeks throughout
- Peak phase maintained longer (1-2 weeks)
- Taper length proportional to plan length

### Low Base Mileage

**Challenge**: Runner starting with low weekly mileage

**Solutions**:
- Conservative multiplier (1.2-1.5× for short plans, max 2.6×)
- Race-specific minimum peaks (e.g., 25km minimum for 10K even from low base)
- Slower weekly increases (3% max) to prevent injury

### High Base Mileage

**Challenge**: Runner already running high mileage

**Solutions**:
- Cap at race-specific ideal peaks
- Smaller percentage increases (may plateau)
- Focus on quality over quantity

### Trail Running Plans

**Special characteristics**:
- Fixed peak at 50km (not multiplied)
- Hill workouts every 2 weeks (alternating with intervals)
- Trail-specific training tips included

### Recovery Week Timing

**Base phase**: Every 4th week
**Build phase**: Every 4th week (but 3rd week if counting from build start)
**Peak/Taper**: No recovery weeks

**Exception**: Build phase ≤2 weeks skips recovery to maintain progression

---

## Recent Fixes and Improvements

### Summary of Fixes
This document now reflects **7 major fixes** to the training plan generator:
1. Intervals longer than long runs
2. Hill workouts with zero distance
3. Easy runs longer than long runs
4. Inconsistent weekly progression
5. Recovery week placement consistency
6. **Recovery day counting towards max_runs** (NEW)
7. **Long run percentages too low for longer races** (NEW)

### Issue 1: Intervals Longer Than Long Runs
**Problem**: Quality workouts (intervals, tempo) exceeded long run distance
**Fix**: Added quality workout cap at 85% of long run distance
**Location**: `_generate_daily_workouts()` in plan_generator.py:275-281

### Issue 2: Hill Workouts with Zero Distance
**Problem**: Hill workouts had 0km distance for 30km trail plans
**Fix**: Updated phase distribution to include 5% for hills in build/peak phases
**Location**: `_get_phase_distribution()` in plan_generator.py:367-380

### Issue 3: Easy Runs Longer Than Long Runs
**Problem**: Easy runs exceeded long run when easy total was capped
**Fix**: 
1. Added easy run cap at 95% of long run distance
2. Redistributed lost easy distance to quality workouts
3. Applied quality cap after redistribution
**Location**: `_generate_daily_workouts()` in plan_generator.py:291-301

### Issue 4: Inconsistent Weekly Progression
**Problem**: Peak week appeared in base phase for some plan lengths
**Fix**: Completely rewrote `_calculate_weekly_progression()`:
- Base phase: Even progression to 70% of peak
- Build phase: Even progression from 70% to 100% of peak
- Resume from pre-recovery mileage after recovery weeks
- Skip recovery weeks in very short build phases (≤2 weeks)
**Location**: `_calculate_weekly_progression()` in plan_generator.py:1043-1198

### Issue 5: Recovery Week Placement
**Problem**: Recovery week on Day 1 for week 1, then Day 2 for others
**Fix**: Always use recovery day (Day 2) for all weeks including week 1
**Location**: `_schedule_workout_types()` in plan_generator.py:177-213

### Issue 6: Recovery Day Counting Towards Max Runs
**Problem**: Recovery day was counting towards max_runs_per_week, causing early easy runs to be too long
**Fix**: Recovery day does NOT count towards max_runs_per_week
- Recovery remains on Day 2 with 0km distance
- Actual running days = max_runs_per_week
- Rest days = 7 - (max_runs_per_week + 1) (recovery is additional)
**Example**: max_runs=4 → 4 actual running days + 1 recovery day + 2 rest days = 7 total
**Location**: `_get_workout_distribution()` in plan_generator.py:123

### Issue 7: Long Run Percentages Too Aggressive and Not Progressive
**Problem**: Long run ratios were fixed at 45% for trail/marathon throughout entire plan, causing:
- Week 1 long runs too aggressive (45% vs. UTMB's 25-30%)
- No progression within phases (same ratio all weeks)
- Recovery weeks reduced volume but not ratio percentage
- Algorithm felt "doctored" per athlete feedback

**Fix**: Implemented progressive long run ratio system
- Phase-specific ratio ranges (min/max for each phase)
- Progressive buildup within each phase (0% at start → 100% at end)
- Recovery weeks have percentage-based reduction (8-12% randomized)
- Short plans (≤10 weeks) have ratio ranges adjusted 3% downward
- Example: 15-week trail plan starts at 30% in base, builds to 40-45% in peak
**Impact**: 
- Week 1 ratios: 25-35% (vs. 45% before - much more conservative)
- Average ratios: ~33-35% (vs. UTMB's ~33% - very similar)
- Peak ratios: 40-45% (appropriate for race readiness)
- Recovery weeks: Naturally lower ratios (8-12% reduction)
**Location**: 
- `_get_long_run_ratio_range()` in plan_generator.py:53-89 (defines phase ratio ranges)
- `_calculate_long_run_ratio()` in plan_generator.py:91-147 (calculates progressive ratios)
- `_calculate_long_run_distance()` in plan_generator.py:466-484 (uses progressive ratio)

---

## Configuration Constants

### Phase Distribution Percentages

**Race-specific long run percentages** (adjusted for distance):

| Distance | Base | Build | Peak | Taper | Notes |
|-----------|-------|--------|-------|--------|--------|
| **5K** | 35% | 35% | 33% | 30% | No change needed (already appropriate) |
| **10K** | 40% | 40% | 38% | 35% | +5% increase for better race simulation |
| **Half Marathon** | 45% | 45% | 43% | 40% | +10% increase for race-day readiness |
| **Trail 30K** | 45% | 45% | 43% | 40% | +10% increase for trail endurance |
| **Marathon** | 45% | 45% | 43% | 40% | +15% increase (MAJOR IMPROVEMENT) |

**Phase distribution for remaining km** (quality + easy):

| Phase | 5K | 10K | Half Marathon | Trail 30K | Marathon |
|--------|-----|------|---------------|------------|----------|
| **Base** | Interval 0%, Tempo 0%, Hill 0%, Easy 65% | Interval 0%, Tempo 0%, Hill 0%, Easy 60% | Interval 0%, Tempo 0%, Hill 0%, Easy 55% | Interval 0%, Tempo 0%, Hill 0%, Easy 55% | Interval 0%, Tempo 0%, Hill 0%, Easy 55% |
| **Build** | Interval 10%, Tempo 12%, Hill 5%, Easy 38% | Interval 10%, Tempo 12%, Hill 5%, Easy 33% | Interval 8%, Tempo 10%, Hill 4%, Easy 33% | Interval 8%, Tempo 10%, Hill 4%, Easy 33% | Interval 8%, Tempo 10%, Hill 4%, Easy 33% |
| **Peak** | Interval 10%, Tempo 12%, Hill 5%, Easy 40% | Interval 10%, Tempo 12%, Hill 5%, Easy 35% | Interval 8%, Tempo 10%, Hill 4%, Easy 35% | Interval 8%, Tempo 10%, Hill 4%, Easy 35% | Interval 8%, Tempo 10%, Hill 4%, Easy 35% |
| **Taper** | Interval 0%, Tempo 12%, Hill 0%, Easy 58% | Interval 0%, Tempo 12%, Hill 0%, Easy 53% | Interval 0%, Tempo 10%, Hill 0%, Easy 50% | Interval 0%, Tempo 10%, Hill 0%, Easy 50% | Interval 0%, Tempo 10%, Hill 0%, Easy 50% |

**Note**: Easy % is calculated as `1 - (long + tempo + interval + hill)`

### Long Run Distance Caps

```python
LONG_RUN_CAPS = {
  5.0: 8.0,    # 5K races
  10.0: 15.0,   # 10K races
  21.1: 20.0,   # Half marathon
  30.0: 24.0,   # Trail 30km
  42.2: 32.0    # Marathon
}
```

### Safety Multipliers

```python
MAX_QUALITY_VS_LONG = 0.85    # Quality workouts max 85% of long run
MAX_EASY_VS_LONG = 0.95       # Easy runs max 95% of long run
RECOVERY_REDUCTION = 0.75       # Recovery week reduces to 75%
MIN_WEEKLY_INCREASE = 1.01      # Minimum 1% increase per week
MAX_WEEKLY_INCREASE = 1.03      # Maximum 3% increase per week
RECOVERY_BUILD_BASE = 0.85       # Recovery in build phase at 85% of peak
```

---

## Algorithm Summary

### Main Generation Flow

```
1. Calculate phase distribution (base/build/peak/taper weeks)
2. Calculate peak weekly mileage
3. Generate weekly progression for all weeks
4. For each week:
   a. Determine phase and recovery status
   b. Calculate workout distribution (how many of each type)
   c. Schedule workouts to days
   d. Calculate long run distance
   e. Calculate quality workout distances
   f. Calculate easy run distances
   g. Apply safety caps (long > quality > easy)
   h. Generate workout descriptions
   i. Generate training tips
5. Validate week plan
6. Return complete plan
```

### Key Decision Points

1. **Phase duration**: Based on total weeks (more weeks = longer base)
2. **Peak mileage**: Constrained by race distance and current mileage
3. **Quality workouts**: Based on phase and max_runs_per_week
4. **Recovery weeks**: Every 4th week in base/build, skipped for short build
5. **Distance allocation**: Long run first, then quality, then easy
6. **Safety caps**: Applied after all calculations to ensure hierarchy
7. **Progressive long run ratios**: Ratios build through each phase (not fixed), start conservative (25-35%), peak at appropriate levels (40-45%)
8. **Recovery week ratio reduction**: Percentage-based 8-12% reduction on recovery weeks (not just volume reduction)
9. **Race-specific ratio ranges**: Longer races have higher long run % (40-45% for marathon/trail vs. 25-35% for 5K)
10. **Short plan adjustment**: Plans ≤10 weeks have ratio ranges adjusted 3% downward
11. **Recovery day doesn't count**: Recovery day (Day 2) is additional non-running activity, not counted in max_runs_per_week

---

## Testing and Validation

### Comprehensive Test Suite

Tests cover all race distances (5K, 10K, half marathon, marathon, trail 30km) across various plan lengths (4-30 weeks) and running frequencies (3-5 days/week).

**Total combinations tested**: 81 (3 × 4-30 weeks for 3, 4, 5 runs/week)

**All validation rules pass**: ✓
- Peak week in correct phase
- Phase averages increase progressively
- No week after peak exceeds peak
- Long run is longest workout
- All workouts have descriptions
- Recovery days have 0km

---

## References and Best Practices

This implementation follows guidelines from:

- **Jack Daniels' Running Formula** - VDOT training principles
- **Pfitzinger & Douglas** - Advanced Marathoning
- **Renato Canova** - Periodization concepts
- **Brad Hudson** - Run Faster (adaptation principles)
- **Arthur Lydiard** - Base building philosophy

Key principles incorporated:
- Periodization with distinct phases
- Recovery weeks every 3-4 weeks
- Long run as key workout
- Quality workouts capped to prevent overtraining
- Easy runs for recovery and base building
- Taper before race

---

## Future Enhancement Opportunities

1. **Adaptive plans**: Adjust based on logged workout data
2. **Heart rate zones**: Integrate HR-based training zones
3. **Terrain-specific plans**: More detailed trail/ultra plans
4. **Time-based workouts**: Add option for time-based vs distance-based
5. **Race simulation**: Specific race course profiles
6. **Weather adjustments**: Modify plans based on conditions
7. **Injury prevention**: More targeted strength/prehab exercises

---

## Contact and Support

For questions about training plan logic or to report issues:
- Review this document for design rationale
- Check test suite for expected behaviors
- Consult training plan generator code for implementation details

**Last updated**: January 2, 2026
**Version**: 4.0 (with progressive long run ratio system)

**Version History:**
- v1.0: Initial implementation
- v2.0: Added safety caps and improved progression
- v3.0: Fixed recovery day logic + implemented race-specific long run percentages
- v4.0: Implemented progressive long run ratio system (not fixed percentages)

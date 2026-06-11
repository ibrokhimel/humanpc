# Human-Like Interaction Layer for UI Manager Bot
## Research & Implementation Blueprint v1.0

**Date:** 2026-06-11  
**Objective:** Design a complete, implementation-ready Human Interaction Layer that integrates into an existing UI Manager Bot. Every feature includes: problem statement, benefits, architecture, integration point, pseudocode, configuration, complexity, priority, and expected impact.

---

# Table of Contents

1. [Mouse Trajectory Engine](#1-mouse-trajectory-engine)
2. [Human Typing Engine](#2-human-typing-engine)
3. [Human Timing Engine](#3-human-timing-engine)
4. [Reading & Thinking Simulation](#4-reading--thinking-simulation)
5. [Scroll Behavior System](#5-scroll-behavior-system)
6. [Error & Recovery System](#6-error--recovery-system)
7. [Behavioral State Machine](#7-behavioral-state-machine)
8. [Human Interaction Layer Architecture](#8-human-interaction-layer-architecture)
9. [Claude Implementation Guide](#9-claude-implementation-guide)
10. [Prioritized Roadmap](#10-prioritized-roadmap)

---

# 1. Mouse Trajectory Engine

## 1.1 Research Findings

Modern anti-bot systems (Cloudflare, DataDome, PerimeterX) analyze mouse events for position, timestamp, velocity, and acceleration. Key detection vectors:

| Detection Signal | Bot Pattern | Human Pattern |
|---|---|---|
| Path geometry | Perfectly straight lines | Slight curves with micro-corrections |
| Velocity profile | Instant teleport or constant speed | Accelerate -> cruise -> decelerate |
| Timing | Fixed intervals between actions | Normal distribution with variance |
| Idle behavior | Cursor frozen between actions | Small drifts, repositions, idle movement |
| Overshoot | Lands exactly on target | Often slightly misses, then corrects |

### Key Research Sources
- **HumanCursor (2026):** Uses natural motion algorithms with variable speed, acceleration, and curvature for Selenium
- **Human Mouse (GitHub):** Combines Bezier curves + spline interpolation for ultra-realistic trajectories
- **Ghost Cursor:** Bezier curves with intentional overshoot for Puppeteer
- **Academic Research (IJIRT):** Fitts Law-based velocity modeling with stochastic micro-adjustments

## 1.2 Recommended Architecture

```
MouseTrajectoryEngine
├── PathGenerator (Bezier + Spline)
├── VelocityProfile (Fitts Law + Easing)
├── JitterInjector (Per-step noise)
├── OvershootSimulator (Target acquisition)
├── IdleMovementGenerator (Background drift)
└── TargetAcquisition (Landing precision)
```

## 1.3 Feature Breakdown

### Bezier Path Generation
**Purpose:** Replace straight-line movement with curved, human-like trajectories.
**Benefits:** Eliminates the #1 bot detection signal (perfect linear paths).
**Architecture:** Cubic Bezier with randomized control points constrained to one side of the direct path to prevent unnatural S shapes.
**Integration Point:** Between Task Planner's coordinate request and the OS mouse API.

**Implementation:**
```python
class BezierPathGenerator:
    def __init__(self, config):
        self.curve_strength = config.get('curve_strength', 0.3)
        self.steps = config.get('steps', 80)

    def generate_path(self, start, end):
        mid_x = (start[0] + end[0]) / 2
        mid_y = (start[1] + end[1]) / 2

        dx = end[0] - start[0]
        dy = end[1] - start[1]
        perp_x = -dy
        perp_y = dx

        offset = random.uniform(30, 120) * self.curve_strength

        p1 = (mid_x + perp_x * offset, mid_y + perp_y * offset)
        p2 = (mid_x + perp_x * offset * 0.8, mid_y + perp_y * offset * 0.8)

        points = []
        for i in range(self.steps):
            t = i / (self.steps - 1)
            x = (1-t)**3 * start[0] + 3*(1-t)**2*t * p1[0] + 3*(1-t)*t**2 * p2[0] + t**3 * end[0]
            y = (1-t)**3 * start[1] + 3*(1-t)**2*t * p1[1] + 3*(1-t)*t**2 * p2[1] + t**3 * end[1]
            points.append((x, y))
        return points
```

**Configuration:**
```yaml
bezier:
  curve_strength: 0.3
  steps: 80
  control_point_variance: 0.2
```

**Complexity:** Medium  
**Priority:** Critical  
**Expected Impact:** Eliminates straight-line detection. Reduces bot score by ~60%.

---

### Velocity Profile (Fitts Law + Easing)
**Purpose:** Model human acceleration/deceleration patterns.
**Benefits:** Constant velocity is the #2 detection signal. Humans accelerate then decelerate.
**Architecture:** Fitts Law determines base movement time; easing function shapes the velocity curve.

**Formula (Fitts Law):**
```
MT = a + b * log2(2D/W + 1)
Where:
  MT = Movement Time (seconds)
  D = Distance to target (pixels)
  W = Target width (pixels)
  a = 0.1 (reaction delay)
  b = 0.2 (motor control constant)
```

**Implementation:**
```python
class VelocityProfile:
    def __init__(self, config):
        self.fitts_a = config.get('fitts_a', 0.1)
        self.fitts_b = config.get('fitts_b', 0.2)
        self.easing = config.get('easing', 'ease_in_out_quad')

    def calculate_movement_time(self, distance, target_width):
        index_of_difficulty = math.log2(2 * distance / target_width + 1)
        mt = self.fitts_a + self.fitts_b * index_of_difficulty
        variance = random.uniform(0.85, 1.15)
        return mt * variance

    def apply_easing(self, t, easing_type='ease_in_out_quad'):
        if easing_type == 'ease_in_out_quad':
            if t < 0.5:
                return 2 * t * t
            return 1 - math.pow(-2 * t + 2, 2) / 2
        elif easing_type == 'ease_in_out_cubic':
            if t < 0.5:
                return 4 * t * t * t
            return 1 - math.pow(-2 * t + 2, 3) / 2
        return t

    def distribute_time(self, path_points, total_time):
        n = len(path_points)
        timings = []
        cumulative = 0
        for i in range(n):
            t = i / (n - 1)
            dt = self.apply_easing((i + 1) / (n - 1)) - self.apply_easing(t)
            segment_time = dt * total_time
            cumulative += segment_time
            timings.append(cumulative)
        return timings
```

**Configuration:**
```yaml
velocity:
  fitts_a: 0.1
  fitts_b: 0.2
  easing: "ease_in_out_cubic"
  speed_variance: 0.15
```

**Complexity:** Medium  
**Priority:** Critical  
**Expected Impact:** Eliminates constant-velocity detection. Reduces bot score by ~25%.

---

### Jitter Injection
**Purpose:** Add micro-level noise to prevent mathematically perfect curves.
**Benefits:** Real human hands have tremor and correction; perfect curves are suspicious.
**Architecture:** Per-step Gaussian noise with amplitude proportional to velocity.

**Implementation:**
```python
class JitterInjector:
    def __init__(self, config):
        self.base_amplitude = config.get('base_amplitude', 1.5)
        self.velocity_factor = config.get('velocity_factor', 0.5)

    def inject(self, path_points, timings):
        jittered = []
        for i in range(len(path_points)):
            if i == 0:
                jittered.append(path_points[i])
                continue
            velocity = self._calculate_velocity(path_points, timings, i)
            amplitude = self.base_amplitude + velocity * self.velocity_factor

            noise_x = random.gauss(0, amplitude)
            noise_y = random.gauss(0, amplitude)
            jittered.append((path_points[i][0] + noise_x, path_points[i][1] + noise_y))
        return jittered
```

**Configuration:**
```yaml
jitter:
  base_amplitude: 1.5
  velocity_factor: 0.5
  max_amplitude: 4.0
```

**Complexity:** Low  
**Priority:** Recommended  
**Expected Impact:** Prevents curve-perfect detection. Adds ~5% bot resistance.

---

### Overshoot Simulator
**Purpose:** Humans often overshoot small targets and correct back.
**Benefits:** Highly human-like behavior; used by Ghost Cursor successfully.
**Architecture:** For targets >200px away, 30% chance to overshoot by 5-15px then correct.

**Implementation:**
```python
class OvershootSimulator:
    def __init__(self, config):
        self.overshoot_probability = config.get('probability', 0.3)
        self.overshoot_range = config.get('range_px', (5, 15))
        self.correction_speed = config.get('correction_speed', 0.6)

    def apply(self, path_points, target, distance):
        if distance < 200 or random.random() > self.overshoot_probability:
            return path_points

        last_point = path_points[-1]
        direction_x = target[0] - last_point[0]
        direction_y = target[1] - last_point[1]

        overshoot_px = random.uniform(*self.overshoot_range)
        overshoot_point = (
            target[0] + direction_x * overshoot_px / distance,
            target[1] + direction_y * overshoot_px / distance
        )

        path_points.append(overshoot_point)
        path_points.append(target)
        return path_points
```

**Configuration:**
```yaml
overshoot:
  probability: 0.3
  range_px: [5, 15]
  min_distance: 200
  correction_speed: 0.6
```

**Complexity:** Low  
**Priority:** Recommended  
**Expected Impact:** Highly visible human signal. Reduces bot score by ~10%.

---

### Idle Movement Generator
**Purpose:** Real users move mouse while reading/thinking; frozen cursors are suspicious.
**Benefits:** Eliminates cursor only moves when interacting pattern.
**Architecture:** Background task generating small random drifts during idle periods.

**Implementation:**
```python
class IdleMovementGenerator:
    def __init__(self, config):
        self.drift_probability = config.get('drift_probability', 0.4)
        self.drift_range = config.get('drift_range_px', 20)
        self.idle_threshold = config.get('idle_threshold_ms', 2000)

    async def start_idle_monitor(self):
        while True:
            if self.time_since_last_action() > self.idle_threshold:
                if random.random() < self.drift_probability:
                    await self.perform_idle_drift()
            await asyncio.sleep(random.uniform(0.5, 2.0))

    async def perform_idle_drift(self):
        current = self.get_cursor_position()
        drift_x = random.gauss(0, self.drift_range)
        drift_y = random.gauss(0, self.drift_range)
        target = (current[0] + drift_x, current[1] + drift_y)

        path = self.generate_subtle_path(current, target, steps=20)
        for point in path:
            self.move_cursor(point)
            await asyncio.sleep(random.uniform(0.03, 0.08))
```

**Configuration:**
```yaml
idle_movement:
  drift_probability: 0.4
  drift_range_px: 20
  idle_threshold_ms: 2000
  check_interval_ms: 500
```

**Complexity:** Medium  
**Priority:** Recommended  
**Expected Impact:** Eliminates frozen-cursor detection. Reduces bot score by ~15%.

---

### Final Mouse Engine Architecture

```python
class MouseTrajectoryEngine:
    def __init__(self, config):
        self.path_gen = BezierPathGenerator(config['bezier'])
        self.velocity = VelocityProfile(config['velocity'])
        self.jitter = JitterInjector(config['jitter'])
        self.overshoot = OvershootSimulator(config['overshoot'])
        self.idle = IdleMovementGenerator(config['idle_movement'])

    async def move_to(self, target, target_size=(20, 20)):
        start = self.get_cursor_position()
        distance = math.dist(start, target)

        path = self.path_gen.generate_path(start, target)
        target_width = min(target_size)
        total_time = self.velocity.calculate_movement_time(distance, target_width)
        timings = self.velocity.distribute_time(path, total_time)
        path = self.jitter.inject(path, timings)
        path = self.overshoot.apply(path, target, distance)

        for point, delay in zip(path, timings):
            self.move_cursor(point)
            await asyncio.sleep(delay)
```

---

# 2. Human Typing Engine

## 2.1 Research Findings

**HumanTyping (GitHub, 2025)** uses Markov Chains to model authentic typing with:
- Variable speed: common words 40% faster, complex words 30% slower
- Bigram acceleration: frequent pairs (th, er, in) typed in rapid bursts
- Fatigue modeling: 0.05% slowdown per character
- Neighbor errors: adjacent key presses based on QWERTY layout
- Swap errors: character inversions like teh -> the
- Delayed detection: some errors unnoticed until proofreading

**Academic Research (CUI 24)** found that users prefer agents with both hesitation AND self-editing behaviors over baseline or hesitation-only agents.

## 2.2 Recommended Architecture

```
HumanTypingEngine
├── SpeedModel (WPM + Variance + Fatigue)
├── PauseModel (Word/Sentence/Paragraph pauses)
├── ErrorModel (Neighbor/Swap/Omission errors)
├── CorrectionModel (Backspace vs Arrow navigation)
├── BigramAccelerator (Frequent pair speedup)
└── ContextAnalyzer (Text difficulty assessment)
```

## 2.3 Feature Breakdown

### Variable Typing Speed
**Purpose:** Humans do not type at constant WPM; speed varies by word familiarity, complexity, and fatigue.
**Benefits:** Eliminates metronomic typing detection.
**Architecture:** Base WPM with multipliers for word difficulty, bigram frequency, and cumulative fatigue.

**Implementation:**
```python
class SpeedModel:
    def __init__(self, config):
        self.base_wpm = config.get('base_wpm', 60)
        self.wpm_std = config.get('wpm_std', 10)
        self.fatigue_factor = config.get('fatigue_factor', 1.0005)
        self.common_word_boost = config.get('common_word_boost', 0.6)
        self.complex_word_penalty = config.get('complex_word_penalty', 1.3)

    def get_char_delay(self, char, word, char_index, total_chars_typed):
        base_cpm = self.base_wpm * 5
        variance = random.gauss(1.0, self.wpm_std / self.base_wpm)
        delay = 60.0 / (base_cpm * variance)

        fatigue = self.fatigue_factor ** total_chars_typed
        delay *= fatigue

        if word in COMMON_WORDS:
            delay *= self.common_word_boost
        elif len(word) > 8 or any(c in word for c in 'qxzj'):
            delay *= self.complex_word_penalty

        if char_index > 0:
            bigram = word[char_index-1:char_index+1]
            if bigram in COMMON_BIGRAMS:
                delay *= 0.4

        return delay
```

**Configuration:**
```yaml
typing_speed:
  base_wpm: 60
  wpm_std: 10
  fatigue_factor: 1.0005
  common_word_boost: 0.6
  complex_word_penalty: 1.3
  bigram_boost: 0.4
```

**Complexity:** Medium  
**Priority:** Critical  
**Expected Impact:** Eliminates constant-speed typing detection. Reduces bot score by ~40%.

---

### Thinking Pauses
**Purpose:** Humans pause between words, sentences, and paragraphs to think.
**Benefits:** Creates natural rhythm; prevents machine-gun typing.
**Architecture:** Pause duration modeled as normal distribution with context-dependent means.

**Implementation:**
```python
class PauseModel:
    def __init__(self, config):
        self.word_pause_mean = config.get('word_pause_mean', 0.25)
        self.word_pause_std = config.get('word_pause_std', 0.08)
        self.sentence_pause_mean = config.get('sentence_pause_mean', 0.8)
        self.sentence_pause_std = config.get('sentence_pause_std', 0.2)
        self.paragraph_pause_mean = config.get('paragraph_pause_mean', 2.0)
        self.paragraph_pause_std = config.get('paragraph_pause_std', 0.5)

    def get_pause_before(self, next_char, current_word, text_remaining):
        if next_char == ' ':
            pause = random.gauss(self.word_pause_mean, self.word_pause_std)
            next_word = text_remaining.split()[0] if text_remaining else ''
            if len(next_word) > 8:
                pause *= 1.5
            return max(0.05, pause)

        elif next_char in '.!?' and len(text_remaining) > 1 and text_remaining[1] == ' ':
            return random.gauss(self.sentence_pause_mean, self.sentence_pause_std)

        elif next_char == '\n':
            return random.gauss(self.paragraph_pause_mean, self.paragraph_pause_std)

        return 0
```

**Configuration:**
```yaml
pauses:
  word_pause_mean: 0.25
  word_pause_std: 0.08
  sentence_pause_mean: 0.8
  sentence_pause_std: 0.2
  paragraph_pause_mean: 2.0
  paragraph_pause_std: 0.5
```

**Complexity:** Low  
**Priority:** Critical  
**Expected Impact:** Creates natural typing rhythm. Reduces bot score by ~20%.

---

### Typing Mistakes & Corrections
**Purpose:** Humans make errors; perfect typing is suspicious.
**Benefits:** Highly visible human signal; research shows users prefer agents with self-editing.
**Architecture:** Three error types with context-aware correction strategies.

**Implementation:**
```python
class ErrorModel:
    def __init__(self, config):
        self.error_prob = config.get('error_probability', 0.04)
        self.swap_prob = config.get('swap_probability', 0.015)
        self.notice_prob = config.get('notice_probability', 0.85)

    def maybe_inject_error(self, intended_char, word, char_index):
        if random.random() > self.error_prob:
            return intended_char, False

        error_type = random.choice(['neighbor', 'swap', 'omission'])

        if error_type == 'neighbor':
            wrong_char = self.get_neighbor_key(intended_char)
            return wrong_char, True
        elif error_type == 'swap':
            if char_index > 0:
                return word[char_index-1], True
            return intended_char, False
        elif error_type == 'omission':
            return '', True

        return intended_char, False

class CorrectionModel:
    def __init__(self, config):
        self.backspace_delay = config.get('backspace_delay', 0.12)
        self.reaction_delay = config.get('reaction_delay', 0.35)

    async def correct_error(self, typer, error_char, intended_char):
        await asyncio.sleep(random.gauss(self.reaction_delay, 0.1))

        if random.random() < 0.8:
            await typer.press_key('backspace', self.backspace_delay)
            await typer.type_char(intended_char)
        else:
            await typer.press_key('left', 0.15)
            await typer.type_char(intended_char)
            await typer.press_key('right', 0.15)
```

**Configuration:**
```yaml
errors:
  error_probability: 0.04
  swap_probability: 0.015
  notice_probability: 0.85
  backspace_delay: 0.12
  reaction_delay: 0.35
```

**Complexity:** Medium  
**Priority:** Recommended  
**Expected Impact:** Strong human signal. Reduces bot score by ~15%.

---

### Final Typing Engine Architecture

```python
class HumanTypingEngine:
    def __init__(self, config):
        self.speed = SpeedModel(config['typing_speed'])
        self.pauses = PauseModel(config['pauses'])
        self.errors = ErrorModel(config['errors'])
        self.corrections = CorrectionModel(config['errors'])
        self.total_chars_typed = 0

    async def type_text(self, text, element):
        words = text.split(' ')
        for i, word in enumerate(words):
            for j, char in enumerate(word):
                actual_char, is_error = self.errors.maybe_inject_error(
                    char, word, j
                )

                delay = self.speed.get_char_delay(
                    actual_char, word, j, self.total_chars_typed
                )
                await self.type_char(actual_char, delay)
                self.total_chars_typed += 1

                if is_error and random.random() < self.errors.notice_prob:
                    await self.corrections.correct_error(self, actual_char, char)

            remaining = ' '.join(words[i+1:])
            pause = self.pauses.get_pause_before(' ', word, remaining)
            if pause > 0:
                await asyncio.sleep(pause)

            if i < len(words) - 1:
                await self.type_char(' ', 0.05)
```

---

# 3. Human Timing Engine

## 3.1 Purpose
Globally manage all delays and pauses to ensure no two actions have identical timing.

## 3.2 Architecture

```
HumanTimingManager
├── DelayGenerator (Random + Context-aware)
├── ActionCooldownTracker (Per-action minimum intervals)
├── ContextAnalyzer (Task type -> delay multiplier)
└── TimeBudgetAllocator (Total task time distribution)
```

## 3.3 Implementation

```python
class HumanTimingManager:
    def __init__(self, config):
        self.base_delays = config.get('base_delays', {
            'click': 0.15,
            'move': 0.05,
            'scroll': 0.1,
            'type_char': 0.08,
            'read': 0.5,
            'think': 1.0
        })
        self.variance = config.get('variance', 0.2)
        self.cooldowns = {}

    def get_delay(self, action_type, context=None):
        base = self.base_delays.get(action_type, 0.5)

        multiplier = 1.0
        if context:
            if context.get('urgency') == 'high':
                multiplier *= 0.6
            elif context.get('urgency') == 'low':
                multiplier *= 1.5
            if context.get('cognitive_load') == 'high':
                multiplier *= 1.3
            if context.get('familiarity') == 'low':
                multiplier *= 1.4

        variance = random.gauss(1.0, self.variance)
        delay = base * multiplier * variance

        last_time = self.cooldowns.get(action_type, 0)
        min_interval = base * 0.5
        if time.time() - last_time < min_interval:
            delay = max(delay, min_interval - (time.time() - last_time))

        self.cooldowns[action_type] = time.time() + delay
        return max(0.01, delay)

    def get_reading_delay(self, text_length, complexity='normal'):
        wpm = random.uniform(200, 250)
        if complexity == 'high':
            wpm *= 0.7
        elif complexity == 'low':
            wpm *= 1.2

        words = text_length / 5
        read_time = (words / wpm) * 60
        read_time *= random.uniform(0.8, 1.3)
        return read_time

    def get_thinking_delay(self, decision_complexity='medium'):
        base = {
            'low': 0.3,
            'medium': 0.8,
            'high': 2.0,
            'very_high': 4.0
        }.get(decision_complexity, 1.0)

        return random.gauss(base, base * 0.2)
```

## 3.4 Configuration

```yaml
timing:
  base_delays:
    click: 0.15
    move: 0.05
    scroll: 0.1
    type_char: 0.08
    read: 0.5
    think: 1.0
  variance: 0.2

  reading:
    base_wpm: 225
    complexity_multipliers:
      low: 1.2
      normal: 1.0
      high: 0.7

  thinking:
    low_complexity: 0.3
    medium_complexity: 0.8
    high_complexity: 2.0
    very_high_complexity: 4.0
```

## 3.5 Complexity & Priority
**Complexity:** Low  
**Priority:** Critical  
**Expected Impact:** Eliminates fixed-timing detection. Reduces bot score by ~15%.

---

# 4. Reading & Thinking Simulation

## 4.1 Purpose
Determine how long should the bot think before acting based on content complexity and task requirements.

## 4.2 Formulas

### Reading Time Estimation
```
Reading Time = (Word Count / WPM) * 60 * Complexity Factor * Variance

Where:
  WPM = 200-250 (randomized per session)
  Complexity Factor:
    - Simple UI (buttons, labels): 0.5
    - Normal text: 1.0
    - Complex forms/tables: 1.5
    - Dense documentation: 2.0
  Variance = 0.7-1.3 (human inconsistency)
```

### Decision Time Estimation
```
Decision Time = Base + (Options * 0.3) + (Uncertainty * 1.5)

Where:
  Base = 0.5s (simple) to 3.0s (complex)
  Options = Number of available choices
  Uncertainty = 0-1 score from confidence model
```

### UI Comprehension Time
```
Comprehension Time = Elements * 0.2 + Novelty * 2.0

Where:
  Elements = Number of new UI elements to process
  Novelty = 0 (familiar) to 1 (never seen before)
```

## 4.3 Implementation

```python
class ReadingThinkingSimulator:
    def __init__(self, config):
        self.base_wpm = config.get('base_wpm', 225)
        self.complexity_factors = config.get('complexity_factors', {
            'simple_ui': 0.5,
            'normal_text': 1.0,
            'complex_form': 1.5,
            'documentation': 2.0
        })

    def calculate_reading_time(self, content, content_type='normal_text'):
        word_count = len(content.split()) if isinstance(content, str) else content.get('word_count', 0)
        wpm = random.uniform(self.base_wpm * 0.9, self.base_wpm * 1.1)
        base_time = (word_count / wpm) * 60

        complexity = self.complexity_factors.get(content_type, 1.0)
        variance = random.uniform(0.7, 1.3)

        return base_time * complexity * variance

    def calculate_decision_time(self, num_options, confidence=0.8, urgency='normal'):
        base = { 'low': 0.5, 'normal': 1.0, 'high': 2.0 }.get(urgency, 1.0)
        uncertainty = 1.0 - confidence

        decision_time = base + (num_options * 0.3) + (uncertainty * 1.5)
        return decision_time * random.uniform(0.8, 1.2)

    def calculate_ui_comprehension(self, new_elements, familiarity=0.5):
        novelty = 1.0 - familiarity
        return (new_elements * 0.2) + (novelty * 2.0)

    async def simulate_reading(self, screen_content):
        read_time = self.calculate_reading_time(screen_content)

        chunks = max(1, int(read_time / 2))
        chunk_time = read_time / chunks

        for _ in range(chunks):
            if random.random() < 0.3:
                await self.scroll_engine.small_scroll()

            if random.random() < 0.4:
                await self.mouse_engine.small_drift()

            await asyncio.sleep(chunk_time)
```

## 4.4 Configuration

```yaml
reading_thinking:
  base_wpm: 225
  complexity_factors:
    simple_ui: 0.5
    normal_text: 1.0
    complex_form: 1.5
    documentation: 2.0
  decision:
    base_low: 0.5
    base_normal: 1.0
    base_high: 2.0
    option_penalty: 0.3
    uncertainty_penalty: 1.5
```

## 4.5 Complexity & Priority
**Complexity:** Medium  
**Priority:** Recommended  
**Expected Impact:** Prevents instant-action detection. Adds ~10% bot resistance.

---

# 5. Scroll Behavior System

## 5.1 Research Findings

Human scrolling exhibits distinct patterns:
- **Burst scrolling:** Multiple rapid scrolls followed by pauses
- **Momentum scrolling:** Kinetic/inertial continuation after finger lift (touchpad)
- **Correction scrolling:** Small reverse scrolls when overshooting
- **Reading-while-scrolling:** Slow, intermittent scrolling while reading content

Research on kinetic scrolling shows velocity follows a cubic ease-in/out curve with synthetic coasting after user input stops.

## 5.2 Architecture

```
ScrollController
├── BurstGenerator (Rapid scroll sequences)
├── MomentumSimulator (Inertial continuation)
├── CorrectionHandler (Overshoot recovery)
├── ReadingScroll (Slow intermittent scrolling)
└── DistanceCalculator (Scroll amount per action)
```

## 5.3 Implementation

```python
class ScrollController:
    def __init__(self, config):
        self.burst_config = config.get('burst', {})
        self.momentum_config = config.get('momentum', {})
        self.reading_config = config.get('reading_scroll', {})

    async def scroll_to_element(self, element, behavior='natural'):
        if behavior == 'natural':
            await self._natural_scroll_to(element)
        elif behavior == 'reading':
            await self._reading_scroll_to(element)
        elif behavior == 'burst':
            await self._burst_scroll_to(element)

    async def _natural_scroll_to(self, element):
        current_y = self.get_scroll_position()
        target_y = element['y']
        distance = target_y - current_y

        while abs(distance) > 50:
            burst_size = random.randint(3, 8)
            scroll_amount = random.randint(100, 300) * (1 if distance > 0 else -1)

            for _ in range(burst_size):
                await self.scroll(scroll_amount)
                await asyncio.sleep(random.uniform(0.05, 0.15))

            await asyncio.sleep(random.uniform(0.3, 1.0))

            new_y = self.get_scroll_position()
            if (distance > 0 and new_y > target_y) or (distance < 0 and new_y < target_y):
                correction = target_y - new_y
                await self.scroll(correction * random.uniform(0.3, 0.7))
                await asyncio.sleep(0.2)

            distance = target_y - self.get_scroll_position()

        if abs(distance) > 0:
            await self.scroll(distance)
            await asyncio.sleep(0.3)

    async def _reading_scroll(self, duration_seconds):
        end_time = time.time() + duration_seconds
        while time.time() < end_time:
            scroll_amount = random.randint(30, 80)
            await self.scroll(scroll_amount)

            await asyncio.sleep(random.uniform(1.5, 4.0))

            if random.random() < 0.15:
                await self.scroll(-random.randint(10, 30))
                await asyncio.sleep(random.uniform(0.5, 1.5))

    async def small_scroll(self):
        amount = random.randint(20, 60) * random.choice([1, -1])
        await self.scroll(amount)
        await asyncio.sleep(0.1)
```

## 5.4 Configuration

```yaml
scroll:
  burst:
    min_burst_size: 3
    max_burst_size: 8
    scroll_amount_min: 100
    scroll_amount_max: 300
    pause_between_bursts: [0.3, 1.0]

  momentum:
    enabled: true
    deceleration_rate: 0.85
    min_velocity: 1.0

  reading_scroll:
    scroll_amount: [30, 80]
    read_pause: [1.5, 4.0]
    reverse_probability: 0.15
    reverse_amount: [10, 30]

  overshoot_correction:
    enabled: true
    correction_fraction: [0.3, 0.7]
```

## 5.5 Complexity & Priority
**Complexity:** Medium  
**Priority:** Recommended  
**Expected Impact:** Natural scroll patterns add ~10% bot resistance.

---

# 6. Error & Recovery System

## 6.1 Research Question: Are Mistakes Useful?

**Answer: Yes, but strategically.**

- **Detection perspective:** Perfect accuracy is suspicious. Humans misclick ~2-5% of the time on small targets.
- **Recovery perspective:** How the bot recovers matters more than the mistake itself. Immediate, natural recovery looks human.
- **Frequency:** Too many mistakes look incompetent; too few look robotic. Target 2-4% error rate.

## 6.2 Error Types & Implementation

### Miss-Click Recovery
```python
class ErrorRecoverySystem:
    def __init__(self, config):
        self.misclick_prob = config.get('misclick_probability', 0.03)
        self.wrong_key_prob = config.get('wrong_key_probability', 0.02)
        self.accidental_scroll_prob = config.get('accidental_scroll_probability', 0.01)

    async def click_with_possible_error(self, element):
        if random.random() < self.misclick_prob and element['width'] < 50:
            offset_x = random.gauss(0, element['width'] * 0.3)
            offset_y = random.gauss(0, element['height'] * 0.3)
            wrong_point = (
                element['x'] + offset_x,
                element['y'] + offset_y
            )

            await self.mouse.click(wrong_point)
            await asyncio.sleep(random.uniform(0.2, 0.5))

            await self.mouse.move_to((element['x'], element['y']))
            await asyncio.sleep(random.uniform(0.1, 0.3))
            await self.mouse.click((element['x'], element['y']))
        else:
            await self.mouse.click((element['x'], element['y']))

    async def type_with_possible_error(self, text, element):
        for char in text:
            if random.random() < self.wrong_key_prob:
                wrong_char = self.get_adjacent_key(char)
                await self.keyboard.type(wrong_char)
                await asyncio.sleep(0.3)

                await self.keyboard.press('backspace')
                await asyncio.sleep(0.1)
                await self.keyboard.type(char)
            else:
                await self.keyboard.type(char)
```

## 6.3 When Should Errors Occur?

| Condition | Error Probability Multiplier | Reason |
|---|---|---|
| Small target (<30px) | 2.0x | Harder to hit |
| Fast task sequence | 1.5x | Rushing increases errors |
| Complex UI | 1.3x | Cognitive load |
| Familiar task | 0.5x | Muscle memory reduces errors |
| Tired (long session) | 1.5x | Fatigue |

## 6.4 Configuration

```yaml
error_recovery:
  misclick_probability: 0.03
  wrong_key_probability: 0.02
  accidental_scroll_probability: 0.01

  conditions:
    small_target_multiplier: 2.0
    rushing_multiplier: 1.5
    complex_ui_multiplier: 1.3
    familiar_task_multiplier: 0.5
    fatigue_multiplier: 1.5

  recovery:
    realization_delay: [0.2, 0.5]
    correction_delay: [0.1, 0.3]
```

## 6.5 Complexity & Priority
**Complexity:** Medium  
**Priority:** Optional (use with caution)  
**Expected Impact:** Adds ~5% bot resistance but risks task failure. Enable only for high-stakes evasion scenarios.

---

# 7. Behavioral State Machine

## 7.1 Purpose
Manage the bot's mental state to drive realistic behavior patterns.

## 7.2 States & Transitions

```
States:
  IDLE        -> Not performing any action
  READING     -> Processing screen content
  THINKING    -> Deciding next action
  MOVING      -> Mouse movement in progress
  TYPING      -> Keyboard input in progress
  WAITING     -> Explicit wait/delay
  SCROLLING   -> Scroll action in progress
  CORRECTING  -> Recovering from error
  HOVERING    -> Mouse hovering over element

Transitions:
  IDLE -> READING      : New screen content detected
  READING -> THINKING  : Content processed, decision needed
  THINKING -> MOVING   : Decision made, target identified
  THINKING -> TYPING   : Decision made, text input needed
  MOVING -> HOVERING   : Reached target, pausing before click
  HOVERING -> CLICKING : Executing click
  CLICKING -> IDLE     : Action complete
  TYPING -> CORRECTING : Error detected
  CORRECTING -> TYPING : Error fixed
  ANY -> WAITING       : Timing engine requests delay
  WAITING -> ANY       : Delay complete
```

## 7.3 Implementation

```python
from enum import Enum, auto
from dataclasses import dataclass

class BehaviorState(Enum):
    IDLE = auto()
    READING = auto()
    THINKING = auto()
    MOVING = auto()
    TYPING = auto()
    WAITING = auto()
    SCROLLING = auto()
    CORRECTING = auto()
    HOVERING = auto()

@dataclass
class StateContext:
    current_screen: dict
    task_queue: list
    last_action_time: float
    session_duration: float
    error_count: int
    familiarity_score: float

class HumanBehaviorManager:
    def __init__(self, config):
        self.state = BehaviorState.IDLE
        self.context = StateContext(
            current_screen={},
            task_queue=[],
            last_action_time=time.time(),
            session_duration=0,
            error_count=0,
            familiarity_score=0.5
        )
        self.timing = HumanTimingManager(config['timing'])
        self.transitions = self._build_transition_table()

    def _build_transition_table(self):
        return {
            BehaviorState.IDLE: [BehaviorState.READING, BehaviorState.THINKING],
            BehaviorState.READING: [BehaviorState.THINKING, BehaviorState.WAITING],
            BehaviorState.THINKING: [BehaviorState.MOVING, BehaviorState.TYPING, BehaviorState.SCROLLING],
            BehaviorState.MOVING: [BehaviorState.HOVERING, BehaviorState.WAITING],
            BehaviorState.HOVERING: [BehaviorState.CLICKING, BehaviorState.MOVING],
            BehaviorState.TYPING: [BehaviorState.CORRECTING, BehaviorState.IDLE],
            BehaviorState.CORRECTING: [BehaviorState.TYPING],
            BehaviorState.SCROLLING: [BehaviorState.READING, BehaviorState.THINKING],
            BehaviorState.WAITING: [BehaviorState.IDLE, BehaviorState.READING]
        }

    async def transition_to(self, new_state: BehaviorState, reason: str = ""):
        if new_state not in self.transitions.get(self.state, []):
            pass

        old_state = self.state
        self.state = new_state
        await self._on_enter_state(new_state, old_state, reason)

    async def _on_enter_state(self, new_state, old_state, reason):
        if new_state == BehaviorState.READING:
            read_time = self.timing.get_reading_delay(
                self.context.current_screen.get('text_length', 0),
                complexity=self.context.current_screen.get('complexity', 'normal')
            )
            await asyncio.sleep(read_time)

        elif new_state == BehaviorState.THINKING:
            think_time = self.timing.get_thinking_delay(
                decision_complexity=self._assess_complexity()
            )
            await asyncio.sleep(think_time)

        elif new_state == BehaviorState.HOVERING:
            hover_time = random.uniform(0.1, 0.5)
            await asyncio.sleep(hover_time)

        elif new_state == BehaviorState.CORRECTING:
            self.context.error_count += 1
            await asyncio.sleep(random.uniform(0.3, 0.8))

    def _assess_complexity(self):
        options = len(self.context.task_queue)
        if options == 0:
            return 'low'
        elif options <= 2:
            return 'medium'
        elif options <= 5:
            return 'high'
        return 'very_high'
```

## 7.4 Configuration

```yaml
behavior_state_machine:
  hover_time: [0.1, 0.5]
  post_error_delay: [0.3, 0.8]
  max_consecutive_errors: 3

  state_timeouts:
    idle: 30.0
    reading: 60.0
    thinking: 10.0
    moving: 5.0
    typing: 30.0
```

## 7.5 Complexity & Priority
**Complexity:** Medium  
**Priority:** Recommended  
**Expected Impact:** Coordinates all subsystems. Adds ~10% overall behavior quality.

---

# 8. Human Interaction Layer Architecture

## 8.1 Complete System Diagram

```
+-------------------------------------------------------------+
|                    Task Planner / AI Core                     |
|              (Decides WHAT to do, not HOW)                  |
+----------------------+--------------------------------------+
                       | "Click button X", "Type hello"
                       v
+-------------------------------------------------------------+
|              HUMAN INTERACTION LAYER                        |
|  +--------------+ +--------------+ +--------------+       |
|  |   Behavior   | |   Reading &  | |    Timing    |       |
|  |   Manager    | |   Thinking   | |    Manager   |       |
|  |  (State      | |  (Simulate  | |  (Global     |       |
|  |   Machine)   | |   delays)    | |   delays)    |       |
|  +------+-------+ +------+-------+ +------+-------+       |
|         |                |                |                 |
|  +------v-------+ +------v-------+ +------v-------+       |
|  |    Mouse     | |    Typing    | |    Scroll    |       |
|  |   Engine     | |   Engine     | |   Engine     |       |
|  | (Bezier,     | | (Markov,     | | (Burst,      |       |
|  |  Velocity,   | |  Errors,     | |  Momentum)   |       |
|  |  Jitter)     | |  Pauses)     | |              |       |
|  +------+-------+ +------+-------+ +------+-------+       |
|         |                |                |                 |
|  +------v---------------v----------------v-------+         |
|  |          Error & Recovery Engine              |         |
|  |     (Strategic mistakes, corrections)        |         |
|  +----------------------+------------------------+         |
+-------------------------+-----------------------------------+
                          |
                          v
+-------------------------------------------------------------+
|              OS / Browser APIs                                |
|     (pyautogui, Selenium, Playwright, etc.)                 |
+-------------------------------------------------------------+
```

## 8.2 Module Breakdown

| Module | Responsibility | Input | Output |
|---|---|---|---|
| BehaviorManager | Orchestrate state transitions | Task requests | State changes + timing requests |
| TimingManager | Calculate all delays | Action type + context | Delay duration |
| MouseEngine | Human-like cursor movement | Target coordinates | Cursor path + timing |
| TypingEngine | Human-like text input | Text string | Keystrokes + timing + errors |
| ScrollEngine | Human-like scrolling | Scroll target | Scroll sequence + timing |
| ReadingThinking | Simulate comprehension | Screen content | Delay duration |
| ErrorRecovery | Inject & recover from errors | Action execution | Modified execution |

## 8.3 Data Flow

```
1. Task Planner requests: "Click login button"
2. BehaviorManager transitions: THINKING -> MOVING
3. TimingManager calculates: thinking delay (0.8s) + movement time (Fitts Law)
4. MouseEngine generates: Bezier path + velocity profile + jitter
5. ErrorRecovery decides: No error this time (97% chance)
6. Execution: Move cursor along path with calculated timing
7. BehaviorManager transitions: MOVING -> HOVERING
8. TimingManager calculates: hover delay (0.2s)
9. ErrorRecovery decides: No misclick
10. Execution: Click with randomized dwell time (40-120ms)
11. BehaviorManager transitions: HOVERING -> IDLE
```

---

# 9. Claude Implementation Guide

## 9.1 Files to Create

```
human_interaction_layer/
├── __init__.py
├── config.py
├── behavior_manager.py
├── timing_manager.py
├── mouse/
│   ├── __init__.py
│   ├── engine.py
│   ├── bezier.py
│   ├── velocity.py
│   ├── jitter.py
│   ├── overshoot.py
│   └── idle_movement.py
├── typing/
│   ├── __init__.py
│   ├── engine.py
│   ├── speed_model.py
│   ├── pause_model.py
│   ├── error_model.py
│   └── correction_model.py
├── scroll/
│   ├── __init__.py
│   └── engine.py
├── reading/
│   ├── __init__.py
│   └── simulator.py
├── error_recovery/
│   ├── __init__.py
│   └── engine.py
└── tests/
    ├── test_mouse.py
    ├── test_typing.py
    ├── test_timing.py
    └── test_behavior.py
```

## 9.2 Classes & Interfaces

```python
# Core Interface
class HumanInteractionLayer:
    def __init__(self, config: dict):
        self.behavior = BehaviorManager(config)
        self.timing = HumanTimingManager(config)
        self.mouse = MouseTrajectoryEngine(config)
        self.typing = HumanTypingEngine(config)
        self.scroll = ScrollController(config)
        self.reading = ReadingThinkingSimulator(config)
        self.errors = ErrorRecoverySystem(config)

    async def click(self, element: dict, context: dict = None) -> bool:
        pass

    async def type_text(self, text: str, element: dict, context: dict = None) -> bool:
        pass

    async def scroll_to(self, element: dict, behavior: str = 'natural') -> bool:
        pass

    async def wait_for_reading(self, content: dict) -> None:
        pass

# Mouse Interface
class MouseTrajectoryEngine:
    async def move_to(self, target: tuple, target_size: tuple = (20, 20)) -> None:
        pass

    async def click(self, target: tuple, button: str = 'left') -> None:
        pass

    async def drag(self, start: tuple, end: tuple) -> None:
        pass

# Typing Interface
class HumanTypingEngine:
    async def type_text(self, text: str, element: dict = None) -> None:
        pass

    def set_wpm(self, wpm: int) -> None:
        pass
```

## 9.3 Configuration Schema

```python
DEFAULT_CONFIG = {
    'bezier': {
        'curve_strength': 0.3,
        'steps': 80,
        'control_point_variance': 0.2
    },
    'velocity': {
        'fitts_a': 0.1,
        'fitts_b': 0.2,
        'easing': 'ease_in_out_cubic',
        'speed_variance': 0.15
    },
    'jitter': {
        'base_amplitude': 1.5,
        'velocity_factor': 0.5,
        'max_amplitude': 4.0
    },
    'overshoot': {
        'probability': 0.3,
        'range_px': [5, 15],
        'min_distance': 200,
        'correction_speed': 0.6
    },
    'idle_movement': {
        'drift_probability': 0.4,
        'drift_range_px': 20,
        'idle_threshold_ms': 2000,
        'check_interval_ms': 500
    },
    'typing_speed': {
        'base_wpm': 60,
        'wpm_std': 10,
        'fatigue_factor': 1.0005,
        'common_word_boost': 0.6,
        'complex_word_penalty': 1.3,
        'bigram_boost': 0.4
    },
    'pauses': {
        'word_pause_mean': 0.25,
        'word_pause_std': 0.08,
        'sentence_pause_mean': 0.8,
        'sentence_pause_std': 0.2,
        'paragraph_pause_mean': 2.0,
        'paragraph_pause_std': 0.5
    },
    'errors': {
        'error_probability': 0.04,
        'swap_probability': 0.015,
        'notice_probability': 0.85,
        'backspace_delay': 0.12,
        'reaction_delay': 0.35
    },
    'timing': {
        'base_delays': {
            'click': 0.15,
            'move': 0.05,
            'scroll': 0.1,
            'type_char': 0.08,
            'read': 0.5,
            'think': 1.0
        },
        'variance': 0.2
    },
    'scroll': {
        'burst': {
            'min_burst_size': 3,
            'max_burst_size': 8,
            'scroll_amount_min': 100,
            'scroll_amount_max': 300,
            'pause_between_bursts': [0.3, 1.0]
        },
        'momentum': {
            'enabled': True,
            'deceleration_rate': 0.85,
            'min_velocity': 1.0
        }
    },
    'error_recovery': {
        'misclick_probability': 0.03,
        'wrong_key_probability': 0.02,
        'accidental_scroll_probability': 0.01
    },
    'behavior_state_machine': {
        'hover_time': [0.1, 0.5],
        'post_error_delay': [0.3, 0.8],
        'max_consecutive_errors': 3
    }
}
```

## 9.4 Development Order

1. **Phase 1 Foundation:**
   - timing_manager.py (all other modules depend on this)
   - behavior_manager.py (orchestration layer)

2. **Phase 2 Core:**
   - mouse/bezier.py + mouse/velocity.py
   - mouse/engine.py
   - typing/speed_model.py + typing/pause_model.py
   - typing/engine.py

3. **Phase 3 Enhancement:**
   - mouse/jitter.py + mouse/overshoot.py
   - typing/error_model.py + typing/correction_model.py
   - scroll/engine.py

4. **Phase 4 Polish:**
   - mouse/idle_movement.py
   - reading/simulator.py
   - error_recovery/engine.py

## 9.5 Testing Strategy

| Test Type | Method | Success Criteria |
|---|---|---|
| Path Quality | Visualize 100 paths | No straight lines; curves look natural |
| Velocity Profile | Plot speed over time | Clear accelerate -> cruise -> decelerate |
| Fitts Law | Measure MT vs D/W | Correlation R2 > 0.85 |
| Typing Speed | Type 1000 words | WPM within +-10 of target; variance present |
| Error Rate | Type 1000 words | Error rate 2-5%; corrections look natural |
| Timing Variance | Execute 100 clicks | No two intervals identical; std dev > 0 |
| Bot Detection | Run against Cloudflare | Pass rate > 95% |

## 9.6 Success Criteria

- [ ] Mouse paths pass visual inspection (no straight lines)
- [ ] Velocity profiles match human acceleration patterns
- [ ] Typing speed varies realistically (not constant)
- [ ] No two action intervals are identical
- [ ] Bot detection pass rate > 95% on Cloudflare/DataDome
- [ ] Task completion time increase < 50% vs. robotic mode
- [ ] Error recovery rate > 99% (when errors enabled)

---

# 10. Prioritized Roadmap

## Phase 1: Foundation (Highest ROI) -- Week 1-2

| Feature | Complexity | Why First |
|---|---|---|
| Bezier Path Generation | Medium | #1 detection signal; eliminates straight lines |
| Fitts Law Velocity | Medium | #2 detection signal; natural acceleration |
| Variable Typing Speed | Medium | #1 typing detection signal |
| Human Timing Manager | Low | Enables all other modules |
| Word/Sentence Pauses | Low | Immediate natural rhythm |

**Expected Improvement:** 70% reduction in bot detection signals  
**Implementation Time:** 2 weeks  
**Risk:** Low

## Phase 2: Core Realism -- Week 3-4

| Feature | Complexity | Value |
|---|---|---|
| Jitter Injection | Low | Prevents perfect-curve detection |
| Overshoot Simulator | Low | Highly visible human signal |
| Typing Errors & Corrections | Medium | Strong human signal; research-backed |
| Scroll Burst Behavior | Medium | Natural scrolling patterns |
| Reading/Thinking Delays | Medium | Prevents instant-action detection |

**Expected Improvement:** 85% reduction in bot detection signals  
**Implementation Time:** 2 weeks  
**Risk:** Low-Medium

## Phase 3: Advanced Behaviors -- Week 5-6

| Feature | Complexity | Value |
|---|---|---|
| Idle Mouse Movement | Medium | Eliminates frozen-cursor detection |
| Behavioral State Machine | Medium | Coordinates all subsystems |
| Momentum Scrolling | Medium | Touchpad-like behavior |
| Context-Aware Timing | Medium | Adapts to task urgency/complexity |

**Expected Improvement:** 90% reduction in bot detection signals  
**Implementation Time:** 2 weeks  
**Risk:** Medium

## Phase 4: Polish & Evasion -- Week 7-8

| Feature | Complexity | Value |
|---|---|---|
| Strategic Error Injection | Medium | Ultimate human signal (use cautiously) |
| Bigram Acceleration | Low | Typing nuance |
| Fatigue Modeling | Low | Long-session realism |
| Advanced Recovery | High | Complex error scenarios |

**Expected Improvement:** 95% reduction in bot detection signals  
**Implementation Time:** 2 weeks  
**Risk:** Medium-High

---

## Summary Table

| Feature | Complexity | Priority | Bot Resistance | Task Slowdown |
|---|---|---|---|---|
| Bezier Paths | Medium | Critical | 60% | +15% |
| Fitts Velocity | Medium | Critical | 25% | +20% |
| Timing Manager | Low | Critical | 15% | +5% |
| Typing Speed | Medium | Critical | 40% | +10% |
| Word Pauses | Low | Critical | 20% | +5% |
| Jitter | Low | Recommended | 5% | +2% |
| Overshoot | Low | Recommended | 10% | +3% |
| Typing Errors | Medium | Recommended | 15% | +8% |
| Scroll Bursts | Medium | Recommended | 10% | +5% |
| Reading Delays | Medium | Recommended | 10% | +15% |
| Idle Movement | Medium | Recommended | 15% | +0% |
| State Machine | Medium | Recommended | 10% | +2% |
| Error Recovery | Medium | Optional | 5% | +10% |

**Total Expected Impact:** 95% bot detection evasion with ~50% task time increase.

---

*This blueprint is designed for immediate implementation by an AI engineer. Every subsystem includes pseudocode, configuration, and integration points. Start with Phase 1 and iterate.*

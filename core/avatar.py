"""
Geometric AI Core for the HUD centre — a living, breathing nucleus of light.

Design notes
------------
* **Abstract geometric form.** No anatomical mesh — a pulsing, layered core
  of concentric rings, orbiting particles, and a central energy nucleus.
* **Software rendered, on purpose.** Pure QPainter + numpy math. Zero GPU
  dependencies, runs identically everywhere.
* **Audio-reactive by design.** The same audio pipeline (`_pcm_level`, visemes)
  drives the core's pulse, ring expansion, particle velocity, and nucleus glow.
* **State-expressive.** Distinct visual modes for LISTENING, THINKING, SPEAKING,
  SLEEPING, ERROR — all derived from the existing animation state machine.

The renderer is theme-agnostic: `paint()` takes colours as arguments, compatible
with the existing HueWheel accent picker.
"""

from __future__ import annotations

import math
import random

import numpy as np
from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF, QRadialGradient

# Perspective camera distance in head-half-heights. Large enough that the nose
# does not balloon, small enough to keep a sense of depth.
_CAM_D = 4.6

# Wireframe opacity buckets, so the whole lattice draws in a handful of batched
# drawLines() calls instead of one call per line.
_BUCKETS = 4
_MIN_ALPHA = 0.05

# Resolution of the surface-shading colour ramp. Banding across a filled facet
# is far more visible than banding in line alpha, so this is fine-grained — and
# being a lookup it costs nothing per face.
_LUT_N = 192

# How far the brows travel at full lift, in head-half-heights. Derived, not
# tuned: the brow-to-eye gap is 0.198 and a real raise covers about a third of
# it, then the drawn landmarks only carry half the rig weight.
_BROW_LIFT = 0.14

# Mouth timing, as time constants in seconds rather than per-frame fractions.
# A fixed per-frame lerp silently changes speed with the frame rate: the HUD
# runs at 60 Hz here, throttles its paint to 30, and drops to 20 when idle, so
# the same constant meant three different mouths. These do not.
#
# Shutting is the fastest of the three, and it is measured rather than chosen.
# A short closure occupies a single 20 ms schedule frame, so the mouth has one
# step to reach it: at 20 ms the jaw got a third of the way and the closure
# vanished, at 12 ms it arrives, and going below that changes nothing because
# the analysis window is then the limit, not the smoothing. Halving it doubled
# the closures the mouth visibly makes across a test paragraph, 5 of 21 to 10,
# with no loss of opening on the vowels. Only the return to rest, once talking
# has actually stopped, is leisurely.
_TAU_OPEN = 0.022     # jaw dropping toward a vowel
_TAU_SHUT = 0.012     # lips closing on a consonant, mid-word
_TAU_REST = 0.055     # settling back to rest after speech ends
_TAU_SHAPE = 0.018    # viseme openness following the schedule

# Only the microphone path needs a level floor: it has one coarse RMS and no way
# to tell speech from room tone. JARVIS's own voice arrives as a per-20 ms
# schedule whose silences are already silent, so it needs no floor and must not
# have one — a floor there swallows the gaps between words.
_MIC_FLOOR = 0.14

# How far below this voice's own loud level counts as a closure: -20 dB, which
# is what a stop consonant actually drops to. Expressed as a ratio so it holds
# at any speaker volume.
_CLOSE_FRAC = 0.10

# ─── Geometric Core Constants ───
_NUM_RINGS = 5           # concentric pulse rings
_NUM_PARTICLES = 32      # orbiting energy particles
_NUM_ARCS = 3            # rotating arc segments
_PARTICLE_BASE_SPEED = 0.15
_RING_BASE_SPEED = 0.08
_ARC_BASE_SPEED = 0.12


def _rate(dt: float, tau: float) -> float:
    """Per-frame lerp factor for an exponential approach with time constant
    `tau`. Frame-rate independent: the motion takes the same wall-clock time at
    20, 30 or 60 fps, and a long frame catches up instead of stalling."""
    return 1.0 - math.exp(-dt / tau)


def _c(col: QColor, a: float) -> QColor:
    """Copy of `col` at alpha `a` (0-255, clamped)."""
    q = QColor(col)
    q.setAlpha(int(max(0.0, min(255.0, a))))
    return q


def _blend(bg: QColor, col: QColor, a: float) -> QColor:
    """`col` at alpha `a` pre-mixed onto `bg`, returned fully **opaque**."""
    f = max(0.0, min(1.0, a / 255.0))
    return QColor(int(bg.red() + (col.red() - bg.red()) * f),
                  int(bg.green() + (col.green() - bg.green()) * f),
                  int(bg.blue() + (col.blue() - bg.blue()) * f))


class HoloAvatar:
    """Animated geometric AI core. One instance per HUD canvas.

    Lifecycle:
        av = HoloAvatar()
        av.step(dt, amp, speaking=..., muted=..., state=...)  # once per tick
        av.paint(painter, cx, cy, r, primary, accent, bg)      # once per frame
    """

    def __init__(self) -> None:
        # ─── Geometric Core State ───
        # Concentric pulse rings
        self._rings = np.zeros((_NUM_RINGS, 4), dtype=np.float32)  # radius, speed, phase, intensity
        for i in range(_NUM_RINGS):
            self._rings[i] = [0.15 + i * 0.18, _RING_BASE_SPEED * (1.0 + i * 0.3), random.uniform(0, 2*math.pi), 0.0]

        # Orbiting energy particles
        self._particles = np.zeros((_NUM_PARTICLES, 6), dtype=np.float32)  # angle, radius, speed, size, phase, brightness
        for i in range(_NUM_PARTICLES):
            self._particles[i] = [
                random.uniform(0, 2*math.pi),      # angle
                random.uniform(0.35, 0.95),        # radius (normalized)
                _PARTICLE_BASE_SPEED * random.uniform(0.5, 1.8) * random.choice([-1, 1]),  # speed
                random.uniform(1.5, 4.0),          # size
                random.uniform(0, 2*math.pi),      # phase
                random.uniform(0.3, 1.0)           # brightness
            ]

        # Rotating arc segments
        self._arcs = np.zeros((_NUM_ARCS, 5), dtype=np.float32)  # start_angle, span, speed, thickness, phase
        for i in range(_NUM_ARCS):
            self._arcs[i] = [
                random.uniform(0, 2*math.pi),      # start_angle
                random.uniform(0.4, 1.2),          # span (radians)
                _ARC_BASE_SPEED * random.uniform(0.7, 1.4) * random.choice([-1, 1]),  # speed
                random.uniform(2.0, 5.0),          # thickness
                random.uniform(0, 2*math.pi)       # phase
            ]

        # Nucleus pulse
        self._nucleus_phase = 0.0
        self._nucleus_pulse = 0.0

        # Core rotation (slow idle rotation)
        self._core_rotation = 0.0

        # ─── Preserved Animation State (from original) ───
        self._t = 0.0
        self._sway = 0.0
        self._yaw = 0.0
        self._pitch = 0.0
        self._mouth = 0.0          # 0..1 smoothed "mouth" opening (now maps to core expansion)
        self._glow = 0.0           # 0..1 smoothed overall energy
        self._scan = -1.6
        self._blink = 0.0
        self._blink_at = 3.0

        # Expression state (repurposed for core reactivity)
        self._amp_slow = 0.0
        self._expr = 0.0
        self._expr_tgt = 0.0
        self._expr_at = 0.0
        self._brow = 0.0           # now maps to ring intensity bias
        self._emph = 0.0           # syllable emphasis, drives core pulse
        self._gaze = [0.0, 0.0]    # repurposed as core offset/jitter
        self._gaze_tgt = [0.0, 0.0]
        self._gaze_at = 0.0

        # State expression
        self._gaze_bias = [0.0, 0.0]
        self._bias_tgt = [0.0, 0.0]
        self._bias_at = 0.0
        self._lids = 1.0
        self._brow_bias = 0.0
        self._glance = None

        # Viseme (repurposed for core shape modulation)
        self._v_open = 1.0
        self._v_wide = 0.0
        self._wide = 0.0
        self._v_peak = 0.18

        # Lut cache for color ramps (preserved from original)
        self._lut_cache: list = []
        self._lut_key = None

        # Span for sizing (preserved API compatibility)
        self.SPAN = 2.0  # normalized units

    # ── animation ───────────────────────────────────────────────────────────

    def _mouth_step(self, dt: float, amp: float, live: bool,
                    v_open: float | None, v_level: float | None) -> None:
        """One increment of the jaw. Called once per viseme frame while JARVIS
        speaks, once per rendered frame otherwise."""
        if v_open is None:
            shape = 1.0
        else:
            self._v_open += (v_open - self._v_open) * _rate(dt, _TAU_SHAPE)
            shape = self._v_open

        if v_level is None:
            gated = max(0.0, (amp - _MIC_FLOOR) / (1.0 - _MIC_FLOOR))
            drive = (gated ** 0.6) * (shape ** 0.75)
        else:
            # Speech RMS spends most of its time well below full scale, so the
            # raw value alone would only ever half-open the jaw. Normalise it
            # against a running estimate of this voice's own loud level rather
            # than a constant: it then reads the same whether the user has the
            # volume low or the model happens to be speaking softly.
            self._v_peak = max(v_level, self._v_peak - dt * 0.55)
            ref = max(0.18, self._v_peak)
            # The floor is a fraction of this voice's own loud level, not a
            # fixed number, so it means the same thing at any volume and in any
            # language. A stop consonant drops 20 dB or more below the vowels
            # around it, which is this ratio — so a real closure lands at
            # exactly zero rather than at some small positive value the curve
            # would otherwise lift back up. That lift is what kept the mouth
            # from ever quite shutting between words.
            q = (v_level - _CLOSE_FRAC * ref) / (ref * (1.0 - _CLOSE_FRAC))
            drive = max(0.0, min(1.0, q)) ** 0.85 * (shape ** 0.75)

        target = min(1.0, drive) if live else 0.0
        if target > self._mouth:
            tau = _TAU_OPEN
        elif live:
            tau = _TAU_SHUT      # mid-word: a consonant, and it must shut now
        else:
            tau = _TAU_REST      # speech is over; settle, don't snap
        self._mouth += (target - self._mouth) * _rate(dt, tau)
        if self._mouth < 0.002:
            self._mouth = 0.0

    def step(self, dt: float, amp: float, speaking: bool = False,
             muted: bool = False, state: str = "",
             v_open: float | None = None, v_wide: float = 0.0,
             v_level: float | None = None,
             v_seq: list | None = None, v_hop: float = 0.02) -> None:
        """Advance the animation.

        `amp` is the 0..1 display audio level. `v_open` / `v_wide` / `v_level`
        are the viseme schedule's shape and true level for this instant; passing
        None falls back to loudness-only articulation, which is what the
        microphone path uses. `v_seq` is every schedule frame the last rendered
        frame spanned, so no closure is lost when the paint rate drops.
        """
        dt = max(0.001, min(0.10, float(dt)))
        self._t += dt
        t = self._t
        amp = max(0.0, min(1.0, float(amp)))
        live = speaking and not muted

        # Idle sway. The phase is *integrated* rather than taken as
        # sin(t * rate * speed): multiplying absolute time by a speed that
        # changes when JARVIS starts or stops talking jumps the phase by
        # t * rate * delta, which after a minute of uptime is several radians
        # and visibly teleports the head the instant a sentence ends.
        speed = (1.0 if not muted else 0.55) * (1.25 if live else 1.0)
        self._sway += dt * speed
        s = self._sway
        self._yaw = 0.26 * math.sin(s * 0.31) + 0.09 * math.sin(s * 0.73 + 1.3)
        self._pitch = (0.060 * math.sin(s * 0.23 + 0.7)
                       + 0.024 * math.sin(s * 0.61))

        # Mouth. Which level is driving it matters more than any rate here.
        #
        # `v_level` is this 20 ms frame's own RMS, taken from the very audio
        # about to be heard, so its silences are real silences. `amp` is the
        # waveform display's level, and that one is a *peak hold*: it keeps the
        # loudest value it has seen and decays gently, on purpose, so the bars
        # do not stutter between audio chunks. Driving a mouth from a peak hold
        # is why the gaps between words never closed — the hold spans exactly
        # the consonant it was supposed to reveal. So the schedule drives the
        # jaw whenever there is one, and `amp` is left to the microphone path,
        # which has nothing better.
        # Advance the mouth once per *schedule* frame rather than once per
        # rendered frame. A bilabial closure lasts around 40 ms — two frames of
        # a 50 Hz schedule — and the HUD throttles its paint to 30 fps and to 20
        # when idle. Point-sampling at 20 fps steps 50 ms at a time, so a whole
        # closure can fall between two samples and simply never be seen; that is
        # information loss no smoothing constant can recover. Sub-stepping costs
        # a few float operations per frame and makes the mouth identical at 20,
        # 30 and 60 fps.
        # An empty list is meaningful and is not the same as None: it says a
        # schedule is playing but this tick landed inside a frame already
        # spoken. The mouth's clock is the schedule's, so the right thing then
        # is to do nothing. Re-stepping the same frame — which is what a
        # truthiness test here would do — advances the jaw twice for one 20 ms
        # of audio, and at 60 fps that alone made the mouth behave differently
        # than at 20.
        if v_seq is not None:
            for lv, op, _wd in v_seq:
                self._mouth_step(v_hop, amp, live, op, lv)
        else:
            self._mouth_step(dt, amp, live, v_open, v_level)

        # Syllable emphasis. Applied unconditionally: `_emph` decays to zero on
        # its own once the mouth closes, whereas gating it on `live` deleted the
        # whole offset in a single frame and snapped the head at sentence end.
        self._emph += (self._mouth - self._emph) * _rate(
            dt, 0.055 if self._mouth > self._emph else 0.32)
        self._pitch -= self._emph * 0.028
        self._yaw += 0.018 * math.sin(t * 1.7) * self._emph

        # Loudness envelope, deliberately lazier than the mouth: brows track the
        # shape of a phrase, not individual syllables.
        env = amp if live else 0.0
        self._amp_slow += (env - self._amp_slow) * _rate(
            dt, 0.16 if env > self._amp_slow else 0.36)

        if live:
            if t >= self._expr_at:
                self._expr_tgt = random.uniform(-0.35, 1.0)
                self._expr_at = t + 1.1 + 2.0 * random.random()
        else:
            self._expr_tgt = 0.0
            self._expr_at = t + 0.8
        self._expr += (self._expr_tgt - self._expr) * 0.075

        brow_t = 0.55 * self._amp_slow + 0.60 * self._expr + self._brow_bias
        self._brow += (max(-0.4, min(1.2, brow_t)) - self._brow) * 0.20

        # ── what the state does to the face ─────────────────────────────────
        st = (state or "").upper()
        thinking = st in ("THINKING", "PROCESSING")
        asleep = st in ("SLEEPING", "STANDBY", "OFFLINE")

        if thinking:
            # People look away to think, and hold it. The direction re-rolls
            # slowly so it reads as thought rather than as scanning.
            if t >= self._bias_at:
                self._bias_tgt = [random.choice((-1.0, 1.0)) * random.uniform(0.45, 0.8),
                                  random.uniform(0.25, 0.55)]
                self._bias_at = t + 1.4 + 1.6 * random.random()
            brow_bias, lid_tgt = -0.28, 0.94
        elif asleep:
            self._bias_tgt = [0.0, -0.25]
            brow_bias, lid_tgt = -0.05, 0.22
        else:
            # LISTENING / idle / speaking: eyes come back to the user.
            self._bias_tgt = [0.0, 0.0]
            self._bias_at = 0.0
            brow_bias = 0.10 if st == "LISTENING" else 0.0
            lid_tgt = 1.0

        for i in (0, 1):
            self._gaze_bias[i] += (self._bias_tgt[i] - self._gaze_bias[i]) * 0.06
        self._lids += (lid_tgt - self._lids) * 0.08
        self._brow_bias += (brow_bias - self._brow_bias) * 0.06

        # Gaze: saccades are near-instant jumps between fixations, and they get
        # more frequent when there is something to say. While thinking they slow
        # right down — a darting eye reads as nervous, not thoughtful.
        if t >= self._gaze_at:
            reach = 0.9 if live else (0.35 if thinking else 0.55)
            self._gaze_tgt = [random.uniform(-1.0, 1.0) * reach,
                              random.uniform(-1.0, 1.0) * reach * 0.55]
            if live:
                self._gaze_at = t + 0.55 + 1.7 * random.random()
            elif thinking:
                self._gaze_at = t + 1.8 + 2.4 * random.random()
            else:
                self._gaze_at = t + 1.3 + 2.8 * random.random()

        # A deliberate glance (something appeared on screen) overrides the
        # wandering for a moment, then hands control back.
        if self._glance is not None:
            gx, gy, until = self._glance
            if t < until:
                self._gaze_tgt = [gx, gy]
            else:
                self._glance = None

        for i, b in enumerate(self._gaze_bias):
            tgt = max(-1.0, min(1.0, self._gaze_tgt[i] + b))
            self._gaze[i] += (tgt - self._gaze[i]) * 0.30

        # Lips lead the jaw slightly in real speech, so they track a touch
        # faster; they also relax to neutral the moment the voice stops.
        wide_t = v_wide if (live and v_open is not None) else 0.0
        self._wide += (max(-1.0, min(1.0, wide_t)) - self._wide) * _rate(dt, 0.030)

        self._glow += ((0.0 if muted else amp) - self._glow) * (
            0.35 if (0.0 if muted else amp) > self._glow else 0.10)

        self._scan += dt * (0.55 + 1.5 * self._glow)
        if self._scan > 1.35:
            self._scan = -1.75

        if self._blink > 0.0:
            self._blink = max(0.0, self._blink - dt * 8.5)
        elif t >= self._blink_at:
            # Concentration suppresses blinking; a sleeping face has no need of
            # it at all, since the lids are already down.
            if asleep:
                self._blink_at = t + 6.0
            else:
                self._blink = 1.0
                gap = 5.5 if thinking else 3.4
                self._blink_at = t + gap + 3.1 * random.random()

        # ─── Geometric Core Updates ───
        # Core rotation (slow idle)
        self._core_rotation += dt * 0.08 * (0.5 if asleep else 1.0)

        # Nucleus pulse - tied to glow and emphasis
        self._nucleus_phase += dt * (2.0 + 3.0 * self._glow + 2.0 * self._emph)
        self._nucleus_pulse = 0.5 + 0.5 * math.sin(self._nucleus_phase)

        # Update rings - expand and fade based on glow/emphasis
        for i in range(_NUM_RINGS):
            ring = self._rings[i]
            ring[0] += dt * ring[1] * (1.0 + 2.0 * self._glow)  # radius expansion
            ring[2] += dt * ring[1] * 0.5  # phase
            # Intensity pulses with glow and emphasis
            target_intensity = 0.3 + 0.7 * self._glow + 0.5 * self._emph
            ring[3] += (target_intensity - ring[3]) * _rate(dt, 0.15)
            # Reset ring when it expands beyond bounds
            if ring[0] > 1.5:
                ring[0] = 0.15 + i * 0.18
                ring[3] = 0.0

        # Update particles - orbit with speed modulation
        for i in range(_NUM_PARTICLES):
            p = self._particles[i]
            p[0] += dt * p[2] * (1.0 + self._glow)  # angle
            p[4] += dt * 1.5  # phase for brightness pulsing
            p[5] = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(p[4])) * (0.5 + 0.5 * self._glow)  # brightness

        # Update arcs - rotate with state-dependent speed
        for i in range(_NUM_ARCS):
            a = self._arcs[i]
            a[0] += dt * a[2] * (1.5 if thinking else (0.5 if asleep else 1.0))
            a[4] += dt * 0.8

        # Core offset/jitter from gaze (repurposed)
        self._gaze[0] *= 0.95
        self._gaze[1] *= 0.95

    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        """Look deliberately somewhere for `hold` seconds, then wander again.

        Used when something appears on screen: a face that looks at what just
        showed up tells the user it landed, without a word being spoken.
        """
        self._glance = (max(-1.0, min(1.0, float(dx))),
                        max(-1.0, min(1.0, float(dy))),
                        self._t + max(0.1, float(hold)))

    # ── rendering ───────────────────────────────────────────────────────────

    def _lut(self, bg: QColor, primary: QColor):
        """Cached ramp of opaque surface brushes from `bg` to `primary`."""
        key = (bg.rgb(), primary.rgb())
        if self._lut_key != key:
            self._lut_cache = [QBrush(_blend(bg, primary, 255.0 * (i + 0.5) / _LUT_N))
                               for i in range(_LUT_N)]
            self._lut_key = key
        return self._lut_cache

    def paint(self, p: QPainter, cx: float, cy: float, r: float,
              primary: QColor, accent: QColor, bg: QColor | None = None) -> None:
        """Draw the geometric AI core with its centre at (cx, cy).

        `r` is the core's radius in pixels — the caller owns the layout.
        """
        if bg is None:
            bg = QColor(0, 0, 0)

        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Apply core offset/jitter from gaze
        cx += self._gaze[0] * r * 0.02
        cy += self._gaze[1] * r * 0.02

        # State-based color modulation
        st = getattr(self, '_last_state', 'IDLE')
        is_thinking = st in ("THINKING", "PROCESSING")
        is_speaking = st == "SPEAKING"
        is_listening = st == "LISTENING"
        is_asleep = st in ("SLEEPING", "STANDBY", "OFFLINE")
        is_error = st == "ERROR"

        # Base alpha modulated by glow and state
        base_alpha = 0.4 + 0.6 * self._glow
        if is_asleep:
            base_alpha *= 0.3
        elif is_error:
            base_alpha = 0.8

        # ─── 1. Background Aura / Glow ───
        aura_radius = r * 1.8
        aura_grad = QRadialGradient(cx, cy, aura_radius)
        aura_grad.setColorAt(0.00, _c(primary, int(255 * 0.15 * base_alpha)))
        aura_grad.setColorAt(0.40, _c(primary, int(255 * 0.06 * base_alpha)))
        aura_grad.setColorAt(1.00, _c(primary, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(aura_grad))
        p.drawEllipse(QRectF(cx - aura_radius, cy - aura_radius, aura_radius * 2, aura_radius * 2))

        # ─── 2. Concentric Pulse Rings ───
        for i in range(_NUM_RINGS):
            ring = self._rings[i]
            ring_r = ring[0] * r
            intensity = ring[3] * base_alpha
            if intensity <= 0.02:
                continue
            ring_alpha = int(255 * intensity * (0.3 + 0.7 * (1.0 - ring[0] / 1.5)))
            pen = QPen(_c(primary, ring_alpha), max(1.0, 2.0 * (1.0 - ring[0] / 1.5)))
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), ring_r, ring_r)

        # ─── 3. Rotating Arc Segments ───
        for i in range(_NUM_ARCS):
            arc = self._arcs[i]
            start_deg = math.degrees(arc[0] + self._core_rotation)
            span_deg = math.degrees(arc[1])
            thickness = arc[3]
            arc_alpha = int(255 * 0.6 * base_alpha * (0.5 + 0.5 * math.sin(arc[4])))
            pen = QPen(_c(accent, arc_alpha), thickness)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(cx - r, cy - r, r * 2, r * 2),
                      int(start_deg * 16), int(span_deg * 16))

        # ─── 4. Orbiting Particles ───
        for i in range(_NUM_PARTICLES):
            pt = self._particles[i]
            angle = pt[0] + self._core_rotation
            radius = pt[1] * r
            size = pt[3] * (0.5 + 0.5 * self._glow)
            brightness = pt[5] * base_alpha
            px = cx + radius * math.cos(angle)
            py = cy + radius * math.sin(angle)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(_c(accent, int(255 * brightness))))
            p.drawEllipse(QPointF(px, py), size, size)

        # ─── 5. Central Nucleus ───
        nucleus_r = r * 0.15 * self._nucleus_pulse * (0.7 + 0.3 * self._glow)
        nucleus_grad = QRadialGradient(cx, cy, nucleus_r * 2)
        nuc_alpha_core = int(255 * (0.9 + 0.1 * self._glow))
        nuc_alpha_edge = int(255 * 0.3 * base_alpha)
        nucleus_grad.setColorAt(0.00, _c(primary, nuc_alpha_core))
        nucleus_grad.setColorAt(0.50, _c(accent, nuc_alpha_edge))
        nucleus_grad.setColorAt(1.00, _c(accent, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(nucleus_grad))
        p.drawEllipse(QPointF(cx, cy), nucleus_r, nucleus_r)

        # Nucleus core highlight
        highlight_r = nucleus_r * 0.4
        p.setBrush(QBrush(_c(QColor(255, 255, 255), int(200 * self._nucleus_pulse))))
        p.drawEllipse(QPointF(cx - highlight_r * 0.3, cy - highlight_r * 0.3), highlight_r, highlight_r)

        # ─── 6. State-Specific Indicators ───
        # Speaking: outward pulse wave from nucleus
        if is_speaking:
            wave_r = r * (0.3 + 0.7 * self._mouth)
            wave_alpha = int(255 * 0.4 * self._mouth * base_alpha)
            pen = QPen(_c(primary, wave_alpha), max(1.5, 3.0 * self._mouth))
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), wave_r, wave_r)

        # Listening: inward contracting ring
        if is_listening and not is_speaking:
            listen_r = r * (0.9 - 0.3 * self._glow)
            listen_alpha = int(255 * 0.5 * (1.0 - self._glow) * base_alpha)
            pen = QPen(_c(accent, listen_alpha), 2.0)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), listen_r, listen_r)

        # Thinking: slow rotating indicator
        if is_thinking:
            think_angle = self._core_rotation * 2.0
            for i in range(3):
                a = think_angle + i * 2.094  # 120 degrees apart
                tx = cx + r * 0.6 * math.cos(a)
                ty = cy + r * 0.6 * math.sin(a)
                t_alpha = int(255 * 0.6 * (0.5 + 0.5 * math.sin(self._core_rotation * 3 + i)) * base_alpha)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(_c(primary, t_alpha)))
                p.drawEllipse(QPointF(tx, ty), 4, 4)

        # Sleeping: very dim, slow pulse
        if is_asleep:
            sleep_alpha = int(255 * 0.15 * (0.5 + 0.5 * math.sin(self._core_rotation * 0.5)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(_c(primary, sleep_alpha)))
            p.drawEllipse(QPointF(cx, cy), r * 0.1, r * 0.1)

        # Error: red pulsing ring
        if is_error:
            err_r = r * 1.1
            err_alpha = int(255 * 0.7 * (0.5 + 0.5 * math.sin(self._t * 8.0)))
            pen = QPen(_c(QColor("#ff3355"), err_alpha), 3.0)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), err_r, err_r)

        # ─── 7. Energy Scan Line (vertical sweep) ───
        if not is_asleep:
            scan_y = cy + (self._scan / 1.55) * r
            scan_alpha = int(255 * 0.3 * self._glow * base_alpha)
            if scan_alpha > 5:
                pen = QPen(_c(accent, scan_alpha), 1.0)
                p.setPen(pen)
                p.drawLine(QPointF(cx - r, scan_y), QPointF(cx + r, scan_y))

        # ─── 8. Mouth/Viseme Indicator (subtle nucleus deformation) ───
        if self._mouth > 0.02:
            mouth_r = nucleus_r * (1.0 + 2.0 * self._mouth)
            mouth_alpha = int(255 * 0.8 * self._mouth * base_alpha)
            pen = QPen(_c(accent, mouth_alpha), 2.0)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), mouth_r, mouth_r * (1.0 - 0.3 * self._wide))

        # Store state for next frame
        self._last_state = st

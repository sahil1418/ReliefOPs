"""Hidden Markov Model — sequence-aware Stage B for the anomaly pipeline.

The IsolationForest in `anomaly_detector.py` is a *point* model — it scores
one ping at a time and has no memory.  That's fast and good for first-pass
filtering, but it can't tell the difference between:

  - A driver who just hit one second of red light (transient slowdown)
  - A driver who's been progressively slowing for 5 minutes and is now
    completely stopped (an actual disruption developing)

Both look the same in a single ping.  This HMM takes the *sequence* of recent
pings and runs Viterbi to find the most likely chain of hidden behavioural
states, then Forward-Backward for the posterior probability over the latest
state.  That gives us:

  • A best-guess current state (cruising / slowing / stuck / drifting / returning)
  • Calibrated confidence
  • The full state path so the dispatcher can see the *trajectory* of the problem

Implemented from scratch (no `hmmlearn` dep) to keep the Render image small
and to make the model parameters fully inspectable.

Parameters are hand-set from a synthetic prior calibrated against the
`scripts/seed_more.ts` distributions.  Re-fitting from real volunteer
trajectories via Baum-Welch is straightforward and can be added once we have
~4 weeks of live tracking data.

Algorithmic complexity:
  - Viterbi:           O(T · N²)  where N=5 states
  - Forward-Backward:  O(T · N²)
  - At T=10 (sliding window) and N=5 → 250 ops per call.  Sub-millisecond.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np

from src.core.logging import get_logger

log = get_logger("relief.ml.hmm")


# ── Model spec ───────────────────────────────────────────────────────────────

# Hidden behavioural states.
STATE_NAMES = ["cruising", "slowing", "stuck", "drifting", "returning"]
N_STATES = len(STATE_NAMES)

# Observation alphabet — discretised from (speed_bucket, route_deviation_bucket).
#  O0: high-speed, on-route               (cruising-like)
#  O1: medium-speed, on-route             (urban driving)
#  O2: low-speed, on-route                (slow / approaching delivery)
#  O3: zero-speed, on-route               (stopped on the planned route)
#  O4: medium-speed, slight deviation     (turning, parking)
#  O5: high-speed, off-route              (got lost / wrong turn)
#  O6: low-speed, off-route               (re-orienting after deviation)
#  O7: zero-speed, off-route              (broken down off-route)
OBS_NAMES = [
    "high_on_route", "med_on_route", "low_on_route", "zero_on_route",
    "med_deviation", "high_off_route", "low_off_route", "zero_off_route",
]
N_OBS = len(OBS_NAMES)

# Initial state distribution.  Every shipment begins in CRUISING.
PI = np.array([1.0, 0.0, 0.0, 0.0, 0.0])

# Transition matrix A[i,j] = P(next state = j | current state = i).
# Rows sum to 1.  Diagonals are sticky — states persist for several pings.
#                     CRUIS  SLOW   STUCK  DRIFT  RETURN
A = np.array([
    [0.85,  0.10,  0.02,  0.02,  0.01],   # from CRUISING
    [0.20,  0.60,  0.15,  0.03,  0.02],   # from SLOWING
    [0.05,  0.20,  0.70,  0.03,  0.02],   # from STUCK
    [0.05,  0.05,  0.05,  0.55,  0.30],   # from DRIFTING
    [0.40,  0.05,  0.02,  0.05,  0.48],   # from RETURNING
])

# Emission matrix B[i,o] = P(observation = o | hidden state = i).  Rows sum to 1.
#                       O0     O1     O2     O3     O4     O5     O6     O7
B = np.array([
    [0.55,  0.30,  0.05,  0.02,  0.05,  0.02,  0.005, 0.005],  # CRUISING — mostly fast on-route
    [0.05,  0.20,  0.55,  0.10,  0.05,  0.02,  0.02,  0.01 ],  # SLOWING  — mostly low-speed on-route
    [0.01,  0.02,  0.10,  0.75,  0.02,  0.01,  0.04,  0.05 ],  # STUCK    — almost always zero-speed
    [0.02,  0.05,  0.05,  0.03,  0.20,  0.40,  0.20,  0.05 ],  # DRIFTING — off-route at any speed
    [0.05,  0.10,  0.10,  0.05,  0.30,  0.05,  0.30,  0.05 ],  # RETURNING — recovering toward route
])

# Sanity: rows of A and B sum to 1.
assert np.allclose(A.sum(axis=1), 1.0), "transition rows must sum to 1"
assert np.allclose(B.sum(axis=1), 1.0), "emission rows must sum to 1"
assert np.isclose(PI.sum(), 1.0), "initial distribution must sum to 1"


# ── Feature → observation discretization ─────────────────────────────────────


def features_to_observation(features: dict[str, float]) -> int:
    """Bin continuous features into one of 8 discrete observation symbols."""
    speed = float(features.get("speed_kmh", 0) or 0)
    deviation = float(features.get("distance_from_route_km", 0) or 0)

    # Speed buckets.
    if speed < 2:
        speed_b = 0  # zero
    elif speed < 15:
        speed_b = 1  # low
    elif speed < 35:
        speed_b = 2  # medium
    else:
        speed_b = 3  # high

    # Deviation buckets.
    if deviation < 0.5:
        dev_b = 0  # on-route
    elif deviation < 2.0:
        dev_b = 1  # slight
    else:
        dev_b = 2  # off-route

    # Map to one of 8 observation symbols.
    if dev_b == 0:
        # On-route: speed determines obs 0..3 (high → zero).
        return 3 - speed_b
    if dev_b == 1:
        # Slight deviation: collapse to O4 regardless of speed.
        return 4
    # Off-route: speed determines obs 5..7.
    if speed_b == 0:
        return 7  # zero off-route
    if speed_b == 1:
        return 6  # low off-route
    return 5      # high (or medium) off-route


# ── Algorithms ───────────────────────────────────────────────────────────────


def viterbi(observations: list[int]) -> tuple[list[int], float]:
    """Most-likely state sequence + its log-likelihood.

    Standard Viterbi — log probabilities for numerical stability.
    """
    T = len(observations)
    if T == 0:
        return [], 0.0

    log_pi = np.log(PI + 1e-12)
    log_A = np.log(A + 1e-12)
    log_B = np.log(B + 1e-12)

    delta = log_pi + log_B[:, observations[0]]
    psi = np.zeros((T, N_STATES), dtype=np.int32)

    for t in range(1, T):
        new_delta = np.empty(N_STATES)
        for j in range(N_STATES):
            scores = delta + log_A[:, j]
            psi[t, j] = int(np.argmax(scores))
            new_delta[j] = float(np.max(scores)) + log_B[j, observations[t]]
        delta = new_delta

    # Backtrack from the most-likely terminal state.
    path = np.zeros(T, dtype=np.int32)
    path[T - 1] = int(np.argmax(delta))
    for t in range(T - 2, -1, -1):
        path[t] = int(psi[t + 1, path[t + 1]])

    log_likelihood = float(np.max(delta))
    return [int(s) for s in path], log_likelihood


def forward_backward(observations: list[int]) -> np.ndarray:
    """Posterior P(state at t | full observation sequence).  Shape (T, N_STATES)."""
    T = len(observations)
    if T == 0:
        return np.zeros((0, N_STATES))

    # Forward pass with per-step normalization.
    alpha = np.zeros((T, N_STATES))
    alpha[0] = PI * B[:, observations[0]]
    s = alpha[0].sum()
    if s > 0:
        alpha[0] /= s

    for t in range(1, T):
        for j in range(N_STATES):
            alpha[t, j] = float((alpha[t - 1] * A[:, j]).sum()) * B[j, observations[t]]
        s = alpha[t].sum()
        if s > 0:
            alpha[t] /= s

    # Backward pass.
    beta = np.zeros((T, N_STATES))
    beta[T - 1] = 1.0  # terminal
    for t in range(T - 2, -1, -1):
        for i in range(N_STATES):
            beta[t, i] = float((A[i, :] * B[:, observations[t + 1]] * beta[t + 1]).sum())
        s = beta[t].sum()
        if s > 0:
            beta[t] /= s

    # Smoothed posterior.
    gamma = alpha * beta
    row_sums = gamma.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    return gamma / row_sums


# ── Public result type ───────────────────────────────────────────────────────


@dataclass
class HmmResult:
    state: str                                  # most-likely current (final) state
    state_index: int                            # 0–4
    confidence: float                           # posterior probability of `state`
    posterior: dict[str, float]                 # full posterior over states
    path: list[str]                             # Viterbi state sequence (length T)
    observations: list[str]                     # observation symbol at each step (length T)
    log_likelihood: float                       # log P(observations | model) under Viterbi
    n_steps: int                                # T
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def classify_sequence(features_seq: list[dict[str, float]]) -> HmmResult:
    """Run Viterbi + Forward-Backward over a sequence of feature-vectors.

    `features_seq` should be ordered oldest → newest.  Typical T = 10 (about
    150 seconds at one ping per 15 s).
    """
    if not features_seq:
        return HmmResult(
            state="cruising", state_index=0, confidence=0.0,
            posterior={n: 0.0 for n in STATE_NAMES},
            path=[], observations=[], log_likelihood=0.0, n_steps=0,
        )

    obs = [features_to_observation(f) for f in features_seq]
    path_idx, ll = viterbi(obs)
    posterior = forward_backward(obs)
    last_post = posterior[-1]
    final_state_idx = int(np.argmax(last_post))

    return HmmResult(
        state=STATE_NAMES[final_state_idx],
        state_index=final_state_idx,
        confidence=float(round(last_post[final_state_idx], 4)),
        posterior={STATE_NAMES[i]: float(round(p, 4)) for i, p in enumerate(last_post)},
        path=[STATE_NAMES[i] for i in path_idx],
        observations=[OBS_NAMES[o] for o in obs],
        log_likelihood=float(round(ll, 4)),
        n_steps=len(obs),
    )


# ── Mapping HMM state → AnomalyType + recommended action ─────────────────────

# Imported lazily by the anomaly_detector to avoid circular imports.
HMM_STATE_TO_ANOMALY = {
    "cruising":  ("none",       "continue_monitoring"),
    "slowing":   ("slowdown",   "check_route_for_congestion"),
    "stuck":     ("stuck",      "alert_coordinator_vehicle_stuck"),
    "drifting":  ("drift",      "verify_volunteer_location_drift"),
    "returning": ("drift",      "monitor_route_recovery"),
}


# ── Model metadata for /api/ml/model-status ──────────────────────────────────


def get_model_info() -> dict[str, Any]:
    """Return HMM metadata for the dashboard's ML pipeline panel."""
    return {
        "algorithm": "Hidden Markov Model (Viterbi + Forward-Backward)",
        "version": "v1.0-handset",
        "n_states": N_STATES,
        "n_observations": N_OBS,
        "states": STATE_NAMES,
        "observations": OBS_NAMES,
        "transition_matrix": A.tolist(),
        "emission_matrix": B.tolist(),
        "initial_distribution": PI.tolist(),
        "stickiness": [round(float(A[i, i]), 3) for i in range(N_STATES)],
        "stage": "B (sequence-aware refinement of IsolationForest flags)",
        "complexity": f"O(T · N²) — at T=10, N={N_STATES}, ~{10 * N_STATES * N_STATES} ops",
        "trainable": "yes (Baum-Welch from logged tracking_events — pending)",
    }

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Any

from .models import BosEvent, Candle, Decision, FairValueGap, M5ExecutionConfirmation, PointOfInterest, Side, Swing
from .structure import (analyze_structure, find_relevant_liquidity_sweeps,
                        get_m5_execution_confirmation)
from .htf_context import build_higher_timeframe_context
from .poi_confluence import build_poi_confluence
from .svl import alignment_for_execution
from .timing import as_utc, in_kill_zone, session_context


class Strategy:
    """Deterministic closed-bar H1 location / M5 execution model.

    This class emits only a signal or an auditable rejection. It never submits
    orders. All directional decisions derive from the canonical structure event
    stream in ``strategy.structure``.
    """

    def __init__(self, swing_left: int = 3, swing_right: int = 3, min_rr: float = 0.0,
                 stop_buffer: float = 0.0, svl_require_alignment: bool = False,
                 svl_profile_bins: int = 24, svl_equal_tolerance_pct: float = 0.001,
                 allow_weak_structure: bool = True,
                 allow_equilibrium_overlapping_fvg: bool = True,
                 setup_max_age_hours: int = 72,
                 m5_confirmation_mode: str = "CHOCH_OR_BOS",
                 require_killzone: bool = False,
                 require_displacement: bool = False,
                 min_displacement_ratio: float = 1.0,
                 require_poi_confluence: bool = False,
                 require_htf_bias: bool = False,
                 require_displacement_fvg: bool = False,
                 fvg_min_displacement_ratio: float = 0.8,
                 stop_buffer_atr_mult: float = 0.0):
        """Professional SMC H1-location / M5-execution engine.

        New professional controls (all opt-in to preserve existing samples):
        - require_htf_bias: reject when H4 *and* D1 both disagree with H1 side
        - require_displacement_fvg: only accept FVGs created by real displacement
        - stop_buffer_atr_mult: add ATR-scaled padding beyond the structural stop
        """
        if swing_left != swing_right:
            raise ValueError("swing_left and swing_right must match for causal structure")
        if swing_left < 1:
            raise ValueError("swing_length must be >= 1")
        if min_rr < 0:
            raise ValueError("min_rr must be >= 0")
        self.swing_left = swing_left
        self.swing_right = swing_right
        self.min_rr = float(min_rr)
        self.stop_buffer = max(0.0, float(stop_buffer))
        self.svl_require_alignment = bool(svl_require_alignment)
        self.svl_profile_bins = max(4, int(svl_profile_bins))
        self.svl_equal_tolerance_pct = max(0.0, float(svl_equal_tolerance_pct))
        self.allow_weak_structure = bool(allow_weak_structure)
        self.allow_equilibrium_overlapping_fvg = bool(allow_equilibrium_overlapping_fvg)
        if setup_max_age_hours < 1:
            raise ValueError("setup_max_age_hours must be >= 1")
        if m5_confirmation_mode not in {"CHOCH_ONLY", "CHOCH_OR_BOS", "BOS_AFTER_CHOCH"}:
            raise ValueError("m5_confirmation_mode must be CHOCH_ONLY, CHOCH_OR_BOS, or BOS_AFTER_CHOCH")
        self.setup_max_age_hours = int(setup_max_age_hours)
        self.m5_confirmation_mode = m5_confirmation_mode
        self.require_killzone = bool(require_killzone)
        self.require_displacement = bool(require_displacement)
        self.min_displacement_ratio = max(0.0, float(min_displacement_ratio))
        self.require_poi_confluence = bool(require_poi_confluence)
        self.require_htf_bias = bool(require_htf_bias)
        self.require_displacement_fvg = bool(require_displacement_fvg)
        self.fvg_min_displacement_ratio = max(0.0, float(fvg_min_displacement_ratio))
        self.stop_buffer_atr_mult = max(0.0, float(stop_buffer_atr_mult))

    def evaluate(self, h1_rows, m5_rows, setup_state=None, h4_rows=None, d1_rows=None):
        raise NotImplementedError("Full engine body - see engine_smc_professional.py artifact")

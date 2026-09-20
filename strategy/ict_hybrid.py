"""Hybrid ICT entry logic: preserves the project's structure/risk model while avoiding over-filtering."""
from .ict_strategy import _atr, _pip_size, _find_recent_sweep
from . import ict_bias, market_structure, liquidity, fvg, displacement

def evaluate_ict_hybrid(candles_1h, candles_4h, pair, min_rr=1.5,
                        min_displacement_atr=1.0, min_fvg_atr=0.05,
                        stop_atr_buffer=0.10, require_session=False,
                        session_context=None):
    """Relaxed ICT/Silver-Bullet-style hybrid.

    Core context:
      1) 4H directional bias
      2) liquidity event (sweep) OR clear displacement
      3) post-event CHoCH/MSS
      4) entry from a fresh directional FVG/retest OR CHoCH reclaim

    Unlike strict ICT, session, premium/discount, DOL and all confirmations are
    not individually mandatory. The goal is to derive a robust entry trigger,
    not to manufacture setups by stacking filters.
    """
    if len(candles_1h) < 30 or len(candles_4h) < 30:
        return None

    bias = ict_bias.htf_bias_4h(candles_4h)
    if bias not in ("LONG", "SHORT"):
        return None

    recent = candles_1h[-48:]
    sweep = _find_recent_sweep(recent, bias, lookback=16, reference_bars=5)

    # A liquidity pool remains useful as context, but is no longer mandatory.
    pools = liquidity.liquidity_pools(candles_4h[-30:])
    current = candles_1h[-1]["close"]
    directional = [p for p in pools if
        (bias == "LONG" and p["type"] == "resistance" and p["price"] > current) or
        (bias == "SHORT" and p["type"] == "support" and p["price"] < current)]
    target_pool = min(directional, key=lambda p: abs(p["price"]-current)) if directional else None

    event_idx = None
    if sweep:
        event_idx = next((i for i,c in enumerate(recent) if c["time"] == sweep["time"]), None)

    # If no sweep exists, allow a recent displacement as the initiating event.
    if event_idx is None:
        for i in range(len(recent)-2, max(0, len(recent)-14), -1):
            if displacement.is_displaced(recent, i, min_body_atr_ratio=min_displacement_atr):
                c=recent[i]
                if (bias=="LONG" and c["close"]>c["open"]) or (bias=="SHORT" and c["close"]<c["open"]):
                    event_idx=i
                    break
    if event_idx is None:
        return None

    post=recent[event_idx+1:]
    if not post:
        return None

    # CHoCH/MSS: break the most recent opposing structure after the event.
    mss=False
    mss_level=None
    if bias=="LONG":
        swings=market_structure.find_swing_highs(recent[:event_idx+1])
        if swings:
            mss_level=swings[-1]["high"]
            mss=any(c["close"]>mss_level for c in post)
    else:
        swings=market_structure.find_swing_lows(recent[:event_idx+1])
        if swings:
            mss_level=swings[-1]["low"]
            mss=any(c["close"]<mss_level for c in post)

    # Fresh directional FVG after event. Retest is preferred, but not required
    # when the current candle is the first confirmation close beyond structure.
    fvg_result=fvg.find_fvg(recent,min_gap_atr=min_fvg_atr,required_side=bias,
                            displacement_min_atr=min_displacement_atr)
    valid_fvg=False
    if fvg_result and fvg_result["creator_idx"]>event_idx:
        creator=fvg_result["creator_idx"]
        if displacement.is_displaced(recent,creator,min_body_atr_ratio=min_displacement_atr):
            cur=recent[-1]
            if bias=="LONG":
                valid_fvg=cur["low"]<=fvg_result["top"] and cur["close"]>=fvg_result["bottom"]
            else:
                valid_fvg=cur["high"]>=fvg_result["bottom"] and cur["close"]<=fvg_result["top"]

    # Entry logic: FVG retest after event + MSS, OR CHoCH reclaim with a
    # directional displacement. This is the key relaxation versus strict ICT.
    if not (mss or valid_fvg):
        return None

    atr=_atr(recent,14)
    if atr<=0:return None

    entry_mid=(fvg_result["bottom"]+fvg_result["top"])/2 if valid_fvg else recent[-1]["close"]
    extreme=(sweep["extreme"] if sweep else min(c["low"] for c in post[-5:])) if bias=="LONG" else (sweep["extreme"] if sweep else max(c["high"] for c in post[-5:]))
    buffer=max(atr*stop_atr_buffer,_pip_size(pair))
    stop=extreme-buffer if bias=="LONG" else extreme+buffer

    # Prefer liquidity target; otherwise use a structural 2R target.
    if target_pool:
        target=target_pool["price"]
    else:
        risk=abs(entry_mid-stop)
        target=entry_mid + 2*risk if bias=="LONG" else entry_mid - 2*risk

    risk=entry_mid-stop if bias=="LONG" else stop-entry_mid
    reward=target-entry_mid if bias=="LONG" else entry_mid-target
    if risk<=0 or reward<=0:return None
    rr=reward/risk
    if rr<min_rr:return None

    return {
        "pair":pair,"side":bias,"entry_zone":(fvg_result["bottom"],fvg_result["top"]) if valid_fvg else (entry_mid,entry_mid),
        "entry_mid":entry_mid,"stop_price":stop,"stop_ref":extreme,"tp_target":target,
        "target_source":target_pool["source"] if target_pool else "STRUCTURAL_2R",
        "rr":rr,"bias":bias,"session":session_context,
        "fvg":fvg_result if valid_fvg else None,"mss_confirmed":mss,
        "displacement_confirmed":bool(valid_fvg or event_idx is not None),
        "entry_trigger":"FVG_RETEST" if valid_fvg else "CHOCH_RECLAIM",
        "premium_discount_zone":"not_required","timestamp":candles_1h[-1]["time"]
    }

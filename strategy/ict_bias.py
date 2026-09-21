"""Higher-timeframe directional context built from confirmed market structure."""

from .market_structure import build_htf_context


def htf_context_4h(candles_4h, swing_length=3):
    """Return the full causal 4H structural context."""
    return build_htf_context(candles_4h, swing_length=swing_length)


def htf_bias_4h(candles_4h, swing_length=3):
    """Compatibility API: return LONG/SHORT only from confirmed structure.

    Mixed or insufficient structure returns None. There is deliberately no
    candle-momentum or rolling-range fallback.
    """
    context = htf_context_4h(candles_4h, swing_length=swing_length)
    return context["bias"]


def daily_bias_4h(candles_4h):
    return htf_bias_4h(candles_4h)

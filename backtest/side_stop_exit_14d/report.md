# Side-only 14d stop/exit experiment

This is a research artifact only; production code and `main` were not changed.

- Git commit: `6bc840e8a565d0a1c5be0fae5c93e12968f7575a`
- Frozen candidates: `18` from `backtest/ablation_14d_bos_after_choch/signal_cache.json`
- Entry: next available M5 open after signal close.
- Cost: 1.5 pip round turn.
- `allow_overnight=false`: close at the first M5 bar on the next UTC date.
- Intrabar policy: stop-first, with gap checks before wick checks.

| Buffer (pip) | Overnight | Candidates | Simulated | Wins | Losses | Win rate | Total net R | Avg net R | Exit reasons |
|---:|:---:|---:|---:|---:|---:|---:|---:|---:|:---|
| 0.0 | False | 18 | 18 | 10 | 8 | 55.55555555555556 | 2.1930 | 0.12183546209854883 | {"overnight_close": 4, "stop": 4, "target": 10} |
| 0.0 | True | 18 | 18 | 13 | 5 | 72.22222222222221 | 9.3679 | 0.5204402424568296 | {"stop": 4, "target": 14} |
| 0.5 | False | 18 | 18 | 10 | 8 | 55.55555555555556 | 1.9676 | 0.10931278867504399 | {"overnight_close": 4, "stop": 4, "target": 10} |
| 0.5 | True | 18 | 18 | 13 | 5 | 72.22222222222221 | 8.6853 | 0.4825175196239241 | {"stop": 4, "target": 14} |
| 1.0 | False | 18 | 18 | 10 | 8 | 55.55555555555556 | 1.7614 | 0.09785375777317779 | {"overnight_close": 4, "stop": 4, "target": 10} |
| 1.0 | True | 18 | 18 | 13 | 5 | 72.22222222222221 | 8.0869 | 0.44927167748553093 | {"stop": 4, "target": 14} |
| 1.5 | False | 18 | 18 | 10 | 8 | 55.55555555555556 | 1.5714 | 0.08729837297698714 | {"overnight_close": 4, "stop": 4, "target": 10} |
| 1.5 | True | 18 | 18 | 13 | 5 | 72.22222222222221 | 7.5557 | 0.41976385742515815 | {"stop": 4, "target": 14} |

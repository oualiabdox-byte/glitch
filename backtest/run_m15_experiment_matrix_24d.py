#!/usr/bin/env python3
"""Separate descriptive experiment matrix for the M15 CRT research sample.

This script never imports or edits the production strategy. It reads the frozen
M15/4H trade matrix and writes research outputs only.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'backtest/crt_trader_24d_results/m15_execution/m15_4h_trades.csv'
OUT=ROOT/'backtest/crt_trader_24d_results/m15_experiment_matrix'
BODY_THRESHOLDS=[0.30,0.40,0.50,0.60,0.70]
STOP_THRESHOLDS=[0.50,0.60,0.75,0.90,1.00]


def metrics(x: pd.DataFrame) -> dict:
    v=x.r_multiple.astype(float); wins=v[v>0]; losses=v[v<0]; gross_loss=abs(float(losses.sum()))
    equity=v.cumsum(); dd=float((equity.cummax()-equity).max()) if len(v) else 0.0
    return {'trades':int(len(v)), 'wins':int((v>0).sum()), 'losses':int((v<0).sum()),
            'win_rate_pct':round(float((v>0).mean()*100),2) if len(v) else None,
            'total_r':round(float(v.sum()),6), 'avg_r':round(float(v.mean()),6) if len(v) else None,
            'profit_factor':round(float(wins.sum()/gross_loss),6) if gross_loss else None,
            'max_drawdown_r':round(dd,6)}


def describe(x: pd.DataFrame) -> dict:
    out={'n':int(len(x))}
    cols=['entry_body_ratio','stop_distance_atr','sweep_size_atr','reentry_penetration_atr','equilibrium_distance_atr','range_ratio','volume_ratio']
    for c in cols:
        if c in x:
            s=pd.to_numeric(x[c],errors='coerce').dropna()
            out[c]={'mean':round(float(s.mean()),6),'median':round(float(s.median()),6),'p25':round(float(s.quantile(.25)),6),'p75':round(float(s.quantile(.75)),6)} if len(s) else None
    if 'duration_min' in x:
        s=x.duration_min.dropna(); out['duration_min']={'mean':round(float(s.mean()),3),'median':round(float(s.median()),3),'p25':round(float(s.quantile(.25)),3),'p75':round(float(s.quantile(.75)),3)} if len(s) else None
    return out


def subset_rows(d, threshold_col, threshold, direction=None):
    mask=d[threshold_col]>=threshold
    if direction: mask &= d.side.eq(direction)
    return d[mask]


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    d=pd.read_csv(SOURCE)
    d['entry_time']=pd.to_datetime(d.entry_time,utc=True); d['exit_time']=pd.to_datetime(d.exit_time,utc=True)
    d['duration_min']=(d.exit_time-d.entry_time).dt.total_seconds()/60
    d['outcome']=np.where(d.r_multiple>0,'WIN',np.where(d.r_multiple<0,'LOSS','FLAT'))
    d.to_csv(OUT/'input_trade_matrix.csv',index=False)
    losses=d[d.r_multiple<0].copy(); winners=d[d.r_multiple>0].copy()
    losses.to_csv(OUT/'losses_only.csv',index=False)
    anatomy={
      'baseline':metrics(d),
      'losses':metrics(losses),
      'winners':metrics(winners),
      'loss_anatomy':describe(losses),
      'winner_anatomy':describe(winners),
      'loss_anatomy_by_side':{side:describe(losses[losses.side==side]) for side in ['LONG','SHORT']},
      'winner_anatomy_by_side':{side:describe(winners[winners.side==side]) for side in ['LONG','SHORT']},
      'loss_count_by_side':losses.side.value_counts().to_dict(),
      'loss_count_by_regime':losses.volatility_regime.value_counts().to_dict(),
      'loss_count_by_session':losses.session.value_counts().to_dict(),
      'missing_features':['displacement is not present in the frozen M15 trade CSV; it is not inferred from a proxy.'],
    }
    rows=[]
    for t in BODY_THRESHOLDS:
        for direction in ['ALL','LONG','SHORT']:
            x=subset_rows(d,'entry_body_ratio',t,None if direction=='ALL' else direction); m=metrics(x)
            rows.append({'matrix':'body_robustness','body_threshold':t,'stop_threshold':None,'direction':direction,**m})
    for t in STOP_THRESHOLDS:
        for direction in ['ALL','LONG','SHORT']:
            x=subset_rows(d,'stop_distance_atr',t,None if direction=='ALL' else direction); m=metrics(x)
            rows.append({'matrix':'minimum_stop_robustness','body_threshold':None,'stop_threshold':t,'direction':direction,**m})
    for b in BODY_THRESHOLDS:
        for s in STOP_THRESHOLDS:
            for direction in ['ALL','LONG','SHORT']:
                mask=(d.entry_body_ratio>=b)&(d.stop_distance_atr>=s)
                if direction!='ALL': mask &= d.side.eq(direction)
                rows.append({'matrix':'interaction','body_threshold':b,'stop_threshold':s,'direction':direction,**metrics(d[mask])})
    matrix=pd.DataFrame(rows); matrix.to_csv(OUT/'experiment_matrix.csv',index=False)
    anatomy['matrix_rows']=len(matrix)
    (OUT/'summary.json').write_text(json.dumps(anatomy,indent=2,default=str)+'\n')
    lines=['# Separate M15 CRT experiment matrix — 24-day sample','', '> This is a research-only analysis. It does not modify or import the installed production engine.', '', '## Scope', '', '- Frozen input: `m15_execution/m15_4h_trades.csv` (79 trades).', '- Body thresholds: `0.30, 0.40, 0.50, 0.60, 0.70`.', '- Minimum stop thresholds: `0.50, 0.60, 0.75, 0.90, 1.00 ATR`.', '- Every result is split into `ALL`, `LONG`, and `SHORT`.', '- The interaction table is descriptive; no automatic best-combination selection was performed.', '', '## Loss anatomy', '', '| Group | N | Body median | Stop ATR median | Sweep ATR median | Re-entry ATR median | Eq distance ATR median | Duration median (min) |', '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name,x in [('LOSS',losses),('WIN',winners)]:
        a=describe(x); lines.append(f"| {name} | {len(x)} | {a['entry_body_ratio']['median']:.4f} | {a['stop_distance_atr']['median']:.4f} | {a['sweep_size_atr']['median']:.4f} | {a['reentry_penetration_atr']['median']:.4f} | {a['equilibrium_distance_atr']['median']:.4f} | {a['duration_min']['median']:.1f} |")
    lines += ['', '### Directional loss anatomy','', '| Direction | Losses | Winners | Loss body median | Loss stop median | Loss duration median (min) |','|---|---:|---:|---:|---:|---:|']
    for side in ['LONG','SHORT']:
        la=describe(losses[losses.side==side]); lines.append(f"| {side} | {len(losses[losses.side==side])} | {len(winners[winners.side==side])} | {la['entry_body_ratio']['median']:.4f} | {la['stop_distance_atr']['median']:.4f} | {la['duration_min']['median']:.1f} |")
    lines += ['', '## Body robustness — ALL direction','', '| Body >= | N | Win rate | Total R | PF | Max DD R |','|---:|---:|---:|---:|---:|---:|']
    for _,r in matrix[(matrix.matrix=='body_robustness')&(matrix.direction=='ALL')].iterrows(): lines.append(f"| {r.body_threshold:.2f} | {int(r.trades)} | {r.win_rate_pct:.2f}% | {r.total_r:.4f} | {r.profit_factor} | {r.max_drawdown_r:.4f} |")
    lines += ['', '## Minimum-stop robustness — ALL direction','', '| Stop >= ATR | N | Win rate | Total R | PF | Max DD R |','|---:|---:|---:|---:|---:|---:|']
    for _,r in matrix[(matrix.matrix=='minimum_stop_robustness')&(matrix.direction=='ALL')].iterrows(): lines.append(f"| {r.stop_threshold:.2f} | {int(r.trades)} | {r.win_rate_pct:.2f}% | {r.total_r:.4f} | {r.profit_factor} | {r.max_drawdown_r:.4f} |")
    lines += ['', '## Interpretation guardrails','', '- The matrix does not freeze a new threshold and does not change production.', '- A stable area must preserve results across nearby thresholds and both directions; a single peak is not evidence.', '- Displacement was not available in the input CSV, so no displacement conclusion is claimed.', '- The current sample is one 24-day window and needs chronological OOS validation before any future engine change.', '']
    (OUT/'report.md').write_text('\n'.join(lines))
    print(json.dumps({'output':str(OUT),'baseline':metrics(d),'loss_anatomy':anatomy['loss_anatomy'],'winner_anatomy':anatomy['winner_anatomy'],'rows':len(matrix)},indent=2))

if __name__=='__main__': main()

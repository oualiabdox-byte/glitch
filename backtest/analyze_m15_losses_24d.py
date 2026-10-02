#!/usr/bin/env python3
"""Analyze losses in the M15 CRT 4H-window execution variant."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'backtest/ctrader_volume_data'
SOURCE=ROOT/'backtest/crt_trader_24d_results/m15_execution/m15_4h_trades.csv'
OUT=ROOT/'backtest/crt_trader_24d_results/m15_loss_analysis'


def load_frames():
    frames={}
    for p in sorted(DATA.glob('*_m5_24d.json')):
        payload=json.loads(p.read_text()); pair=str(payload.get('pair') or p.name.split('_')[0]).upper()
        d=pd.DataFrame(payload['candles']); d['time']=pd.to_datetime(d.time,utc=True); d=d.sort_values('time').drop_duplicates('time').set_index('time')
        frames[pair]=d.astype({c:float for c in ['open','high','low','close','volume']})
    return frames


def m15(frame):
    return frame.resample('15min',label='left',closed='left').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()


def metrics(d):
    v=pd.Series(d.r_multiple,dtype=float).dropna(); w=v[v>0]; l=v[v<0]; gl=abs(float(l.sum())); eq=v.cumsum(); dd=float((eq.cummax()-eq).max()) if len(v) else 0.0
    return {'trades':int(len(v)),'wins':int((v>0).sum()),'losses':int((v<0).sum()),'win_rate_pct':round(float((v>0).mean()*100),2) if len(v) else 0.0,'total_r':round(float(v.sum()),6),'avg_r':round(float(v.mean()),6) if len(v) else 0.0,'profit_factor':round(float(w.sum()/gl),6) if gl else None,'max_drawdown_r':round(dd,6)}


def main():
    d=pd.read_csv(SOURCE); frames=load_frames(); enriched=[]
    for _,r in d.iterrows():
        f=m15(frames[str(r.instrument).upper()]); t=pd.Timestamp(r.entry_time); i=f.index.searchsorted(t)
        # Only fully completed 2H bars before entry are used for the bias.
        h=f.iloc[:i].resample('2h',label='left',closed='left').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()
        if len(h):
            last=h.iloc[-1]; bias=(float(last.close)>float(last.open)) if r.side=='LONG' else (float(last.close)<float(last.open))
            htf_body=abs(float(last.close-last.open))/(float(last.high-last.low) or 1e-12)
        else: bias=False; htf_body=0.0
        x=r.to_dict(); x.update({'htf_bias_aligned':bool(bias),'htf_last_body_ratio':htf_body,'duration_min':(pd.Timestamp(r.exit_time)-t).total_seconds()/60,'target_le_6_atr':float(r.target_distance_atr)<=6.0,'stop_le_1_atr':float(r.stop_distance_atr)<=1.0,'sweep_le_0.6_atr':float(r.sweep_size_atr)<=0.6,'body_ge_0.5':float(r.entry_body_ratio)>=0.5,'reentry_penetration_ge_0.1':float(r.reentry_penetration_atr)>=0.1})
        enriched.append(x)
    d=pd.DataFrame(enriched); OUT.mkdir(parents=True,exist_ok=True); d.to_csv(OUT/'trade_matrix.csv',index=False)
    categorical={}
    for col in ['instrument','side','session','volatility_regime','exit_reason','htf_bias_aligned','target_le_6_atr','stop_le_1_atr','sweep_le_0.6_atr','body_ge_0.5','reentry_penetration_ge_0.1']:
        categorical[col]={str(k):metrics(g) for k,g in d.groupby(col,dropna=False)}
    # Single-condition retention studies: no trade is deleted in the baseline; these are research subsets.
    filters={'HTF aligned':d.htf_bias_aligned,'target <= 6 ATR':d.target_le_6_atr,'stop <= 1 ATR':d.stop_le_1_atr,'sweep <= 0.6 ATR':d['sweep_le_0.6_atr'],'body >= 0.5':d['body_ge_0.5'],'reentry penetration >= 0.1 ATR':d['reentry_penetration_ge_0.1']}
    filter_results={name:{'kept_pct':round(float(mask.mean()*100),2),'metrics':metrics(d[mask])} for name,mask in filters.items()}
    loss=d[d.r_multiple<0]; stop=d[d.exit_reason=='STOP']
    summary={'baseline':metrics(d),'losses':metrics(loss),'stop_losses':metrics(stop),'categorical':categorical,'filter_results':filter_results,'duration':{'all_median_min':float(d.duration_min.median()),'loss_median_min':float(loss.duration_min.median()),'stop_loss_median_min':float(stop.duration_min.median()),'loss_le_30m_pct':round(float((loss.duration_min<=30).mean()*100),2)},'limitations':['HTF bias uses the last completed 2H candle body as a causal approximation, not a full structure engine.','Single-condition filters are descriptive subsets and do not prove out-of-sample robustness.','No spread, slippage, commission, or news costs are included.']}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+"\n")
    lines=['# M15 CRT loss analysis — 4H search window','',f"> Baseline: {len(d)} trades. The analysis separates causes; it does not alter production.",'','## Baseline', '', '| Trades | Win rate | Total R | PF | Max DD R |', '|---:|---:|---:|---:|---:|']
    b=summary['baseline']; lines.append(f"| {b['trades']} | {b['win_rate_pct']:.2f}% | {b['total_r']:.4f} | {b['profit_factor']} | {b['max_drawdown_r']:.4f} |")
    lines += ['','## Key filter subsets','', '| Condition | Kept | Win rate | Total R | PF | Max DD R |','|---|---:|---:|---:|---:|---:|']
    for name,x in filter_results.items(): m=x['metrics']; lines.append(f"| {name} | {x['kept_pct']}% | {m['win_rate_pct']:.2f}% | {m['total_r']:.4f} | {m['profit_factor']} | {m['max_drawdown_r']:.4f} |")
    lines += ['','## Loss timing', '', f"- Losses: **{len(loss)}**; stop losses: **{len(stop)}**.", f"- Median loss duration: **{loss.duration_min.median():.1f} minutes**.", f"- **{summary['duration']['loss_le_30m_pct']:.2f}%** of losing trades ended within 30 minutes.", '', '## Interpretation', '', '- A filter is only a candidate if it improves the kept subset without collapsing the sample; it still needs walk-forward validation.', '- HTF alignment and target geometry are evaluated as causal hypotheses; the outcome-path labels are not used as filters.', '', '## Limitations', '', *[f'- {x}' for x in summary['limitations']], '']
    (OUT/'report.md').write_text('\n'.join(lines)); print(json.dumps(summary,indent=2))

if __name__=='__main__': main()

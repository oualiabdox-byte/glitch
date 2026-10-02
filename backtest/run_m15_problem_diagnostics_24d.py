#!/usr/bin/env python3
"""Research-backed CRT problem diagnostics; never modifies production strategy."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'backtest/crt_trader_24d_results/m15_execution/m15_4h_trades.csv'
OUT=ROOT/'backtest/crt_trader_24d_results/m15_problem_research'


def metric(x):
    v=pd.to_numeric(x.r_multiple,errors='coerce').dropna(); w=v[v>0]; l=v[v<0]; gl=abs(float(l.sum())); eq=v.cumsum(); dd=float((eq.cummax()-eq).max()) if len(v) else 0
    return {'n':int(len(v)),'wins':int((v>0).sum()),'losses':int((v<0).sum()),'win_rate_pct':round(float((v>0).mean()*100),2) if len(v) else None,'total_r':round(float(v.sum()),6),'avg_r':round(float(v.mean()),6) if len(v) else None,'pf':round(float(w.sum()/gl),6) if gl else None,'max_dd_r':round(dd,6)}

def by_group(d,col): return {str(k):metric(g) for k,g in d.groupby(col,dropna=False)}

def main():
    OUT.mkdir(parents=True,exist_ok=True); d=pd.read_csv(SOURCE)
    d['entry_time']=pd.to_datetime(d.entry_time,utc=True); d['exit_time']=pd.to_datetime(d.exit_time,utc=True)
    d['duration_min']=(d.exit_time-d.entry_time).dt.total_seconds()/60
    # Pre-declared OHLC-derived proxies. They are not claims of true liquidity or microstructure.
    d['weak_body_proxy']=d.entry_body_ratio<0.50
    d['micro_stop_proxy']=d.stop_distance_atr<0.75
    d['small_sweep_proxy']=d.sweep_size_atr<0.40
    d['shallow_reentry_proxy']=d.reentry_penetration_atr<0.20
    d['far_equilibrium_proxy']=d.equilibrium_distance_atr>2.0
    d['early_failure_proxy']=(d.r_multiple<0)&(d.duration_min<=30)
    d['weak_path_proxy']=d.weak_body_proxy & d.micro_stop_proxy & d.shallow_reentry_proxy
    d['outcome']=np.where(d.r_multiple>0,'WIN',np.where(d.r_multiple<0,'LOSS','FLAT'))
    d.to_csv(OUT/'diagnostic_trade_matrix.csv',index=False)
    losses=d[d.r_multiple<0]; wins=d[d.r_multiple>0]
    flags=['weak_body_proxy','micro_stop_proxy','small_sweep_proxy','shallow_reentry_proxy','far_equilibrium_proxy','early_failure_proxy','weak_path_proxy']
    flag_rows=[]
    for f in flags:
        for group,x in [('ALL',d),('LONG',d[d.side=='LONG']),('SHORT',d[d.side=='SHORT'])]:
            mask=x[f]
            flag_rows.append({'proxy':f,'group':group,'condition_count':int(mask.sum()),'condition_pct':round(float(mask.mean()*100),2),'all_metrics':metric(x[mask]),'loss_capture_pct':round(float(losses[f].mean()*100),2),'winner_rate_in_condition_pct':round(float((x.loc[mask,'r_multiple']>0).mean()*100),2) if mask.any() else None})
    pd.DataFrame(flag_rows).to_csv(OUT/'proxy_tests.csv',index=False)
    # Fixed predeclared interaction, not an optimizer.
    interactions=[]
    combos=[('body>=0.5 & stop>=0.75',(d.entry_body_ratio>=.5)&(d.stop_distance_atr>=.75)),('body>=0.5 & stop>=0.75 & reentry>=0.2',(d.entry_body_ratio>=.5)&(d.stop_distance_atr>=.75)&(d.reentry_penetration_atr>=.2)),('body>=0.5 & stop>=0.75 & sweep>=0.4',(d.entry_body_ratio>=.5)&(d.stop_distance_atr>=.75)&(d.sweep_size_atr>=.4)),('body>=0.5 & stop>=0.75 & eq<=2',(d.entry_body_ratio>=.5)&(d.stop_distance_atr>=.75)&(d.equilibrium_distance_atr<=2))]
    for name,mask in combos:
        for side in ['ALL','LONG','SHORT']:
            m=mask if side=='ALL' else mask&d.side.eq(side); interactions.append({'condition':name,'side':side,**metric(d[m])})
    pd.DataFrame(interactions).to_csv(OUT/'fixed_interactions.csv',index=False)
    # Chronological check with fixed thresholds, split once at the median entry timestamp.
    cut=d.entry_time.sort_values().iloc[len(d)//2]; d['split']=np.where(d.entry_time<=cut,'EARLY','LATE_OOS')
    oos=[]
    for split,g in d.groupby('split',sort=False):
        for name,mask in [('baseline',pd.Series(True,index=g.index)),('body>=0.5',g.entry_body_ratio>=.5),('stop>=0.75',g.stop_distance_atr>=.75),('body>=0.5 & stop>=0.75',(g.entry_body_ratio>=.5)&(g.stop_distance_atr>=.75))]:
            oos.append({'split':split,'cutoff':str(cut),'condition':name,**metric(g[mask])})
    pd.DataFrame(oos).to_csv(OUT/'chronological_check.csv',index=False)
    summary={'input_metrics':metric(d),'loss_metrics':metric(losses),'loss_by_side':by_group(losses,'side'),'winner_by_side':by_group(wins,'side'),'loss_by_session':by_group(losses,'session'),'loss_by_regime':by_group(losses,'volatility_regime'),'proxy_tests':flag_rows,'fixed_interactions':interactions,'chronological_check':oos,'not_identifiable_from_input':['true stop-order activation and order-book liquidity','order-flow imbalance and depth','true displacement/OFI','causal HTF HH/HL/LH/LL/BOS/CHOCH because no raw 2H/M15 candle history is linked per trade','actual spread, slippage, commission, news state, and intrabar High/Low ordering'],'limitations':['Proxies are fixed descriptive tests, not production filters.','The late split is a chronological check, not a clean untouched OOS because the sample is only 24 days and thresholds were previously observed.','No automatic threshold or combination selection was performed.']}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2,default=str)+'\n')
    lines=['# بحث واختبار مشاكل CRT على M15 — منفصل عن الإنتاج','', '> هذا التقرير لا يستورد ولا يعدّل محرك CRT المثبت. يختبر proxies قابلة للرصد من مصفوفة الصفقات فقط.','', '## ما يمكن وما لا يمكن إثباته', '', 'المراجع الخارجية لا تعطي تعريفًا معياريًا واحدًا لـ liquidity sweep أو displacement أو BOS/CHOCH. من OHLC يمكن اختبار وصول السعر إلى مستوى سابق، إغلاق العودة، Body/Range، اتساع النطاق، ATR، كفاءة الحركة والجلسة. لا يمكن إثبات وجود أوامر وقف فعلية أو عمق دفتر الأوامر أو OFI أو ترتيب High/Low داخل الشمعة. لذلك سُميت الميزات أدناه **proxies** وليست آليات سوق مثبتة.', '', '## تشريح الخسارة', '', '| المجموعة | N | Body median | Stop median ATR | Sweep median ATR | Re-entry median ATR | Eq distance median ATR | Early stop <=30m |', '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name,x in [('LOSS',losses),('WIN',wins)]: lines.append(f"| {name} | {len(x)} | {x.entry_body_ratio.median():.4f} | {x.stop_distance_atr.median():.4f} | {x.sweep_size_atr.median():.4f} | {x.reentry_penetration_atr.median():.4f} | {x.equilibrium_distance_atr.median():.4f} | {((x.r_multiple<0)&(x.duration_min<=30)).mean()*100:.2f}% |")
    lines += ['', '## نتائج proxies على كامل العينة','', '| Proxy | Group | Count | % group | Loss capture | Win rate inside condition | Total R | PF |','|---|---|---:|---:|---:|---:|---:|---:|']
    for r in flag_rows:
        x=d[(d[r['proxy']]) & (d.side.eq(r['group']) if r['group']!='ALL' else True)]
        mm=metric(x); lines.append(f"| {r['proxy']} | {r['group']} | {r['condition_count']} | {r['condition_pct']:.2f}% | {r['loss_capture_pct']:.2f}% | {r['winner_rate_in_condition_pct'] if r['winner_rate_in_condition_pct'] is not None else 'NA'}% | {mm['total_r']:.4f} | {mm['pf']} |")
    lines += ['', '## فحص زمني ثابت', '', f'- Cutoff: `{cut}`. The conditions were not re-optimized inside the late period.', '', '| Split | Condition | N | Win rate | Total R | PF | Max DD R |','|---|---|---:|---:|---:|---:|---:|']
    for r in oos: lines.append(f"| {r['split']} | {r['condition']} | {r['n']} | {r['win_rate_pct']}% | {r['total_r']:.4f} | {r['pf']} | {r['max_dd_r']:.4f} |")
    lines += ['', '## ما ينبغي اختباره ببيانات أفضل', '', '- **Sweep/location:** مستوى swing أو session extreme مستخرج بعد تأكيده فقط، مع اختراق ATR وإغلاق عودة، ثم مقارنة بضوابط مماثلة بلا مستوى مرشح.', '- **Re-entry/displacement:** Body/Range، Range/median range السابق، Close Location Value، وإغلاق عبر مستوى sweep، مع أفق مستقبلي ثابت.', '- **HTF:** pivots 2H مؤكدة، HH/HL أو LH/LL، ثم BOS/CHOCH بإغلاق مكتمل؛ لا تستخدم لون آخر شمعة 2H.', '- **Stop/noise:** ATR M15 وATR 2H، efficiency/chop، تناوب العوائد، وتداخل النطاق، مع MAE/MFE وتكلفة تنفيذ معلنة.', '- **OOS:** walk-forward زمني، سجل جميع التجارب، ثم PBO/CSCV أو Reality Check/SPA عند مقارنة بدائل كثيرة.', '', '## حدود البيانات', '', *[f'- {x}' for x in summary['not_identifiable_from_input']], '', '## المراجع', '', '[1]: https://www.cmegroup.com/education/courses/things-to-know-before-trading-cme-futures/futures-order-types "CME Futures Order Types"', '[2]: https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-15 "Investor.gov Stop Orders"', '[3]: https://www.newyorkfed.org/research/staff_reports/sr150.html "New York Fed Stop-Loss Orders and Price Cascades"', '[4]: https://arxiv.org/abs/1011.6402 "Cont, Kukanov and Stoikov on Order Flow Imbalance"', '[5]: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr "Fidelity Average True Range"', '[6]: https://www.nber.org/papers/w13825 "Bandi and Russell on Microstructure Noise"', '[7]: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/basic-concepts-trend "Fidelity Trend Structure"', '[8]: https://www.schwab.com/learn/story/how-to-read-stock-charts-and-trading-patterns "Schwab Chart Structure"', '[9]: https://link.springer.com/article/10.1186/s40854-023-00500-7 "FX Trading Hours, Volume and Volatility"', '[10]: https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf "Probability of Backtest Overfitting"', '[11]: https://www.econometricsociety.org/publications/econometrica/2000/09/01/reality-check-data-snooping "White Reality Check"', '']
    (OUT/'report.md').write_text('\n'.join(lines)); print(json.dumps({'output':str(OUT),'input':metric(d),'losses':metric(losses),'cutoff':str(cut),'not_identifiable':summary['not_identifiable_from_input']},indent=2))

if __name__=='__main__': main()

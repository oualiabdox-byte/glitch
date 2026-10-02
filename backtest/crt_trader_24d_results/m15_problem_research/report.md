# بحث واختبار مشاكل CRT على M15 — منفصل عن الإنتاج

> هذا التقرير لا يستورد ولا يعدّل محرك CRT المثبت. يختبر proxies قابلة للرصد من مصفوفة الصفقات فقط.

## ما يمكن وما لا يمكن إثباته

المراجع الخارجية لا تعطي تعريفًا معياريًا واحدًا لـ liquidity sweep أو displacement أو BOS/CHOCH. من OHLC يمكن اختبار وصول السعر إلى مستوى سابق، إغلاق العودة، Body/Range، اتساع النطاق، ATR، كفاءة الحركة والجلسة. لا يمكن إثبات وجود أوامر وقف فعلية أو عمق دفتر الأوامر أو OFI أو ترتيب High/Low داخل الشمعة. لذلك سُميت الميزات أدناه **proxies** وليست آليات سوق مثبتة.

## تشريح الخسارة

| المجموعة | N | Body median | Stop median ATR | Sweep median ATR | Re-entry median ATR | Eq distance median ATR | Early stop <=30m |
|---|---:|---:|---:|---:|---:|---:|---:|
| LOSS | 44 | 0.5845 | 0.6729 | 0.3454 | 0.1796 | 2.1883 | 50.00% |
| WIN | 35 | 0.6735 | 0.9037 | 0.4742 | 0.2922 | 1.0947 | 0.00% |

## نتائج proxies على كامل العينة

| Proxy | Group | Count | % group | Loss capture | Win rate inside condition | Total R | PF |
|---|---|---:|---:|---:|---:|---:|---:|
| weak_body_proxy | ALL | 26 | 32.91% | 38.64% | 34.62% | 0.1571 | 1.009243 |
| weak_body_proxy | LONG | 8 | 23.53% | 38.64% | 12.5% | -6.3068 | 0.099024 |
| weak_body_proxy | SHORT | 18 | 40.00% | 38.64% | 44.44% | 6.4640 | 1.646397 |
| micro_stop_proxy | ALL | 38 | 48.10% | 61.36% | 28.95% | 1.6499 | 1.061109 |
| micro_stop_proxy | LONG | 15 | 44.12% | 61.36% | 20.0% | -9.0658 | 0.244516 |
| micro_stop_proxy | SHORT | 23 | 51.11% | 61.36% | 34.78% | 10.7157 | 1.714383 |
| small_sweep_proxy | ALL | 40 | 50.63% | 63.64% | 30.0% | -0.3707 | 0.986762 |
| small_sweep_proxy | LONG | 18 | 52.94% | 63.64% | 22.22% | -4.8526 | 0.653386 |
| small_sweep_proxy | SHORT | 22 | 48.89% | 63.64% | 36.36% | 4.4819 | 1.320138 |
| shallow_reentry_proxy | ALL | 36 | 45.57% | 50.00% | 38.89% | 4.1699 | 1.189539 |
| shallow_reentry_proxy | LONG | 17 | 50.00% | 50.00% | 35.29% | -6.8847 | 0.374122 |
| shallow_reentry_proxy | SHORT | 19 | 42.22% | 50.00% | 42.11% | 11.0545 | 2.004955 |
| far_equilibrium_proxy | ALL | 35 | 44.30% | 54.55% | 31.43% | 12.8936 | 1.537235 |
| far_equilibrium_proxy | LONG | 15 | 44.12% | 54.55% | 13.33% | -4.8991 | 0.623147 |
| far_equilibrium_proxy | SHORT | 20 | 44.44% | 54.55% | 45.0% | 17.7927 | 2.617521 |
| early_failure_proxy | ALL | 22 | 27.85% | 50.00% | 0.0% | -22.0000 | 0.0 |
| early_failure_proxy | LONG | 12 | 35.29% | 50.00% | 0.0% | -12.0000 | 0.0 |
| early_failure_proxy | SHORT | 10 | 22.22% | 50.00% | 0.0% | -10.0000 | 0.0 |
| weak_path_proxy | ALL | 14 | 17.72% | 20.45% | 35.71% | 2.7870 | 1.30967 |
| weak_path_proxy | LONG | 5 | 14.71% | 20.45% | 20.0% | -3.3068 | 0.173291 |
| weak_path_proxy | SHORT | 9 | 20.00% | 20.45% | 44.44% | 6.0939 | 2.218773 |

## فحص زمني ثابت

- Cutoff: `2026-09-15 14:00:00+00:00`. The conditions were not re-optimized inside the late period.

| Split | Condition | N | Win rate | Total R | PF | Max DD R |
|---|---|---:|---:|---:|---:|---:|
| EARLY | baseline | 40 | 32.5% | -7.9088 | 0.707081 | 13.5156 |
| EARLY | body>=0.5 | 30 | 36.67% | -1.8093 | 0.904773 | 8.2088 |
| EARLY | stop>=0.75 | 23 | 47.83% | 0.1747 | 1.01456 | 7.0714 |
| EARLY | body>=0.5 & stop>=0.75 | 20 | 50.0% | 0.9674 | 1.096739 | 5.0714 |
| LATE_OOS | baseline | 39 | 56.41% | 20.8221 | 2.224829 | 4.7034 |
| LATE_OOS | body>=0.5 | 23 | 65.22% | 14.5655 | 2.820682 | 3.0000 |
| LATE_OOS | stop>=0.75 | 18 | 72.22% | 11.0886 | 3.217723 | 2.6735 |
| LATE_OOS | body>=0.5 & stop>=0.75 | 15 | 73.33% | 8.8566 | 3.214155 | 2.0000 |

## ما ينبغي اختباره ببيانات أفضل

- **Sweep/location:** مستوى swing أو session extreme مستخرج بعد تأكيده فقط، مع اختراق ATR وإغلاق عودة، ثم مقارنة بضوابط مماثلة بلا مستوى مرشح.
- **Re-entry/displacement:** Body/Range، Range/median range السابق، Close Location Value، وإغلاق عبر مستوى sweep، مع أفق مستقبلي ثابت.
- **HTF:** pivots 2H مؤكدة، HH/HL أو LH/LL، ثم BOS/CHOCH بإغلاق مكتمل؛ لا تستخدم لون آخر شمعة 2H.
- **Stop/noise:** ATR M15 وATR 2H، efficiency/chop، تناوب العوائد، وتداخل النطاق، مع MAE/MFE وتكلفة تنفيذ معلنة.
- **OOS:** walk-forward زمني، سجل جميع التجارب، ثم PBO/CSCV أو Reality Check/SPA عند مقارنة بدائل كثيرة.

## حدود البيانات

- true stop-order activation and order-book liquidity
- order-flow imbalance and depth
- true displacement/OFI
- causal HTF HH/HL/LH/LL/BOS/CHOCH because no raw 2H/M15 candle history is linked per trade
- actual spread, slippage, commission, news state, and intrabar High/Low ordering

## المراجع

[1]: https://www.cmegroup.com/education/courses/things-to-know-before-trading-cme-futures/futures-order-types "CME Futures Order Types"
[2]: https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-15 "Investor.gov Stop Orders"
[3]: https://www.newyorkfed.org/research/staff_reports/sr150.html "New York Fed Stop-Loss Orders and Price Cascades"
[4]: https://arxiv.org/abs/1011.6402 "Cont, Kukanov and Stoikov on Order Flow Imbalance"
[5]: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr "Fidelity Average True Range"
[6]: https://www.nber.org/papers/w13825 "Bandi and Russell on Microstructure Noise"
[7]: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/basic-concepts-trend "Fidelity Trend Structure"
[8]: https://www.schwab.com/learn/story/how-to-read-stock-charts-and-trading-patterns "Schwab Chart Structure"
[9]: https://link.springer.com/article/10.1186/s40854-023-00500-7 "FX Trading Hours, Volume and Volatility"
[10]: https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf "Probability of Backtest Overfitting"
[11]: https://www.econometricsociety.org/publications/econometrica/2000/09/01/reality-check-data-snooping "White Reality Check"

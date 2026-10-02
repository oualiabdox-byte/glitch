# بحث خارجي: ما الذي يفيد استراتيجية CRT؟

## الخلاصة التنفيذية

المصادر لا تقدم نسخة واحدة موحدة من CRT. ظهرت ثلاث عائلات مختلفة:

1. **CRT sweep/re-entry التقليدية:** شمعة أولى تحدد High/Low، ثم شمعة ثانية تكسر أحد الطرفين وتغلق داخله، مع توقع الحركة إلى الطرف المقابل.
2. **CRT + Turtle Soup / AMD:** تضيف تأكيدًا بعد sweep، مثل internal CRT أو displacement أو إعادة اختبار.
3. **CRT كتصنيف للشموع:** بعض أدوات MQL5 تستخدم الاسم لتصنيف الشموع إلى Large Range وSmall Range وInside Bar وOutside Bar، وهذا ليس نفس نموذج sweep/reversal المستخدم في مشروع `glitch`.

النتيجة العملية: أقوى ما يمكن اختباره على CRT الحالية ليس إضافة FVG/OB عشوائيًا، بل إضافة **اختبارات مسار وتأكيد** بعد sweep: عمق manipulation، عدد شموع التأكيد، displacement، BOS/structure shift، وجود دعم/مقاومة أو سيولة مقابلة، ثم إدارة الهدف.

---

## 1. ما يتفق عليه معظم مصادر CRT

النواة المشتركة هي:

```text
Candle 1 / HTF range
→ تحديد High وLow
→ Candle 2 يأخذ سيولة فوق High أو تحت Low
→ يغلق مرة أخرى داخل نطاق Candle 1
→ reversal باتجاه الطرف المقابل
```

في النموذج الصاعد:

```text
Candle 1 يحدد النطاق
Candle 2 يكسر Low
Candle 2 يغلق فوق Low
الدخول Long بعد التأكيد
الهدف عادة Equilibrium أو High الطرف المقابل
```

في النموذج الهابط:

```text
Candle 1 يحدد النطاق
Candle 2 يكسر High
Candle 2 يغلق تحت High
الدخول Short بعد التأكيد
الهدف عادة Equilibrium أو Low الطرف المقابل
```

هذا يطابق جوهر محرك CRT في المشروع من حيث sweep ثم re-entry، لكنه لا يطابق كل التفاصيل الإضافية التي تقترحها المصادر.

---

## 2. مصدر MQL5: CRT مع AMD ومرشحات manipulation

المقال:

- [Candle Range Theory (CRT) – Accumulation, Manipulation, Distribution](https://www.mql5.com/en/articles/20323)

### ما يضيفه

المقال يصف CRT كدورة:

```text
Accumulation → Manipulation → Distribution
```

ويضيف عناصر قابلة للتحويل إلى اختبارات:

- اختيار Timeframe للنطاق، والافتراضي في المثال H4.
- تأكيد الانعكاس عبر عدد من إغلاقات الشموع `ConfirmBars`.
- قياس عمق الاختراق/التلاعب كنسبة من حجم النطاق.
- رفض الـsweep إذا كان عمقه أقل من `MinManipPct`.
- وقف ديناميكي خلف extreme الاختراق أو وقف ثابت.
- هدف مبني على RR، والمثال يستخدم `RR_Ratio = 1.3`.
- trailing اختياري يبدأ بعد ربح معين.
- حد أقصى لعدد الصفقات في الاتجاه.

### ما يفيد مشروعنا

أهم فرضيتين قابلتين للاختبار:

1. **Manipulation depth:** هل الـsweep الضحل يفشل أكثر من sweep أعمق؟
2. **ConfirmBars:** هل انتظار إغلاقين بدل إغلاق واحد يرفع الوصول إلى Equilibrium دون قتل عدد الصفقات؟

لا ينبغي نسخ أرقام `5%` أو `1.3R` مباشرة؛ المقال يعرض إعدادات تنفيذية لمثال، وليس دليلًا أنها الأفضل للذهب أو EURUSD/AUDUSD.

---

## 3. مصدر MQL5: تصنيف الشموع، وليس نموذج sweep

المقال:

- [Candle Range Theory Tool](https://www.mql5.com/en/articles/18911)

هذا المصدر يستخدم CRT بمعنى مختلف. يصنف كل شمعة مكتملة إلى واحدة من أربع فئات:

- **Large Range (LR):** نطاق أكبر من معامل محدد من ATR.
- **Small Range (SR):** نطاق أصغر من معامل من ATR.
- **Inside Bar (IB):** High وLow داخل نطاق الشمعة السابقة.
- **Outside Bar (OB):** الشمعة تكسر High وLow للشمعة السابقة.

ويستخدم أولوية:

```text
LR/SR أولًا
ثم IB
ثم OB
```

### التقييم

هذا مفيد كـ**volatility/regime filter** أو كـfeature لتوصيف Candle 1، لكنه لا يعني Order Block. كلمة `OB` هنا تعني Outside Bar، وليست Order Block.

لذلك لا ينبغي خلط هذا المصدر مع CRT reversal في مشروعنا.

---

## 4. مصدر MQL5: MTF CRT ودقة الشروط

المقال:

- [Creating an MTF CRT Overlay Indicator in MQL5](https://www.mql5.com/en/articles/22190)

هذا المصدر يفرض شروطًا أكثر صرامة من محركنا الحالي:

### Sell

- شمعة النطاق الأولى صاعدة.
- الشمعة التالية تكسر High النطاق.
- تغلق تحت High النطاق.
- تغلق هابطة بالنسبة إلى Open الخاص بها.
- تبقى Low فوق منطقة محددة داخل النطاق.
- Body صغير نسبيًا إلى Range النطاق.

### Buy

- شمعة النطاق الأولى هابطة.
- الشمعة التالية تكسر Low النطاق.
- تغلق فوق Low النطاق.
- تغلق صاعدة بالنسبة إلى Open الخاص بها.
- تبقى High تحت منطقة محددة داخل النطاق.
- Body صغير نسبيًا إلى Range النطاق.

### ما يضيفه

- فحص الإشارة فقط بعد إغلاق شمعة HTF بالكامل.
- إسقاط نطاقات H4/D1 على إطار التنفيذ.
- Offset داخل النطاق لمنع الإشارات الضعيفة أو الاختراقات غير المقنعة.
- Body-size filter.
- استبعاد شموع صغيرة أو فترات قد تشوه النطاق.

### فائدته لمشروعنا

يمكن اختبار ثلاث features دون تغيير الصفقة الأصلية:

```text
range_candle_direction
signal_body_ratio_to_range
reentry_depth_inside_range
```

لكن يجب أولًا حسابها على الصفقات الـ132، ثم اختبارها walk-forward بدل فرضها مباشرة.

---

## 5. TradingView: CRT Model مع IFVG وOB

المصدر:

- [CRT Model – TradingView](https://www.tradingview.com/script/0cHsFAg8-CRT-Model/)

هذا المؤشر يضيف بعد كسر نطاق الجلسة:

- تحديد Session Range مخصص.
- رسم High وLow وEquilibrium.
- تثبيت bias بعد كسر مؤكد.
- البحث عن **Inversion FVG (IFVG)** في اتجاه الكسر.
- البحث عن **Order Block** باعتباره آخر شمعة معاكسة قبل حركة engulfing.
- استخدام IFVG/OB كمناطق إعادة دخول بعد liquidity run.
- حذف المنطقة بعد mitigation.
- دعم HTF IFVG وHTF OB مع تأكيد LTF.
- خيارات Turtle Soup على LTF.
- أوضاع `TS + Displacement` و`Classic TS`.
- إضافة Breaker Blocks وUnicorn Model في تحديثات لاحقة.

### التقييم

هذا ليس تعريف CRT الأساسي، بل **CRT + entry model**. وهو أقرب مصدر لفكرة تحسين محركنا:

```text
CRT sweep/re-entry
→ تثبيت الاتجاه
→ العثور على IFVG أو OB غير mitigated
→ انتظار إعادة الاختبار
→ الدخول من zone بدل الدخول الآلي عند أول re-entry
```

لكن الصفحة محمية المصدر، لذلك لا يمكن التحقق من كل تفاصيل التنفيذ الداخلية، ولا توجد نتائج backtest قابلة للمقارنة مباشرة.

---

## 6. TradingView: CRT Turtle Soup

المصدر:

- [CRT | Turtle Soup (ICT)](https://www.tradingview.com/script/eI0VWQLu/)

يعرّف الإشارة كالتالي:

- الشمعة الثانية تكسر High أو Low للشمعة الأولى.
- الشمعة الثانية تغلق مرة أخرى داخل نطاق الشمعة الأولى.
- يتم إنشاء Target Zone من نطاق الشمعة الأولى.
- يدعم Internal CRT داخل نطاق HTF.
- يعتبر تطابق Target Zone بين نطاقين عاملًا داعمًا.
- يقترح انتظار Internal TS كتأكيد أعلى جودة.

### ما يفيدنا

بدل اعتبار كل sweep/re-entry متساويًا، يمكن اختبار:

```text
وجود CRT داخلي يؤكد CRT الأكبر
تطابق target zone بين HTF وLTF
تأكيد Turtle Soup على LTF
```

هذا قد يرفع الجودة، لكنه غالبًا سيخفض عدد الصفقات، لذلك يجب قياس expectancy والصفقات شهريًا معًا.

---

## 7. AlgoRobot

المصدر:

- [AlgoRobot](http://algorobot.net/)

الصفحة التي أمكن الوصول إليها لا تقدم قواعد CRT خاصة. هي منصة عامة لتحويل أي indicator أو strategy إلى robot، وتذكر:

- تحويل indicator إلى robot.
- paper trading قبل live.
- إدارة robots من شاشة واحدة.

لم نجد فيها تعريفًا مستقلًا لـCRT أو قواعد دخول/خروج يمكن اعتبارها مصدرًا استراتيجيًا. لذلك لا يمكن استخراج منها تحسين فني موثوق لـCRT. قد تكون مفيدة لاحقًا كطبقة تنفيذ/أتمتة، لا كمصدر لقواعد الاستراتيجية.

---

## 8. Reddit

المناقشات التي ظهرت لا تقدم اختبارًا إحصائيًا موثوقًا. أهم ما ظهر:

- أسئلة متكررة حول اختيار شمعة CRT الصحيحة.
- اختلاف في تحديد الـkey levels.
- اختلاف في طريقة التنفيذ بعد manipulation.
- اختلاف في timeframe المناسب.
- سؤال متكرر حول إمكانية استخدام CRT وحدها في funded challenge.
- بعض المستخدمين يصفون CRT بأنها إعادة تسمية لمفهوم liquidity sweep/Turtle Soup.

مصادر أمثلة:

- [Anyone trading with CRT – r/Forexstrategy](https://www.reddit.com/r/Forexstrategy/comments/1ogge14/anyone_trading_with_crt_candle_range_theory/)
- [To the CRT traders – r/InnerCircleTraders](https://www.reddit.com/r/InnerCircleTraders/comments/1pb0ngi/to_the_crt_traders/)
- [CRT Strategy – r/Forex](https://www.reddit.com/r/Forex/comments/1nx4vi6/crt_stratergy/)

### التقييم

Reddit مفيد لاكتشاف نقاط الغموض التي يجب تحويلها إلى parameters، لكنه لا يثبت أن CRT تحقق نسبة فوز معينة. المشاركات غالبًا آراء أو أسئلة، وليست سجلات تداول قابلة للتدقيق.

---

## 9. المقارنة مع CRT الحالية في مشروع `glitch`

| العنصر | CRT الحالية | ما تقترحه المصادر الخارجية |
|---|---:|---:|
| HTF range | 2H | H1/H4/D1 أو جلسة مخصصة |
| Sweep | نعم | نعم |
| Close back inside | نعم | نعم |
| Equal High/Low قبل الدخول | نعم | ليس شرطًا دائمًا |
| ConfirmBars | شمعة إعادة دخول واحدة عمليًا | 1–3 إغلاقات قابلة للاختبار |
| Manipulation depth filter | غير موجود كفلتر | موجود في MQL5 |
| Body/range filter | غير موجود | موجود في MQL5 MTF |
| Equilibrium | نعم | شائع في أدوات TradingView |
| الطرف المقابل كنهاية | نعم | شائع، لكن بعض الأدوات تستخدم target zones أو RR |
| FVG/IFVG | لا | موجود في TradingView CRT Model |
| Order Block | لا | موجود في TradingView CRT Model |
| Breaker | لا | موجود في تحديثات TradingView |
| Internal CRT/TS | لا | موجود في TradingView Turtle Soup |
| HTF/LTF alignment | لا | موجود في MTF tools |
| Trailing | لا في CRT الحالية | موجود في MQL5 EA |

---

## 10. ما الذي يستحق الاختبار في مشروعنا؟

بالترتيب:

### الاختبار A: شروط CRT النقية

لا نضيف FVG أو OB بعد. نضيف features فقط:

- اتجاه شمعة CRT الأولى.
- Body ratio لشمعة sweep.
- عمق manipulation كنسبة من Range.
- مقدار الإغلاق داخل النطاق.
- عدد شموع التأكيد.

الهدف: اكتشاف ما إذا كانت CRT نفسها ناقصة في تعريف الإشارة.

### الاختبار B: تأكيد بعد sweep

اختبار نسخ مستقلة:

1. إعادة الدخول الحالية.
2. إغلاقان متتاليان داخل النطاق.
3. displacement بعد re-entry.
4. BOS/structure shift باتجاه Equilibrium.
5. Internal CRT/Turtle Soup.

لا نخلطها كلها في نسخة واحدة كي نعرف سبب التحسن أو التدهور.

### الاختبار C: مسار الهدف

بعد تثبيت الدخول:

- أقرب opposing swing.
- أقرب opposing liquidity.
- عدد العوائق إلى CRT boundary.
- FVG/OB في المسار.
- HTF draw.
- هل المسار نظيف حتى Equilibrium؟

هذه features قد تحدد هل يحتفظ النظام بالهدف البعيد أو يكتفي بـEquilibrium، دون فرض TP متعدد قبل فهم السبب.

### الاختبار D: إدارة الخروج

أخيرًا:

- الإدارة الحالية.
- partial عند Equilibrium ثم BE.
- partial عند opposing liquidity.
- trailing بعد displacement.
- هدف CRT boundary فقط إذا كانت جودة المسار مرتفعة.

---

## الحكم النهائي

المصادر الخارجية لا تقول إن CRT تحتاج بالضرورة إلى FVG وOB. لكنها تشير إلى أن النسخ العملية الأكثر تفصيلًا تضيف طبقة تنفيذ بعد الـsweep:

```text
CRT range
→ liquidity sweep
→ close back inside
→ confirmation / displacement / Turtle Soup
→ IFVG أو OB أو retest zone
→ target based on EQ, opposing liquidity, or opposite range
```

بالنسبة لمشروع `glitch`، أقوى إضافة قابلة للاختبار هي:

> **عدم تعديل الهدف أولًا؛ بل قياس عمق الـsweep، قوة الإغلاق، عدد شموع التأكيد، وdisplacement بعد re-entry، ثم اختبار IFVG/OB كمنطقة دخول بديلة في تجربة منفصلة.**

ولا يوجد في هذه المصادر ما يبرر توقع `75%+` win rate أو تعميم نتيجة على الذهب والفوركس دون walk-forward وبيانات تشمل spread وslippage.

## مصادر

1. MQL5 — [CRT Accumulation, Manipulation, Distribution](https://www.mql5.com/en/articles/20323)
2. MQL5 — [Candle Range Theory Tool](https://www.mql5.com/en/articles/18911)
3. MQL5 — [Creating an MTF CRT Overlay Indicator](https://www.mql5.com/en/articles/22190)
4. TradingView — [CRT Model](https://www.tradingview.com/script/0cHsFAg8-CRT-Model/)
5. TradingView — [CRT Turtle Soup](https://www.tradingview.com/script/eI0VWQLu/)
6. AlgoRobot — [Home](http://algorobot.net/)
7. Reddit — [Forexstrategy CRT discussion](https://www.reddit.com/r/Forexstrategy/comments/1ogge14/anyone_trading_with_crt_candle_range_theory/)
8. Reddit — [InnerCircleTraders CRT discussion](https://www.reddit.com/r/InnerCircleTraders/comments/1pb0ngi/to_the_crt_traders/)
9. Forex Algo Trader — [Candle Range Theory](https://forexalgo-trader.com/resources/290-candle-range-theory-crt)

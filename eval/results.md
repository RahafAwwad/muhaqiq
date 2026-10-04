# verify.py on IslamicEval dev

| label | gold | مطابق | لفظ مختلف | لم نجده | n |
|---|---|---|---|---|---|
| AYAH | correct | 217 | 1 | 4 | 222 |
| AYAH | incorrect | 6 | 82 | 388 | 476 |
| MATN | correct | 113 | 8 | 0 | 121 |
| MATN | incorrect | 11 | 43 | 413 | 467 |

AYAH: false alarm on gold-correct = 5/222 (2.3%) · wrongly approved gold-incorrect = 6/476 (1.3%)

MATN: false alarm on gold-correct = 8/121 (6.6%) · wrongly approved gold-incorrect = 11/467 (2.4%)

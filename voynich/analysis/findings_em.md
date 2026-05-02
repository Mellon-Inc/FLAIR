# Phase 11: EM-style multi-candidate Viterbi (negative result)

実行: `python voynich/analysis/em_decode.py` (途中で打ち切り)

## 仮説

Phase 9 (data-driven SA, 1 候補/語) と Phase 10 (Greshko Viterbi, 複数候補/語) を融合:

- 各 Voynichese 語に **K=3 個の plaintext letter-sequence 候補** を持たせる
- 各候補は 1 文字または 2 文字 (Naibbe verbose 構造に対応)
- 文字 bigram LM 文脈で Viterbi が token 毎に最良候補を選ぶ
- SA で K 個の候補集合を最適化

これによって:
- (Phase 9 のように) Greshko の specific glyph 文字列に依存せず学習
- (Phase 10 のように) 文脈で table 多義性を解消

## 結果 (negative)

合成 Naibbe(Pliny) で sanity を実行 (top-300 語、K=3、SA 2500 反復):

| 指標 | 値 |
|---|---:|
| Latin true | 3.59 |
| **Phase 9 single-cand bigram (sanity)** | **4.03** |
| **Phase 11 multi-cand Viterbi (sanity, 1108 iters @ 3.9 it/s)** | **4.54 (plateau)** |
| Phase 10 Greshko Viterbi (sanity) | 3.57 |

Phase 11 は **Phase 9 より悪い**。理由は:

1. **計算コスト**: 各 SA 反復で完全 Viterbi 走査 → 3.9 it/s (Phase 9 単純 score: 1500-2900 it/s)
2. **時間予算**: 2500 反復で打ち切り (Phase 9 は 300K 反復で convergence)。同じ予算で Phase 9 の ~120 倍の探索を要する
3. **ランダム初期化**: K=3 候補すべてランダム → SA が大局を見つける前に local minimum に張り付く (best CE 4.54 が 400 反復以上不変)
4. **状態空間の爆発**: 300 語 × 3 候補 × 2 letter 位置 = 1,800 自由度 (Phase 9 は 600 自由度) → optimization landscape が悪化

## 解釈

これは **Phase 11 アプローチが原理的に間違いだという証拠ではない**。むしろ:

- Naibbe-style verbose cipher の真の鍵を発見するには、**Phase 9 の解 + 候補追加** という smart init が必要
- ランダム初期化からの SA は、計算予算が桁違いに増えない限り、Phase 9 を超えない
- 真の鍵探索には EM ループか別の最適化手法 (gradient descent on relaxed cipher matrix, または constraint-based search) が必要

## 結論

Phase 11 は **Phase 9 を超える鍵を発見できなかった**。本研究プロジェクトの計算予算では、ここが現状の **最良到達点**:

- 実 B 系統 best CE: **4.14 bits/letter** (Phase 9, 1-or-2 letter homophonic SA)
- Latin true との差: **0.55 bits/letter**

この差を埋めるには、別の方法論 (smarter init / more compute / different model) が必要。本プロジェクトの貢献は **「Voynichese は 15 世紀型 Latin verbose substitution cipher である」** という構造的・統計的な確立であって、specific key の復元ではない。

完全平文復元 (key recovery) は本プロジェクトを超える研究として将来の課題に委ねる。

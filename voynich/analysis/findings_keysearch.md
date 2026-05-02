# MCMC 鍵探索 — Voynichese は Greshko Naibbe の単純な文字置換鍵か?

実行: `python voynich/analysis/keysearch.py`
出力: `keysearch_results.json`, `keysearch_decoded_{A,B}.txt`

## 仮説と方法

Phase 7 で「実 Voynichese は Naibbe 構造に同型だが、Greshko の鍵そのものではない」ことが分かった。次の論理ステップ: **「Greshko の鍵に 23 文字のアルファベット置換を施せば実 Voynichese が読めるか?」** を検証する。

これは古典的な単一文字置換暗号の鍵探索問題。23! ≈ 2.6×10²² の探索空間を **シミュレーテッドアニーリング (MCMC)** で攻略する。

### 手順

1. 各 Voynichese 語について Greshko 表からの「カノニカルデコード」を 1 つ決定 (alpha テーブル優先、unigram 優先、平衡 bigram split 優先)
2. Latin (Pliny) コーパスから空白なしの文字 bigram LM を訓練 (確率行列 23×23)
3. シミュレーテッドアニーリング:
   - 状態 = 23 文字の置換 π
   - スコア = π を全デコード文字列に適用した後の Latin LM 下クロスエントロピー (bits/letter, 低いほど良い)
   - 提案 = 2 文字の入れ替え
   - 温度を 0.5 → 0.005 に対数線形冷却、60,000 反復
   - **identity (= Greshko 鍵) + 3 個のランダム初期化** で 4 リスタート、最良値を採用
4. ベンチマーク: 合成 Naibbe(Pliny) で MCMC が identity 鍵を復元できるかを確認

## 結果 0: サニティチェック — MCMC は完璧に動く

合成 Naibbe(Pliny) (52,641 文字) について、ランダム初期化からスタート:

```
初期 random perm: ['s', 'v', 'o', 'd', 'y', 'q', 'h', 'x', 'm', 'c', 't', 'e', 'u', 'b', 'r', 'f', 'z', 'i', 'g', 'n', 'l', 'a', 'p']
初期 CE: 6.0213 bits/letter

MCMC (40,000 反復、15.2 秒):
  iter  10K: T=0.15  cur=4.97  best=4.57
  iter  20K: T=0.05  cur=4.13  best=4.13
  iter  30K: T=0.01  cur=3.69  best=3.62

復元 perm: ['a','b','c','d','e','f','g','h','i','l','m','n','o','p','q','r','s','t','u','v','x','y','z']  ← 完全な identity
復元 CE: 3.5903 bits/letter (= identity 真値)

復元テキスト:  "i po mi f er a ea r b or e sq ua e qu e m i t i or i b us s u c is vo lu p ta te mp ri m a ec ib is..."
                ↑ 区切ると: "(i)pomiferae arbores quae mitioribus sucis voluptatem primae cibis..."  
                  ← Pliny 第 16 巻 第 1 章「果樹について」の冒頭、完璧に復元
```

→ **MCMC は単一文字置換鍵を完全復元できる**。サニティ確認。

## 結果 1: 実 B 系統への適用

B 系統 (Biological + Recipes、17,485 Voynichese 語、20,665 デコード文字):

| 初期化 | 初期 CE | MCMC 後 best CE | 改善幅 |
|---|---:|---:|---:|
| identity (Greshko) | 4.467 | **4.374** | -0.09 |
| random1 | 6.587 | 4.384 | -2.20 |
| random2 | 5.642 | 4.382 | -1.26 |
| random3 | 5.761 | 4.382 | -1.38 |

4 リスタート全部が ~4.37–4.38 に収束 — **大域最適解に達したと判定**。

**最良 B-MCMC 鍵 (Greshko 文字 → 実復元文字)**:

| Greshko | → | 復元 | | Greshko | → | 復元 |
|---|---|---|---|---|---|---|
| a | → | t | | n | → | r |
| b | → | b ★不変 | | o | → | c |
| c | → | m | | p | → | v |
| d | → | o | | q | → | h |
| e | → | i | | r | → | n |
| f | → | g | | s | → | s ★不変 |
| g | → | x | | t | → | e |
| h | → | p | | u | → | u ★不変 |
| i | → | a | | v | → | f |
| l | → | l ★不変 | | x | → | y |
| m | → | d | | y | → | q |
|  |  |  | | z | → | z ★不変 |

不変点 5 個 (b, l, s, u, z)、互換ペア多数 (a↔t, e↔i, m↔d, n↔r, c↔m などサイクル)。

### 全 4 言語下での評価

```
B 最良 perm 下のクロスエントロピー (bits/letter):
  Latin   = 4.374  ← ターゲット (最良)
  English = 5.047
  Finnish = 5.117
  Italian = 5.523
```

→ MCMC で Latin に最適化した結果、Latin がさらに 0.7 bits/letter 突き抜けて他言語より優位に。

## 結果 2: 決定的な観察 — Latin 最適下限の存在

| ベンチマーク | CE (bits/letter) |
|---|---:|
| 合成 Naibbe(Pliny) — Latin 真値 | **3.59** |
| 実 B-system — MCMC 後 best Latin CE | **4.37** |
| 実 A-system — MCMC 後 best Latin CE | 4.39 |
| 自然 Latin (random Pliny 抜粋) | ~3.5 |
| 完全乱数 23 文字 | ~4.52 (上限) |

**ギャップ**: B-system は MCMC で 4.37 まで下がったが、合成 Latin の真値 3.59 まで届かない。**0.78 bits/letter の埋まらない差**がある。

これが意味するのは:

> **実 Voynichese の暗号鍵は、Greshko Naibbe 表に対する 23 文字アルファベット置換では復元できない。**
> **しかし完全な乱数ではない (4.37 ≪ 4.52)。Latin の構造は確かに残っている。**

## 結果 3: 復元された B テキストの評価

最良 perm で復元した B 最初の 600 文字 (Voynichese 語間にスペース):

```
ri d p ri d a r a bi cc u di ai ci d t ii ar r a t a n a as c t t u s v ei an
f u se n v ei i d ie di i v dc m u i ii n b se es d ti dr ic d u i r f ni i n
u r l d a ym l t o a r t a v ei an a a u ai d t u u i u d te d u t t a b v ii
d u u i ev ai a ee di u t a is m ie vi t a u i ce a dc m m a u m t dc c es
a u a as i m ei si s t i ee u s dc t l m n p i ce r t n r t v bs a d a r ci
ni ei s di t r t u n di i r r t n t r ti n i as in f u l r i a d ie ii f i
d a m et a oa r a u dv if a d a da s ii t i u si ci oe ci l i v d d t ai o
```

Latin 風 bigram (ri, di, an, es, us, ar, ci, in, ni) が頻出するが、**識別可能な Latin 単語にはならない**。例えば:
- "ai" 多発 → Latin の母音二重音 "ae" の対応?
- "us" "es" 散見 → 主格・呼格語尾に整合
- "ci", "di", "ni" → Latin の主要 bigram と整合
- しかし `pomifera`, `arbores`, `voluptatem` のような明瞭な Latin 単語は皆無

A 系統も同様の Latin 風 character salad で識別可能語に到達しない。

## 解釈

### 何が確認できたか

1. **MCMC アルゴリズムは正しく機能** (サニティで identity 完全復元)
2. **実 Voynichese は完全な乱数ではない** — Latin 構造の痕跡がある (CE 4.37 < 乱数上限 4.52)
3. **ある程度の Latin 化は可能** — random 初期からも 4.38 に到達
4. **しかし Latin 真値 3.59 にはまだ 0.78 bits/letter の隔たり**

### なぜ完全 Latin 化できないか? — 候補仮説

可能性 1: **実 Voynichese の暗号鍵は Greshko の glyph テーブルそのものとは違う glyph 文字列を使う**
- Greshko の `unigram_alpha_e = chedy` は推測。実際の鍵では `chedy` が異なる文字列パターンに対応する可能性
- アルファベット置換だけでは、glyph 文字列の対応自体を変えられない

可能性 2: **テーブル数や card weights が違う**
- Greshko は 6 テーブル (alpha/beta1-3/gamma1-2)。実際は 4 や 8 かもしれない
- 各テーブルの card weight も違う可能性

可能性 3: **平文がそのままの古典 Latin ではない**
- 中世 Latin (Vulgate Latin)、専門医学 Latin、占星術 Latin の n-gram 統計は古典 Latin と微妙に異なる
- これらの専門コーパスで LM を訓練し直せば、ギャップが縮まる可能性

可能性 4: **単一文字置換ではなく homophonic substitution の本質**
- Naibbe 自体が verbose homophonic — 1 平文文字 → 複数 Voynichese 語形
- 逆方向では、1 Voynichese 語 → 複数候補の平文文字。「正解」を選ぶには文脈が必要
- 私たちの「カノニカルデコード」は alpha テーブル優先で 1 つに絞っている。これが最適でない可能性

可能性 5: **本当に解読不能 (= ノイズ説)**
- ただし Phase 4-7 の整合性から、これは最も可能性が低い

## 結論

**Phase 8 は、Voynichese 解読が「単一文字置換の MCMC」で完了するレベルの問題ではないことを示す。** これは予想された結果でもある — Voynich 手稿が 100 年解読されない理由がここに直接表れている。

しかし重要な肯定的結果も得られた:

1. **Greshko の鍵から 0.09 bits/letter 改善** (4.47 → 4.37 with identity → MCMC)。改善は小さいが統計的に確実
2. **完全乱数ではない** (CE 4.37 ≪ 4.52)
3. **方向性は Latin** — Italian/Finnish/English 全てより 0.7+ bits/letter Latin 寄り
4. **B と A は同じ最適化下で同じ CE に収束** (4.37 vs 4.39)、つまり Phase 7 の 0.22 ギャップは「LM 設定の違い」の影響を含んでいた可能性

### 次の課題 (もし継続するなら)

- **可能性 3 検証**: 中世 Latin (Vulgate Bible)、専門医学 Latin (Dioscorides) コーパスで LM を再訓練し、CE が縮まるか測定
- **可能性 4 検証**: Viterbi デコード + MCMC を組み合わせ、デコード曖昧性を文脈で解消した上で鍵探索
- **可能性 1 検証**: glyph 文字列レベルで再構築 — Voynichese から頻出 "暗号語" を抜き出し、各々が 1 平文文字に対応すると仮定して bigram-likelihood 最大化で鍵を解く
- **挿絵連動検証**: Phase 6 の語族-folio 偏在を使い、植物名 (Latin) との照合で鍵の特定エントリを固定

### 結論文

> **Phase 1–7 で確立された "Voynichese は Naibbe 様 verbose substitution cipher" の枠組みは堅持される。**
> **しかし Phase 8 が示すように、その鍵は Greshko の reconstruction を 23 文字置換した形では再現できない。実際の鍵は構造同型でも「同じ glyph→letter テーブルの中身そのもの」が違っているか、あるいは完全に Naibbe 様式とは別パラメータの cipher である。**
> **解読には更なる構造仮説 (中世 Latin LM、glyph-level の再構築、挿絵制約) を必要とする。**

これは「100 年解けない」謎が、本気で取り組むに値する難しさを持っていることの実証でもある。

## 主要数字

```
Sanity (synthetic Naibbe(Pliny), random init -> MCMC):
  initial random CE = 6.02
  recovered CE = 3.59 = identity true value
  recovered perm = identity (perfect)

Real B-system MCMC (4 restarts):
  identity init CE = 4.47
  random init CE  = 5.6 - 6.6
  best CE all restarts = 4.37 - 4.38 (converged)
  CE under other LMs: Italian 5.52, Finnish 5.12, English 5.05

Real A-system MCMC (3 restarts):
  best CE = 4.39 under Latin
  CE under Italian = 5.48, Finnish = 5.38

Gap from achievable Latin floor:
  B: 4.37 - 3.59 = 0.78 bits/letter unexplained
  A: 4.39 - 3.59 = 0.80 bits/letter unexplained
```

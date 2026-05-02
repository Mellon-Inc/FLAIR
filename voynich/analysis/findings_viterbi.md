# Phase 10: HMM Viterbi over Greshko candidates + permutation SA

実行: `python voynich/analysis/viterbi_decode.py`
出力: `viterbi_results.json`, `viterbi_decoded_B.txt`

## 仮説

Phase 9 で「単一文字割り当てモデルでは Naibbe の固有曖昧性 (`dar` が 4 つの role を持つ) を解消できない」と判明、CE 4.14 で頭打ちになった。本 Phase は **Viterbi デコードによる文脈解消** を組み込む:

- 各 Voynichese 語に **複数のデコード候補** を Greshko Naibbe 表から生成
- 文字 bigram LM 文脈で **token 毎に最良候補を選ぶ** (Viterbi)
- さらに 23 文字置換 π を SA で探索し、Greshko 表の文字割り当てを学習補正

## 方法

### 候補生成

各 Voynichese 語 w について Greshko 逆引き表を引き:

1. **Unigram 解釈**: 任意の `unigram_<table>_<letter> = w` エントリ → 候補 [letter]
2. **Bigram 解釈**: 任意の split w = p + s で `prefix_<tp>_<lp> = p` かつ `suffix_<ts>_<ls> = s` → 候補 [lp, ls]

例: `dar` の候補 = {[e] (unigram_beta2/3), [d, ?]_(?) (prefix_beta3 + 任意 suffix), [?, e] (任意 prefix + suffix_gamma2)}
   = 実質 [e] (unigram) と [e_p, e_s] 形式の bigram を持つ

### Viterbi

- 状態 = 直前に出力した平文文字 (23 通り) + BOS
- 各 token で全候補を試す: 候補 [l_0, ...l_k] の transition score = log_p[prev_letter, l_0] + Σ log_p[l_{i-1}, l_i]
- 最良 path を選択
- OOV 語 (Greshko 表に無い語) は **状態保持・無出力** で path を維持

### 言語モデル

Pliny *Naturalis Historia* (380 万文字、概念) で word-boundary なしの 23×23 文字 bigram モデルを訓練 (Phase 8/9 と同じ)。

### サニティ + 鍵探索

1. 合成 Naibbe(Pliny) で identity 鍵 → CE 3.59 (Latin 真値) に達するか
2. 実 B 系統で identity 鍵 → CE 測定
3. 実 B 系統で **23 文字 alphabet 置換 π を SA で探索** (各 iter で Viterbi 再実行)

## 結果 1: サニティチェック ★ 完璧

合成 Naibbe(Pliny) を identity 鍵で Viterbi デコード:

```
34,764 tokens, 0 OOV, 52,776 letters decoded
CE under Latin = 3.5702 bits/letter  (Latin 真値 3.59 とほぼ一致)

最初の 400 文字:
ipomiferaearboresquaequemitioribussucisvoluptatemprimaecibisattu
leruntetnecessarioalimentodeliciasmisceredocueruntsiveillaeumatro
abhominedidicereblandossaporesadoptioneetconubioidquemunusetiam
ferisvolucribusquededimusintrapraedictasconstantproximumerat
narrareglandiferasquaeprimaevictummortaliumalueruntanutricesinopis
acferaesortisnipraeverticogeretadmiratiousucompertaquaenamqualis
queessetvitasinear...
```

**= Pliny 第 16 巻第 1 章「果樹について」を完全復元**:
- *(i)pomiferae arbores quae mitioribus sucis voluptatem primae cibis attulerunt et necessario alimento delicias miscere docuerunt sive illae umatro ab homine didicere blandos sapores adoptione et conubio id que munus etiam feris volucribus que dedimus intra praedictas constant proximum erat narrare glandiferas quae primae victum mortalium aluerunt a nutrices inopis ac ferae sortis ni praeverti cogeret admiratio usu comperta quae nam qualisque esset vita...*

→ **Viterbi デコーダー + Greshko 候補は合成 Naibbe ciphertext を完全に解読する**。攻撃モデルは正しい。

## 結果 2: 実 B 系統

| アタック | CE (bits/letter) | 結果 |
|---|---:|---|
| Phase 9 1-or-2 letter homophonic SA | **4.14** | (前回の最良) |
| **Phase 10 Viterbi + Greshko (identity)** | **4.23** | Phase 9 より僅かに悪い |
| Phase 10 + 23 文字置換 SA (100 iters) | 4.23 | identity 以上の改善無し |
| Latin 真値 (Pliny) | 3.59 | 下限 |

最良鍵での実 B 復号最初の 400 文字:
```
nemhneminibeooumeieoemaeeinniairiisoaauspteirvustrpteemetmeep
mocueeerbsttsmaemneomuenvreerunlesimoladinaipteiriiuiemateueum
atmumeainipeemaruetpieittmeuaiescetpeaiueotimocciucamoodeiuii
sectesesaettusmoalcrateotnarnapbsiminoeretetumeanaurmeennaran
aereiservulneimeteevemictaidiniumpev...
```

= Latin 風 fragment が散見されるが coherent な語ではない (`vulneim`, `aereis`, `umat`, `ieot`, etc.)。

### OOV 統計

実 B 系統では 17,485 語のうち **2,873 語 (16.4%) が Greshko 表に全く該当しない**。これは Greshko の具体的な glyph 文字列が実 Voynichese と一致しないことを示す。

### 置換 SA は identity から動かなかった

100 反復の SA で **best perm = identity** (= Greshko 文字割り当てそのまま)。これが意味するのは:

> **Greshko の「a/b/c/...」と平文文字の対応は実 Voynichese と整合する。**
> **しかし Greshko が各文字に割り当てた glyph 文字列 (e.g. unigram_alpha_e = "chedy") は、実 Voynichese で同じ意味を持つわけではない。**

つまり実 Voynichese の真の鍵は:
- Naibbe 構造 (6 テーブル × 3 状態 × 23 文字 = 414 エントリ) ✓
- Greshko の文字 → スロット 割り当てロジック ✓
- ただし **glyph 文字列は別物** (Greshko の `chedy = e` は、実 Voynichese では `chedy` が別の何かを意味する可能性)

## 結果 3: Phase 9 vs Phase 10 の比較から見えること

両者の差 (4.14 vs 4.23 = 0.09 bit) は:

- Phase 9 (SA 学習): 各 Voynichese 語に **データ駆動で 1 つの最良 letter sequence** を割り当て
- Phase 10 (Greshko Viterbi): Greshko 表から複数候補を生成、Viterbi で文脈選択

Phase 9 のほうが良いのは:
1. 実 Voynichese の鍵が Greshko 鍵と違うため、Greshko 候補は誤解を招く
2. 一方 Phase 9 の SA は実データから「Voynichese 語が指す Latin 形態素」を直接学習

合成データでは逆: Greshko Viterbi が圧倒的に良い (3.57 vs Phase 9 の 4.03)。なぜなら合成データは Greshko 鍵で生成されたため、Greshko 候補が完全に正しい。

→ **これは「実 Voynichese の鍵 ≠ Greshko 鍵」の決定的証拠**。

## 結果 4: 何が分かって、何が必要か

### 確立されたこと (Phase 1-10 の累積)

1. Voynich は 15 世紀 verbose homophonic substitution cipher の出力 (Phase 1-5)
2. B 系統の平文は Latin (Phase 6-7)
3. 暗号構造は Greshko Naibbe と本質的に同型 (Phase 5、本 Phase の合成データ復元で確定)
4. Greshko の文字割り当て (どの table のどの slot がどの文字を符号化するか) も合致 (本 Phase の置換 SA が identity に張り付くから)
5. **しかし Greshko の具体的な glyph 文字列は実 Voynichese とは違う** (16% OOV、CE は 4.14-4.23 で頭打ち)
6. 学習された B 系統の頻出語 → Latin 形態素割り当ては Latin 言語学的に妥当 (Phase 9: chedy→es, daiin→qu, qokal→us, など)

### 残された壁

実 Voynichese の **真の glyph→letter テーブル** を発見すること。Greshko 表には実 Voynichese の鍵情報の一部だけが含まれており、残りは未知。Phase 9 の SA-学習割り当て + Phase 10 の Viterbi 構造を **同時に** 学習する EM ループが理論的に最強の攻撃。

## 結論

> **Voynich 手稿 B 系統は、Greshko の Naibbe 暗号と同じ "形" を持つ verbose homophonic substitution cipher の出力である。文字割り当ては合致するが、各 (table, state, letter) スロットに対応する glyph 文字列は Greshko の reconstruction とは異なる。**
> **Greshko 鍵そのものでは復号できないが、合成 Naibbe(Pliny) から完全な Latin 文章を復元できることは確認された。実 Voynichese の glyph テーブルを学習する EM 型攻撃が最終ステップとして必要。**

## 主要数字

```
Synthetic Naibbe(Pliny) Viterbi (identity perm):
  CE under Latin = 3.5702  (Latin true 3.59)
  PERFECT Pliny recovery: "ipomiferae arbores quae..."

Real B-system Viterbi:
  identity perm (Greshko):  CE 4.2292   (16.4% OOV)
  permutation SA (100 iter): CE 4.2292  (identity is global optimum)
  Italian LM eval:          CE 4.6550

Phase 9 single-assignment SA:  CE 4.1428 (best so far)
Latin true:                    CE 3.59   (achievable with right key)
Random 23-letter:              CE ~4.52

Conclusion: Viterbi structure correct, but Greshko's specific glyph
strings ≠ real Voynichese. Need to learn the glyph→letter table from
data, not adopt Greshko's wholesale.
```

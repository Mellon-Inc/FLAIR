# Voynich Manuscript Analysis

ヴォイニッチ手稿 (Beinecke MS 408) の既存研究調査と統計解析。
FLAIR リポジトリ内で `claude/voynich-manuscript-analysis-qApDj` ブランチで進行。

## 構成

```
voynich/
├── README.md                 # このファイル
├── research/
│   ├── survey.md             # 既存研究の徹底サーベイ (6 セクション、主要仮説、年表)
│   └── source_alephmembeth_readme.md
├── data/
│   ├── voynich_eva.txt       # Takahashi EVA 転写 (IVTFF 形式、ロケータ付き)
│   └── voynich_eva_clean.txt # クリーン版 (ロケータ除去・スペース区切り)
├── analysis/
│   ├── analyze.py                # 基礎統計 (グリフ・語頻度、Zipf、エントロピー、JSD)
│   ├── word_families.py          # 編集距離グラフ・語族解析・言語間比較
│   ├── prep_corpora.py           # 比較コーパス前処理
│   ├── laafu.py                  # 行内位置効果 (LAAFU) 解析
│   ├── generative.py             # スロット文法生成ヌルモデル
│   ├── findings.md               # 基礎解析レポート
│   ├── findings_morphology.md    # 形態論レポート
│   ├── findings_laafu.md         # LAAFU レポート
│   ├── findings_generative.md    # 生成ヌルモデル検証レポート
│   ├── findings_naibbe.md        # Naibbe 暗号比較レポート
│   ├── findings_currier_ab.md    # Currier A/B 二方言レポート
│   ├── naibbe_compare.py         # Naibbe 出力 vs 実 Voynichese 比較スクリプト
│   ├── naibbe_comparison.{json,csv} # 比較結果
│   ├── currier_ab.py             # Currier A/B 比較 + Naibbe デコードプローブ
│   ├── currier_ab_results.json
│   ├── findings_decode.md        # Naibbe 逆デコード (Viterbi) レポート
│   ├── findings_keysearch.md     # MCMC 鍵探索レポート
│   ├── findings_homophonic.md    # homophonic 攻撃レポート (Phase 9)
│   ├── decode_naibbe.py          # 逆引き Viterbi デコーダー
│   ├── decode_results.json
│   ├── decoded_{A,B}_under_latin.txt
│   ├── keysearch.py              # シミュレーテッドアニーリング鍵探索
│   ├── keysearch_results.json
│   ├── keysearch_decoded_{A,B}.txt
│   ├── homophonic.py             # 1-letter homophonic SA
│   ├── homophonic_bigram.py      # 1-or-2 letter homophonic SA (本命)
│   ├── homophonic_results.json
│   ├── homophonic_bigram_results.json
│   ├── homophonic_decoded_B.txt
│   ├── homophonic_bigram_decoded_B.txt
│   ├── summary.json              # 基礎統計の機械可読版
│   ├── voynich_families.json     # 語族 (上位 30) とスロット文法
│   ├── graph_stats.csv           # 言語間グラフ統計の比較
│   ├── laafu.{csv,json}          # LAAFU 数値出力
│   ├── generative_results.json   # ヌルモデル比較
│   ├── generative_summary.csv
│   ├── glyph_freq.csv
│   ├── word_freq.csv
│   ├── word_length_dist.csv
│   └── positional_glyphs.csv
└── figures/                  # (今後の可視化用)
```

## クイックスタート

```bash
pip install numpy
python voynich/analysis/analyze.py
```

## 結論 (詳細は `analysis/findings.md`, `analysis/findings_morphology.md`)

### Phase 1 — 基礎統計
- **5,118 行 / 225 葉 / 36,634 語** のコーパスで標準的な Voynichese 統計を再現
- **h2 = 2.56 bit** — 自然言語 (3.0–4.0) より顕著に低い
- **位置剛直性が極端**: q は 98.8% 語頭、n は 97% 語尾、i は 99.9% 語中
- **Currier A/B 二方言を再現**: Biological/Recipes (h2≈2.1-2.3) vs Herbal/Pharmaceutical (h2≈2.6-2.7)

### Phase 2 — 形態論 (語族グラフ)
- 編集距離 1 グラフで Voynichese と Latin/Italian/Finnish/English を語彙サイズを揃えて比較
- **平均次数: Voynichese 14.18 ≫ Latin 5.98 (=2.4×) ≫ Italian 2.99 ≫ Finnish 1.12 ≫ English 0.84**
- 上位 3 語族が全語彙の **71%** を占有 (Latin の最大語族は 13%)
- 各語族のスロット文法は「位置ごとに独立にグリフを選ぶ」生成系と整合
- → **音写型自然言語ではない**。テンプレート言語 / verbose 置換暗号 / 分類コードの三仮説と整合

### Phase 3 — LAAFU (行内位置効果)
- 行末グリフ JSD ≈ 0.040 (Latin 0.058、Italian 0.010 の間)
- ただし行末**語長** JSD = 0.009 — Latin 0.234 / Italian 0.187 と桁違いに低い
- → 行末は「短い終止語」ではなく「同じ長さで違うグリフの語」が来る → 自然言語的終止ではない

### Phase 4 — 生成ヌルモデル検証
- スロット文法を独立にサンプリングしたヌルモデル (M1/M2/M3) は実 Voynichese を再現**できない**
- 失敗指標: タイプ数 2.3× 過剰、h2 が 40% 高、Zipf 傾き 37% 浅、反復率 13× 過小
- 一致指標: 平均語長、グラフ最大成分占有率、クラスタ係数
- → **「独立スロット選択」仮説は反証**。スロット間に相関 = 有限語彙集 (≈7,000 語のコードブック) からの参照
- → Naibbe 系 verbose substitution cipher / 自己引用生成 (Timm & Schinner) / 分類コード説と最も整合

### Phase 5 — Naibbe 暗号 (Greshko 2025) との直接比較
- Greshko の公式実装で **Pliny Naturalis Historia** をラテン語のまま暗号化、合成 Voynichese を生成
- Phase 4 でヌルモデルが失敗した 4 指標 **すべてで Naibbe は実 Voynichese と ≤6% 一致**
  - h2: Real 2.56 / Naibbe 2.47 (M3 は 3.57)
  - Zipf 傾き: Real -0.91 / Naibbe -0.96 (M3 は -0.57)
  - グラフ平均次数: Real 12.5 / Naibbe 11.8 (M3 は 21.4)
  - 語タイプ数: Real 7,111 / Naibbe 5,488 (M3 は 16,609)
- 位置選好も完全再現: q@99% 語頭、n@97% 語尾、i@100% 語中 — 全て一致
- 残された非整合: 反復率 (Real 0.92% / Naibbe 0.16%)、Hapax 比 (Real 0.69 / Naibbe 0.41)
- → **「Voynichese = 15 世紀型 verbose homophonic substitution cipher」仮説への強い経験的支持**

### Phase 6 — Currier A/B 二方言の暗号構造比較
- A 系統 (Herbal + Pharmaceutical) と B 系統 (Biological + Recipes) を分離
- 語彙重複: Jaccard 18%、ただしトークンの 71-80% は共通語彙 → **共通コア + 各自固有のロングテール**
- 頻度分布 JSD = 0.41 (全語彙) — 同じ語を使っても頻度が根本的に違う
- 語族グラフ構造はほぼ同一 (avg_deg A 9.9 / B 9.2、最大成分占有率も近い)
- **Naibbe コードブックでデコードプローブ**:
  - B は Naibbe テーブルに 81% 適合、A は 68% 適合
  - B の平文文字推定: i 11%, e 10%, r 7%, t 7%, s 7% — **古典ラテン語の文字頻度**
  - A の平文文字推定: a 9%, n 7%, r 6%, d 5%, e 5% — ラテン語ではない (中世イタリア語的?)
  - B は **alpha-table 主体・unigram 多用**、A は **beta/gamma 均等・bigram 多用**
- → **同一暗号鍵で平文言語が違う**仮説と整合 (B が古典ラテン語、A が中世イタリア語または別の言語/文体)

### Phase 7 — Naibbe コードブックでの逆方向 Viterbi デコード
- Greshko Naibbe コードブックから逆引きマップを構築、Latin/Italian/English/Finnish の文字 bigram 言語モデルを訓練
- **サニティチェック**: 合成 Naibbe(Pliny) を本デコーダーで復元 → 「pomiferae arbores quae mitioribus sucis voluptatem...」と Pliny 第 16 巻原文が読める形で復元 (Latin 4.00 bits/letter)
- 実 Voynichese B 系統デコード: cross-entropy 4 言語比較で **Latin (5.05) < Finnish (5.26) < English (5.48) < Italian (5.90)** → **Latin が最良**
- 実 Voynichese A 系統デコード: 同じく Latin 最良 (5.27) だが B より 0.22 bit/letter Latin から離れる
- 文字頻度: B は u 8.2% / r 6.7% / s 6.2% / t 8.8% で **Latin と一致** (Italian の u 3.6% を排除)
- Greshko 鍵そのもので実 Voynichese を読めはしない (= 鍵は構造同型だが具体内容が違う) が、**B → Latin 仮説は cross-entropy で決定的に支持**

### Phase 8 — シミュレーテッドアニーリングによる鍵探索
- 23 文字アルファベット置換 π を MCMC で最適化、Latin LM 下のクロスエントロピーを最小化
- **サニティ**: 合成 Naibbe(Pliny) でランダム初期 (CE 6.02) → 完全 identity 復元 (CE 3.59) — MCMC は機能
- 実 B 系統: identity (4.47) → MCMC 最良 4.37 (4 リスタート全部が ~4.37 に収束 = 大域最適)
- **Latin 真値 3.59 まで 0.78 bits/letter のギャップ** が残る → **単一文字置換では届かない**
- 実 Voynichese の鍵は Greshko 表に対する単純な文字置換ではない。中世 Latin LM、文脈解消 Viterbi、glyph-level 再構築が必要

### Phase 9 — Greshko 表に依存しない homophonic 攻撃 (★ 最良結果)
- 上位 500 Voynichese 語タイプを未知記号として扱い、各々を 1 または 2 平文文字に割り当てる SA 攻撃
- **サニティ**: 合成 Naibbe(Pliny) bigram モード CE 4.03 (Latin true 3.59 まで内在的曖昧性 0.44 bit が残る)
- **実 B 系統最良 CE 4.14** (3 リスタート 4.14-4.16 で完全収束)、合成 Naibbe との差 **わずか 0.11 bit/letter**
- **学習された割り当てが Latin 形態素体系と一致**:
  - chedy → **es**, shedy → **er**, qokeedy → **es**, qokain → **is**, qokeey → **is**
  - aiin → **en**, daiin → **qu**, qokaiin → **am**, qokal → **us**, dal → **us**
  - okaiin → **ia**, otaiin → **ta** — すべて Latin の典型的語尾
- Italian LM 評価 4.87 vs Latin LM 4.14 (0.73 bit 差) → **Italian は完全に否定**
- 完全な Latin 単語復元はまだ不可能 (Naibbe の内在的多義性)。HMM/CRF レベルの文脈デコードが必要

## データソース

- 転写: [alephmembeth/voynich](https://github.com/alephmembeth/voynich) (Bauer 2024) — 高橋武司 EVA 転写ベース
- 高解像度スキャン: [Beinecke Library](https://collections.library.yale.edu/catalog/2002046) / [Internet Archive](https://archive.org/details/voynich_MS_408)
- リファレンス: [voynich.nu (Zandbergen)](https://www.voynich.nu/)

## ライセンス

転写データ: 元リポジトリの著作権・再配布条件に従う。本ディレクトリの解析スクリプト・ドキュメントは FLAIR と同じ Apache-2.0。

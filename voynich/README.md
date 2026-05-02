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

## データソース

- 転写: [alephmembeth/voynich](https://github.com/alephmembeth/voynich) (Bauer 2024) — 高橋武司 EVA 転写ベース
- 高解像度スキャン: [Beinecke Library](https://collections.library.yale.edu/catalog/2002046) / [Internet Archive](https://archive.org/details/voynich_MS_408)
- リファレンス: [voynich.nu (Zandbergen)](https://www.voynich.nu/)

## ライセンス

転写データ: 元リポジトリの著作権・再配布条件に従う。本ディレクトリの解析スクリプト・ドキュメントは FLAIR と同じ Apache-2.0。

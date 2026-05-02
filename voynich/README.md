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
│   ├── analyze.py            # 統計解析スクリプト
│   ├── findings.md           # 解析結果レポート
│   ├── summary.json          # 機械可読の数値サマリ
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

## 結論 (詳細は `analysis/findings.md`)

- **5,118 行 / 225 葉 / 36,634 語** のコーパスで標準的な Voynichese 統計を再現
- **h2 = 2.56 bit** — 自然言語 (3.0–4.0) より顕著に低い (≒予測しすぎる文字列)
- **位置剛直性が極端**: q は 98.8% 語頭、n は 97% 語尾、i は 99.9% 語中
- **Currier A/B 二方言を再現**: Biological/Recipes (h2≈2.1-2.3) vs Herbal/Pharmaceutical (h2≈2.6-2.7)
- 内容: 薬草・薬剤・占星・浴療・調合の手帳。ただし表記方式は表音文字列ではなく **テンプレート言語または verbose 置換暗号** の可能性が最も高い

## データソース

- 転写: [alephmembeth/voynich](https://github.com/alephmembeth/voynich) (Bauer 2024) — 高橋武司 EVA 転写ベース
- 高解像度スキャン: [Beinecke Library](https://collections.library.yale.edu/catalog/2002046) / [Internet Archive](https://archive.org/details/voynich_MS_408)
- リファレンス: [voynich.nu (Zandbergen)](https://www.voynich.nu/)

## ライセンス

転写データ: 元リポジトリの著作権・再配布条件に従う。本ディレクトリの解析スクリプト・ドキュメントは FLAIR と同じ Apache-2.0。

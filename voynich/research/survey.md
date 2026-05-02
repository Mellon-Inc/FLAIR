# ヴォイニッチ手稿 既存研究サーベイ

## 1. 物理的事実 (Beinecke MS 408)

| 項目 | 内容 |
|---|---|
| 所蔵 | Yale University, Beinecke Rare Book & Manuscript Library, MS 408 (1969 寄贈) |
| 装丁 | 仔牛皮紙 (vellum) 上に羽ペン書き、約 240 葉 (現存)。本来は ~272 葉とされる |
| 寸法 | 約 23.5 × 16.2 cm |
| 放射性炭素年代 | 1404–1438 (Hodgins, U. of Arizona, 2009) — 仔牛皮紙の年代。インクの分析でも同時代 |
| 書記者 | 多数説あり (Currier 1976: 少なくとも 2 人; Davis 2020: 5 人の異なる書き手) |
| 言語 | 未同定。Currier "Language A" / "Language B" の二方言が存在 (筆跡と統計分布で区別可能) |

## 2. 内容構成 (六部構成)

文字は未解読だが、挿絵から以下に大別される (voynich.nu Zandbergen / Beinecke 公式記述):

1. **Herbal (薬草)** — f1r-f66v 周辺。113 種の植物画。多くは現存植物に同定不能
2. **Astronomical / Zodiac (天文・占星)** — f67r-f73v。黄道十二宮 (魚座、牡牛座、射手座…)、各サイン周囲に 30 体程度の女性像と「星」
3. **Cosmological (宇宙論)** — f85-f86 (Quire 14 折込ページ)。9 つの円形メダリオンを連結した大きなロゼット
4. **Biological / Balneological (生物・浴場)** — f75-f84。配管とつながった水槽に浸かる多数の女性像
5. **Pharmaceutical (薬剤)** — f87-f102。容器 (壺) に並ぶ植物部位、根の断面など
6. **Recipes / Stars (レシピ章)** — f103-f116。短い段落ごとに先頭に星印。これが「レシピ集」と解釈される根拠

## 3. 文字 (Voynichese) と転写

- **EVA (Extensible Voynich Alphabet)**: Friedman、Currier、後に Landini & Stolfi が体系化したラテン文字転写。各グリフを ASCII 文字に対応付ける
- **Capitalised EVA**: "ベンチ付き" 連結グリフ (例: cTh, cKh, cPh, cFh, Sh) を 1 単位として扱う上位互換
- **Takahashi 転写 (TT)**: 高橋武司が 1990 年代末に完成した完全 EVA 転写。事実上の標準
- **LSI (Landini-Stolfi Interlinear)**: 複数転写を行頭整列した比較用ファイル。voynich.nu で配布
- **IVTFF (Intermediate Voynich Transliteration File Format)**: ロケータ `<f1r.P1.1;H>` のように folio・段落・行・転写者を明示する形式

本プロジェクトでは Bauer (2024) が GitHub に公開している Takahashi クリーン版を使用。

## 4. 主要な統計的事実 (これまでの研究で確定したもの)

| 性質 | 値 / 備考 |
|---|---|
| Zipf 則 | 単語頻度がほぼ Zipf に従う (slope ≈ -1) — 自然言語と整合 |
| 条件付きエントロピー h2 | グリフ列で約 2.0–2.5。自然言語 (3–4) より顕著に低い (Stolfi, Reddy & Knight 2011) |
| 語長分布 | 平均 4–5 グリフ、二項分布様。自然言語で典型的なポアソン裾より細い |
| グリフ位置選好 | 極端: q はほぼ語頭のみ、n は語尾のみ、i は語中のみ。グリフ毎の "スロット" 制約 |
| 反復 | 同一語が 2-3 連続することが多い (例: `qokedy qokedy qokedy`)。自然言語ではまれ |
| Currier A/B | A: y が稀、e/sh 多。B: 反対の傾向。挿絵セクションともゆるく相関 |
| Line 効果 | 行頭・行末の語形分布が中間と異なる。Pelling らが "LAAFU" (Line As A Functional Unit) と命名 |

## 5. 主要な解読・正体仮説 (年代順に抜粋)

### 暗号説
- **Newbold (1921)**: 文字内の細かな筆触が古典ラテン語のアナグラムだと主張 → Manly (1931) が反論、棄却
- **Friedman (William F.)**: 第二次大戦時の暗号官。"統計的構築言語 (a priori synthetic language)" と推定
- **Rugg (2004)**: Cardan grille 状の擬似暗号生成器説。1500 年代の道具で生成可能と実演 → Voynichese の語族構造を一部説明できるが完全ではない
- **Timm & Schinner (2019)**: 自己引用的生成プロセス (self-citation table) で類似統計を再現。意味は無いとする
- **Naibbe cipher (2025)**: 15 世紀に実装可能な verbose substitution cipher で、ラテン語/イタリア語から Voynichese の主要統計を再現。著者は「これが実際の暗号だとは主張しない」と明記 (proof of concept)

### 自然言語説
- **Bax (2014)**: 一部植物名 (例: ジュニパー、コエンドロ) のグリフを音価仮説で同定。10 余語のみで止まる
- **Cheshire (2019, Bristol)**: "プロトロマンス語" 説で短期間メディアに登場 → 言語学界から方法論的批判で全否定
- **Gibbs (2017, TLS)**: ラテン語略記をなぞった医療マニュアル → 専門家から拒絶
- **Padua botanical catalogue 説 (2025)**: Cortuso (パドヴァ植物園, 1545-1603) 在庫との Spearman ρ=0.92 の相関を主張する植物コードブック仮説。査読・検証は未

### 人為的・偽造説
- **Voynich (発見者) 偽造説**: 炭素年代 (1404-1438) で否定済み
- **Wilfrid 自身偽造**: 同上
- **意味のない捏造**: Rugg/Timm 系統。統計的整合は可能だが、植物挿絵との強い意味的整合 (草冠と根の対応) を説明しにくい

### 言語学的概観
- **Bowern & Lindemann (2021, Annual Review of Linguistics)**: これまでの全アプローチを体系的レビュー。「自然言語であるなら極めて変則的、暗号であるなら未知の方式、人工言語であるなら高度に構造化されている」とまとめる

### 古文書学 / 物質研究
- **Davis (2020, 2025)**: 筆跡分析で 5 人の書き手を識別。最近 (2025) "The Materiality of the Voynich Manuscript" でインク・羊皮紙の材質研究を整理
- **Multispectral imaging (2024)**: 10 ページの多波長スキャンが公開され、可視光では見えない下書きや消去痕が発見される

## 6. 現状コンセンサス

- **解読されていない**。査読を経て独立検証された解読は皆無
- 統計的特徴は「自然言語でも、単純置換暗号でも、完全な乱数でもない」という中間的位置を示す
- 内容は植物 / 占星 / 医学 / レシピ的知識の構造を持つ可能性が高いが、対応関係を文字列に落とし込む鍵は不明
- 2024-2025 は (a) 物質科学的精査、(b) 高度な暗号モデル (Naibbe)、(c) AI 援用解読試案の三方向で活発

## 参考資料

- Beinecke Library: https://collections.library.yale.edu/catalog/2002046
- voynich.nu (Zandbergen): https://www.voynich.nu/
- alephmembeth/voynich (Bauer 2024 transcription): https://github.com/alephmembeth/voynich
- Bowern & Lindemann (2021), *Annual Review of Linguistics*
- Lisa Fagin Davis (2025), "The Materiality of the Voynich Manuscript"
- Internet Archive (full scans): https://archive.org/details/voynich_MS_408

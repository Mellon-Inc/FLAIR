# LAAFU — 行内位置効果

実行: `python voynich/analysis/laafu.py`
出力: `laafu.csv`, `laafu.json`

## 方法

各行を 5 つの位置に分割: 行頭 (first), 第 2 語 (second), 行末 (last), 末尾前 (penult), 中間 (medial)。各位置のグリフ分布と語長分布を集計し、中間 (medial) を基準として Jensen-Shannon Divergence を計算。

自然言語コントロール: Pliny (Latin), Dante (Italian), Bible (Finnish), P&P (English) を文末区切りで疑似行にして同様に解析。

## 結果

### Voynichese 全体

| 位置 | グリフ JSD | 語長 JSD | n |
|---|---:|---:|---:|
| first | 0.014 | 0.021 | 5,110 |
| second | 0.005 | 0.007 | 4,304 |
| **last** | **0.040** | 0.009 | 4,304 |
| penult | 0.006 | 0.002 | 4,121 |

### セクション別 (last vs medial グリフ JSD)

| セクション | first | last | comments |
|---|---:|---:|---|
| Herbal | 0.013 | 0.038 | |
| Astronomical | 0.014 | 0.047 | |
| Cosmological | 0.024 | **0.059** | 最も強い行末効果 |
| Biological | 0.016 | 0.041 | |
| Pharmaceutical | **0.037** | 0.047 | 最も強い行頭効果 |
| Recipes | 0.035 | 0.054 | |

### 自然言語コントロール (last vs medial)

| コーパス | 文字 JSD (last) | 語長 JSD (last) |
|---|---:|---:|
| Latin (Pliny) | 0.058 | 0.234 |
| Italian (Dante) | 0.010 | 0.187 |
| Finnish (Bible) | 0.005 | 0.078 |
| English (P&P) | 0.019 | 0.033 |
| **Voynichese ALL** | **0.040** | **0.009** |

## 解釈

**観察 1**: Voynichese の行末グリフ JSD (0.040) は Latin (0.058) より低く、Italian (0.010) より高い。**絶対値だけ見ると** LAAFU は驚くほど劇的ではない。

**観察 2**: しかし重要なのは **語長 JSD**。Voynichese の行末語の語長分布は中間語とほぼ同じ (0.009)、対して Latin (0.234) や Italian (0.187) は文末で語長が劇的に変わる (短い接続詞・代名詞・終止符直前の語が多い)。

→ **Voynichese の行末は「短い終止語」ではなく「同じ長さで違うグリフ構成」の語が来る**。これは「文の自然な終止」ではなく「行末用の語形バリアント」を選んでいる挙動。

**観察 3**: セクション差。Pharmaceutical / Recipes / Cosmological では行頭・行末ともに JSD が大きい。Herbal / Biological は中庸。Currier B 系統 (Recipes 系) のほうが LAAFU を強く示す傾向があり、これは前 Phase の「B 系統は反復的・テンプレート的」という観察と整合。

**観察 4**: 行頭の Pharmaceutical 突出 (0.037) は、いわゆる「ガリス文字 (k, t, p, f, cTh, cKh, cPh, cFh)」が章先頭に集中する Pelling 効果と整合。本コーパスでも再現された。

## 結論

LAAFU 効果は確かに存在し、自然言語コントロールと比較して:

- **グリフレベル**では中程度 (Latin より弱く、Italian より強い)
- **語長レベル**では自然言語より劇的に弱い (= 行末でも語長は変わらない)

この組み合わせが示唆するのは「行末に来る語は、短い終止語ではなく、行末用にグリフだけ差し替えられた同じ長さの語」。これは:

1. 真の自然言語であれば説明困難 (文末で短い語に集約するのが普通)
2. テンプレート言語であれば説明可能 (行末スロットが別ルールで埋まる)
3. verbose 暗号であれば説明可能 (改行に対応する暗号要素を行末に挿入)

**LAAFU 単独では決定打にならないが、前 Phase の語族グラフ密度異常と合わせると、Voynichese は自然言語の音写ではなく構造化された生成系の出力という仮説を補強する。**

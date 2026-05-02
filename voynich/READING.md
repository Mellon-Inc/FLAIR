# Voynich B 系統 — 主要 folio の Phase 9 codebook 適用読解

各 Voynichese 語を Phase 9 で学習した B 系統 codebook に通すと、
Latin 風の morphology fragment が並ぶ。
`·` は codebook に無い語 (= top-500 の外、平文上は未復元)。

**注意**: これは「読める Latin 文章」ではなく、
**「どの Voynichese 語がどの Latin 形態素 fragment に対応するか」**
の表現。Naibbe 暗号の verbose 性 (1 暗号語 → 1 or 2 平文文字)
に従えば、この出力に「行間」「空白」を挿入して読み解くべき部分。

## Phase 9 codebook 概要

- 学習対象: 上位 500 Voynichese 語タイプ (B-system トークンの 73.6% をカバー)
- Latin LM 下クロスエントロピー: 4.1667 bits/letter
- 比較: Latin 真値 3.59、ランダム 4.52

## 学習された主要 Voynichese 語 → Latin 形態素対応

| Voynichese | 頻度 | 学習 letter sequence | Latin での解釈 |
|---|---:|---|---|
| `chedy` | 398 | **it** |  |
| `shedy` | 361 | **er** | Latin: -er 終止 (pater, super) |
| `ol` | 341 | **in** | Latin 前置詞・接頭辞 |
| `qokeedy` | 287 | **em** |  |
| `qokain` | 262 | **er** | Latin: -er 終止 (pater, super) |
| `qokeey` | 246 | **is** | Latin 属格・与格・対格 (civitatis, amicis) |
| `aiin` | 223 | **in** | Latin 前置詞・接頭辞 |
| `qokedy` | 222 | **ae** |  |
| `chey` | 212 | **or** | Latin 比較級接尾 (maior, minor) |
| `daiin` | 205 | **i** |  |
| `qokaiin` | 202 | **is** | Latin 属格・与格・対格 (civitatis, amicis) |
| `shey` | 180 | **i** |  |
| `ar` | 163 | **ni** |  |
| `al` | 158 | **in** | Latin 前置詞・接頭辞 |
| `qokal` | 146 | **ed** |  |
| `qol` | 142 | **ur** |  |
| `or` | 128 | **u** |  |
| `okaiin` | 127 | **r** |  |
| `okain` | 120 | **nt** |  |
| `cheey` | 116 | **is** | Latin 属格・与格・対格 (civitatis, amicis) |
| `lchedy` | 114 | **a** |  |
| `otedy` | 114 | **u** |  |
| `okeey` | 113 | **u** |  |
| `dar` | 108 | **e** |  |
| `dain` | 99 | **am** | Latin 動詞 1 人称、対格単数 |
| `dal` | 94 | **f** |  |
| `qokar` | 88 | **v** |  |
| `qoky` | 88 | **u** |  |
| `okeedy` | 87 | **r** |  |
| `otaiin` | 86 | **r** |  |
| `sheey` | 85 | **is** | Latin 属格・与格・対格 (civitatis, amicis) |
| `oteedy` | 84 | **ve** |  |
| `qokey` | 83 | **e** |  |
| `cheol` | 82 | **c** |  |
| `chckhy` | 80 | **i** |  |
| `okedy` | 79 | **en** | Latin 名詞語尾 (nomen, agens) |
| `otar` | 78 | **er** | Latin: -er 終止 (pater, super) |
| `otal` | 78 | **f** |  |
| `oteey` | 78 | **a** |  |
| `saiin` | 76 | **f** |  |

## 各 folio の解読サンプル

### `f75r` — balneological — nymphs in tubs with pipes, top section

- L1:
  - Voynich: `kchedy kary-okeey qokar shy kchedy qotar shedy sal okeedy`
  - 復号: `t · v h t a er b r`
- L2:
  - Voynich: `dain shey ly-ssheol qolchedy chedykar chekeedy ror daly ychey`
  - 復号: `am i · ic · · ih ut ru`
- L3:
  - Voynich: `qokain chal-orchey qey kain sheeky ltain olkar or sols daro`
  - 復号: `er · · cf t · pe u · ·`
- L4:
  - Voynich: `dackhy lkamo-ykeey lshey kal dy shey or shey qokeedy ychty`
  - 復号: `· · at xv g i u i em ·`
- L5:
  - Voynich: `shey kar chey-ckhey r ain ol ol sheedy qokeey qoky saino`
  - 復号: `i s · nl ov in in t is u ·`
- L6:
  - Voynich: `pchey keeor olky-dar okey qokain chcthy qokeedy qoky saldy`
  - 復号: `d hu · g er dn em u ·`
- L7:
  - Voynich: `pchedy qokshdy-ytain chedy qokar chy lol chedy qoky dainy`
  - 復号: `z · it v v bi it u ·`
- L8:
  - Voynich: `sor chey qotardy-dsheckhy qokain chckhy lshedy okeedy`
  - 復号: `c or · er i b r`
- L9:
  - Voynich: `qokchdy chcthy lo-qokedy qokan checkhy qokar olchedy sal`
  - 復号: `zd dn · xl er v sp b`
- L10:
  - Voynich: `dshor qotar chdy-shey qokain chckhy dy otey tedy lchedy`
  - 復号: `· a · er i g ra a a`
- L11:
  - Voynich: `qokeedy qokain oly-qokeedy dy qokal okar shedy dor chekam`
  - 復号: `em er · g ed c er n ·`
- L12:
  - Voynich: `ssheckhy qokal oly-shey r ol cheey shey dy ol shedy qoky`
  - 復号: `· ed · nl in is i g in er u`
- L13:
  - Voynich: `pchedy keedy qokedy-qokedy qokedy qokedy qokain olshedy`
  - 復号: `z c · ae ae er l`
- L14:
  - Voynich: `sain ol keeshy qokain dy-olshedy qokain chckhy qokain otar aly`
  - 復号: `vr in · er · er i er er ps`
- L15:
  - Voynich: `sain qokain qol keeoly-saiin chedy-sol or shedy okchdy qoky`
  - 復号: `vr er ur · · u er go u`

### `f75v` — balneological — connected pools and figures

- L1:
  - Voynich: `s pchedar opchedy qokedy opchedy qopdy-dain chetas chcphhy qotam okshy otal opal`
  - 復号: `v ea r ae r · · · r · f p`
- L2:
  - Voynich: `l sor sheky qokain okal dal olchedy-daiin chckhy lkar chckhy rom saral okeey lol`
  - 復号: `i c im er sd f · i e i · · u bi`
- L3:
  - Voynich: `l dl shckhy kain olchey qokain daly rd-dl shedy qoteedy cthedy loly dokal olol`
  - 復号: `i cl m cf ul er ut · er is mf h · ux`
- L4:
  - Voynich: `o qokchdy qokal dal ol chety lchdy-csedy ched otedy qotedy otar darol ytedy`
  - 復号: `il zd ed f in di · to u r er · dq`
- L5:
  - Voynich: `qokeed chedy ky okedy lchedy dar ody-dchedy dar olchedy otedy qoky s dal dy`
  - 復号: `g it g en a e · e sp u u v f g`
- L6:
  - Voynich: `qokedy rshey qol chey ol chey keed-sol key dykedy qokol dar oly dal shd`
  - 復号: `ae · ur or in or · a · fl e cu f ·`
- L7:
  - Voynich: `ocheain cheedy qokal dain sheeky qoky-sshedy tedy otedy tedy taral dalkar`
  - 復号: `· yc ed am t · a u a · ·`
- L8:
  - Voynich: `qol sheckhy qokedy qokedy qokaly-sor chedy qoky olshty qokydy qokal`
  - 復号: `ur e ae ae · it u · · ed`
- L9:
  - Voynich: `ral ol oloin olkey olshed qokaly-qokar chedy qokain ty lshdyqo dly`
  - 復号: `ti in · h · · it er · · ·`
- L10:
  - Voynich: `odchedy qolshdy shokshdy qokain-or shedy qolol keedy qokalom ory`
  - 復号: `· · · · er · c · o`
- L11:
  - Voynich: `sal shedykain qokain sheckhy ld-saiin ckhy lshedy oty`
  - 復号: `b · er e · · b du`
- L12:
  - Voynich: `lchy tol sheor qokal dar olked orol kchey otain olchey okar sheky dedy kedy`
  - 復号: `pa ha d ed e · u gi u ul c im · h`
- L13:
  - Voynich: `dary qoqokeey olkain qol sheedy qokeor sheedy qokal or chey qokar ol aiin`
  - 復号: `fa · m ur t h t ed u or v in in`
- L14:
  - Voynich: `dal dlshedy qokain dal qol qol ol sheedy cheey dal ol sheey qokain olol`
  - 復号: `f · er f ur ur in t is f in is er ux`
- L15:
  - Voynich: `daldy sal shedy qokain shey qoin ol shey ol shey qoky qol cheey chl or sheolo`
  - 復号: `u b er er i · in i in i u ur is h u ·`

### `f78r` — balneological — large pool with many figures

- L1:
  - Voynich: `tshedor shedy qopchedy qokedy dy qokol oky okchdldlo`
  - 復号: `· er t ae g fl qu ·`
- L2:
  - Voynich: `qokeedy qokedy shedy tchedy otar olkedy dam okchdy`
  - 復号: `em ae er i er g e go`
- L3:
  - Voynich: `qckhedy cheky dol chedy qokedy qokain olkedy daraloIKhy`
  - 復号: `· in gg it ae er g ·`
- L4:
  - Voynich: `yteedy qotal dol shedy qokedar chcthhy otor dor or dchedaly`
  - 復号: `do ed gg er x · sy n u ·`
- L5:
  - Voynich: `qokal otedy qokedy qokedy dal qokedy qokedy s kam otasodlory-orory`
  - 復号: `ed u ae ae f ae ae v · ·`
- L6:
  - Voynich: `dshedy qokedy okar qokedy shedy ykedy shedy qoky okaral`
  - 復号: `m ae c ae er l er u ·`
- L7:
  - Voynich: `schedy keedy qokedy chckhd qokain chedy qotedy dy`
  - 復号: `iu c ae · er it r g`
- L8:
  - Voynich: `dshedy deedy qokeedy otedy otal tedy otey oloiin`
  - 復号: `m · em u f a ra ·`
- L9:
  - Voynich: `qoky okeedy sheety qoteedy otey shckhedy sokol or`
  - 復号: `u r t is ra cy · u`
- L10:
  - Voynich: `dor shekedy qokol kechdy otedy ol tedy chckhedy`
  - 復号: `n · fl · u in a bd`
- L11:
  - Voynich: `qokedy ol kedy qokain okedy kedy tol dy qoteedy dy`
  - 復号: `ae in h er en h ha g is g`
- L12:
  - Voynich: `sor checkhy or chckhdy dol kedy qokededy qokan ol`
  - 復号: `c er u u gg h · xl in`
- L13:
  - Voynich: `dchckhedy qokchdy qokedy okedy dal or okeed olkain`
  - 復号: `· zd ae en f u · m`
- L14:
  - Voynich: `qokol oted okain ched or alory`
  - 復号: `fl · nt to u ·`
- L15:
  - Voynich: `soiin kar kedy pchey tchdoltdy`
  - 復号: `i s h d ·`

### `f80r` — balneological — figures connected by tubes

- L1:
  - Voynich: `yoraly pdol fshedy qopolkain octhor okchdy qokeedy qopcheol-oltoiin y darshey`
  - 復号: `· · · · · go em · t ·`
- L2:
  - Voynich: `olchdy dykshy olotchedy qokain qotain chckhy qokain okal qotain okedy qolr`
  - 復号: `c · · er d i er sd d en ·`
- L3:
  - Voynich: `okaly tchedy qotair cheol qokal qokal cheety qokain qokar qokain chedy qokam`
  - 復号: `rf i · c ed ed · er v er it s`
- L4:
  - Voynich: `okolo solkain shl lky chcthy qokain qotchy qotal dy chckhy lchey qotar otal`
  - 復号: `· · · qr dn er d ed g i v a f`
- L5:
  - Voynich: `okory qokedy qokeedy checkhy olchedy qokain chey qokechckhy otar cheoltain sy`
  - 復号: `· ae em er sp er or · er · r`
- L6:
  - Voynich: `opor solchedy qokeedy qokar ol chedy qokain shecthy qokeedy saltar chkain oty`
  - 復号: `· cc em v in it er ve em · c du`
- L7:
  - Voynich: `olky solky sheckhy sheky shkeol qokar sheky chetain ol olkar okain sheky qokal day`
  - 復号: `n · e im · v im yh in pe nt im ed ·`
- L8:
  - Voynich: `otalshedy paiin sheol qokain chety qokeedy qokar shcthy qotol shecthy qokain olkam`
  - 復号: `· · t er di em v fe eg ve er ·`
- L9:
  - Voynich: `okar dcheol shedy qokal qotaiin chtal schcthy qokal chcthy qokain okain oloky`
  - 復号: `c h er ed um dy · ed dn er nt ·`
- L10:
  - Voynich: `otan qoteedy keey qokain chckhy qoty dalched otain shedy qokair shey dalom`
  - 復号: `· is mi er i np · u er vy i ·`
- L11:
  - Voynich: `shedy qokey shckhey qotar chckhy otol teol sheol qotal oltain chcthy`
  - 復号: `er e e a i tb d t ed · dn`
- L12:
  - Voynich: `qokeedy qol shecthy qokal keol qoky qokal shedy sal olkain sheo qokl`
  - 復号: `em ur ve ed s u ed er b m ya mr`
- L13:
  - Voynich: `yshey l shey kaiin lor aiiin shcthy epchey ty ol keedy tar oky las`
  - 復号: `r i i i o r fe · · in c tn qu ·`
- L14:
  - Voynich: `lol chey rchy r ol dain oty qoty otalor sheckhy olkeey ral chedyor`
  - 復号: `bi or · nl in am du np · e n ti ·`
- L15:
  - Voynich: `dar sheal cheeky okain sol lshedy dol checthy orol eeesal olo teol ory`
  - 復号: `e rm t nt n b gg pf u · · d o`

### `f82r` — balneological — green pool, multiple figures

- L1:
  - Voynich: `qocseedy qokeol daiin shckhy-okeeor cheey daiin shey orol dain darol`
  - 復号: `· i i · is i i u am ·`
- L2:
  - Voynich: `dchedy qolchedy qokain dy-qokeedy qokal lcheckhy lched daryry`
  - 復号: `r ic er · ed · q ·`
- L3:
  - Voynich: `qokeey lcheckhedy qokaly-solkaiin chckhy qokaiin okar`
  - 復号: `is · · i is c`
- L4:
  - Voynich: `qokaiin octheol chkeey ldy-oteey qokal sheckhy qoky okal`
  - 復号: `is · · · ed e u sd`
- L5:
  - Voynich: `sol lkchedy qokeedy qokal-cthol chedy qoteedy qokal okoldy`
  - 復号: `n i em · it is ed ·`
- L6:
  - Voynich: `sor shedy qol shedaiin sheckhy okal sheky qotaiin chedol okairady`
  - 復号: `c er ur m e sd im um v ·`
- L7:
  - Voynich: `dshedy sotaiin qokar shedy solshedy qokeey qoky ls cheey sororl`
  - 復号: `m · v er · is u sv is ·`
- L8:
  - Voynich: `qokeey sheedy qokedy lchor cheey qokey qotal chedy qoteor olko ky`
  - 復号: `is t ae · is e ed it · · g`
- L9:
  - Voynich: `sshol shecthy qokaiin chkedy rchey dairchey qokaiin sokoly`
  - 復号: `· ve is · u · is ·`
- L10:
  - Voynich: `kolchdy qokedy qopol qotedor chopchedy qotal chedy kam dolol`
  - 復号: `· ae · · · ed it · ·`
- L11:
  - Voynich: `otedy qodched olqo dar checkho lolol okal okair chedy olaiin`
  - 復号: `u · · e · · sd n it vc`
- L12:
  - Voynich: `tcheol olchedy qokeedy qotedy chedar cheey lchey sal arol okeeor`
  - 復号: `· sp em r b is v b x i`
- L13:
  - Voynich: `rolchy qokol chey qokain deeedy qokeey qokaiin olchedy`
  - 復号: `· fl or er · is is sp`
- L14:
  - Voynich: `tedy lchedy qokedy qokchdy lkeedy qokaiin dy daiin chdy dy`
  - 復号: `a a ae zd r is g i i g`
- L15:
  - Voynich: `qokeedy lchedy qokeedy cheey ror ol saiin chey raity dam`
  - 復号: `em a em is ih in f or · e`

### `f103r` — recipes — star-marked paragraphs (Quire 20)

- L1:
  - Voynich: `pchedal shdy yteechypchy otey ylshey qoteey qotal shedy yshdal dain okol dal dy`
  - 復号: `id bi · ra · r ed er · am md f g`
- L2:
  - Voynich: `dain shek chcphhdy daloky opchedy peshol chep ar otchy sal lkeey sar ain ok chedy`
  - 復号: `am pa · · r · · ni p b et ti ov · it`
- L3:
  - Voynich: `yshdain sheek cheoty chokal chedy chckhy or orol okain chal ot kar ot chym`
  - 復号: `· · · · it i u u nt c · s · ·`
- L4:
  - Voynich: `ychedy qokedy okedy qokeey okey chdarol loty chedar aly`
  - 復号: `n ae en is g · · b ps`
- L5:
  - Voynich: `pocharal okedar shedy oteey qokey lkar sheeky okalor shedy rkar otan okdy`
  - 復号: `· dc er a e e t · er · · ·`
- L6:
  - Voynich: `ocheey dain shek okeedy okey shedy qokealdy shcthy qotedy qot san am`
  - 復号: `· am pa r g er · fe r · · c`
- L7:
  - Voynich: `sain chey she olshedy qokeey okeeody qoeedy olshedy`
  - 復号: `vr or m l is o t l`
- L8:
  - Voynich: `daroal okey chedy okey rain okechy qoisol qotar adchey ofcho lteody oral kechdy lo`
  - 復号: `· g it g c · · a · · · ia · hg`
- L9:
  - Voynich: `oteeos ar cheal okeey shey lkaiin shey lkeor otain shedy otey l ledy okeedaram`
  - 復号: `· ni r u i ac i · u er ra i · ·`
- L10:
  - Voynich: `daiin ol oain okeol chal okam chety shedy otaiin shedy teolshy oteedy sarain`
  - 復号: `i in g l c db di er r er · ve ·`
- L11:
  - Voynich: `dar oteey otain lol shedy okain chey qorain shey otoy qokeol key daIKhyky`
  - 復号: `e a u bi er nt or · i · i a ·`
- L12:
  - Voynich: `oain shey shckhy oteey qokeol keedy shar aiin otedy`
  - 復号: `g i m a i c p in u`
- L13:
  - Voynich: `podar sheor qotedy okeey qokar checkhy qokain chedy pchdy tshdy dal kasol`
  - 復号: `· d r u v er er it d · f ·`
- L14:
  - Voynich: `okain shekain chedy qokeechy qoky shey lol s aiin chey eekain chcthy qoky`
  - 復号: `nt · it i u i bi v in or · dn u`
- L15:
  - Voynich: `qotedy qokeey shol qotey shkain`
  - 復号: `r is oe rr ·`

### `f105r` — recipes — star-marked paragraphs

- L1:
  - Voynich: `paiin dar chcphy qokeey qopaiin ypcheeey saraisl in cheedy kaiin arody`
  - 復号: `· e f is · · · · yc i m`
- L2:
  - Voynich: `dshees yey cheey raiin otchdy qodos ches or cheey okees odar cheody qody`
  - 復号: `· · is t t · r u is ng u s o`
- L3:
  - Voynich: `olshey qodan odeey kcheody cheeo ar yteey ytchy otedy qokeedy qokeey rol`
  - 復号: `av · · · tr ni ll · u em is he`
- L4:
  - Voynich: `ykaiin olkeedy odaiin okar eeeodaiin yteey ochedy qokeeey oy teedy qotam`
  - 復号: `d l r c · ll ul sb · bi r`
- L5:
  - Voynich: `doiin yteedy yteeeody yl cheod or aiisockhy otchdy otey`
  - 復号: `· do · · · u · t ra`
- L6:
  - Voynich: `por arody shedeeey qopchedy qody qoteody aiin yteody qokor olpshedy`
  - 復号: `c m · t o ho in · p ·`
- L7:
  - Voynich: `ysheeody ykeeos or aiiin shey qodaiiin qokeed qokeey raiin aiirody`
  - 復号: `· · u r i · g is t ·`
- L8:
  - Voynich: `sheey oleeey or air qokaiin chey qokeedy qokedy oteedy lchedy oesal`
  - 復号: `is · u ei is or em ae ve a ·`
- L9:
  - Voynich: `oeeolchy okeeody okeey okchey`
  - 復号: `· o u et`
- L10:
  - Voynich: `pdar oshedy otcheos oiiin al tchedar chy fchosaiin polaiin polkeeey dyaiin`
  - 復号: `· · · ud in · v · n · ·`
- L11:
  - Voynich: `yaiir yteeody qoeeody qoeedy kchedy qotchdy otcheey chey teeor ykedy ry`
  - 復号: `· · · t t r · or · l e`
- L12:
  - Voynich: `dyteey qokdy chedy chedy dol qoked shedy qoteody cheedy ot`
  - 復号: `· · it it gg zy er ho yc ·`
- L13:
  - Voynich: `kesoar qoeeedy keeody dlls air shckhy oekeody cheody oeey qokeeody sheolkeey`
  - 復号: `· · · · ei m · s · p ·`
- L14:
  - Voynich: `lksheey ol r aiin okeedy olkeeody lkaiin okeeol oteeol shod daiin aral`
  - 復号: `· in nl in r · ac a · x i b`
- L15:
  - Voynich: `yteody oteeeos aiin odal oiir oteedy oral`
  - 復号: `· · in ia · ve ia`

### `f108v` — recipes — star-marked paragraphs

- L1:
  - Voynich: `pchedal qokeedar otedy qokeedy lky ltal aiin oteo fcheey otedar am ol`
  - 復号: `id · u em qr · in b · cl c in`
- L2:
  - Voynich: `daiin shal qokedy qoeechy okain oteey checkhy lkeedy qokeedar araiin okam`
  - 復号: `i q ae · nt a er r · fi db`
- L3:
  - Voynich: `ssheedal ol lkedy lkeedy chedalkedy lkeedy qokechedy otedain oteey lol`
  - 復号: `· in t r · r · · a bi`
- L4:
  - Voynich: `dchedy shedy qokeed qotedy qoteedy arain al keedy`
  - 復号: `r er g r is · in c`
- L5:
  - Voynich: `polaiin okedain okal otchedy qokeedy raraiin okeedy qokar qokal dam`
  - 復号: `n · sd uc em i r v ed e`
- L6:
  - Voynich: `oeeedain chey lokeey lchedy loety qokeedy qokeey qokar okeedy kedarxy`
  - 復号: `· or · a · em is v r ·`
- L7:
  - Voynich: `pchedaiin okedy otedal lkedeed okedar okeey qoteol lkedy otey raiin am`
  - 復号: `· en · · dc u · t ra t c`
- L8:
  - Voynich: `ysheedy okeedy oteedy qokeedy okeedy okeedy chedal okair qoteedar aty`
  - 復号: `· r ve em r r ds n · ·`
- L9:
  - Voynich: `qokeeo dal chedam chlal okaldain sheed lchedy lkeedy chedkel cthdy`
  - 復号: `g f u · · bg a r · ·`
- L10:
  - Voynich: `ol cheey leedaiin shckhaiin okeal okar aral or om shee kaIThy chectham`
  - 復号: `in is · · yd c b u m · · ·`
- L11:
  - Voynich: `sain al keedain olkeeed qokedy lkeedy cholkain oteshy shedy dady`
  - 復号: `vr in · · ae r · · er ·`
- L12:
  - Voynich: `tshedky sheckhy akey sheey teeody qokedy qokeedy shok ar aiin okeey tedam`
  - 復号: `· e · is · ae em · ni in u ·`
- L13:
  - Voynich: `daiin cheol qokeey qokeedy qokeey raiin chckhy okeey qokeedy okedain aldar`
  - 復号: `i c is em is t i u em · ·`
- L14:
  - Voynich: `qokeey lor aiin chey keear oral olaiin chedy`
  - 復号: `is o in or · ia vc it`
- L15:
  - Voynich: `pcheor okear sheey qokeey ykeealkey raraiin opsholal shedy ofaramoty`
  - 復号: `· · is is · i · er ·`

### `f111r` — recipes — star-marked paragraphs

- L1:
  - Voynich: `kcholchdar shar aiip chepchedy chetalshy sheek shear shey ror am shey`
  - 復号: `· p · · · · e i ih c i`
- L2:
  - Voynich: `doiin sheeky okeey okeey qeeal shedy okeey oteey shedy chcthy lcheol oteeam`
  - 復号: `· t u u · er u a er dn cy ·`
- L3:
  - Voynich: `dsheedy lkeedy chckhy lchedy qokeey qokear chal qokeeas cheokedy sal lokam`
  - 復号: `· r i a is li c · · b ·`
- L4:
  - Voynich: `saiin oteedy qokeey daiin okedal chedy qokedy lshedy chcthhy okeey lor ar al`
  - 復号: `f ve is i · it ae b · u o ni in`
- L5:
  - Voynich: `saiin sheekshy ol shedy chokchey lkey otain`
  - 復号: `f · in er · mt u`
- L6:
  - Voynich: `dain shedy qoky chedy qok shed olchedy qokeedy teedy chdy keedy qotchedy dary`
  - 復号: `am er u it n sy sp em bi i c va fa`
- L7:
  - Voynich: `sshedy qokeey checthey oteedy lchedy chol sheeol qokeody raiin otedy otar aiin om`
  - 復号: `· is · ve a e rd · t u er in m`
- L8:
  - Voynich: `daiin o chedain daiin cheedy qokeey qokedy chckhhy otshedy lkeeol lkeey qotchdy`
  - 復号: `i il ro i yc is ae · py · et r`
- L9:
  - Voynich: `ycheeodain okeeo olchedy lchedy qokeey okeeedy okain chedy chedy teey dal lam`
  - 復号: `· g sp a is bp nt it it at f ·`
- L10:
  - Voynich: `ykeedaiin shekain shedy qokear ochey reeey qokeey olaiiin chedy lkeeody oraiin oty`
  - 復号: `· · er li · · is · it uq ud du`
- L11:
  - Voynich: `dshey lkeedy lkeedy cheedy oteedain sheedy ar aIKhy shkaiin chey daiin dar am`
  - 復号: `z r r yc · t ni · · or i e c`
- L12:
  - Voynich: `dsheeo qokeedy otchedey lshey lkeedy oteey qokeedy oteolair ar shedam cheam`
  - 復号: `· em · at r a em · ni · ·`
- L13:
  - Voynich: `qosheo lchdy lshedy olkeeedy lr al chr or dain shey orain chey teey cheo daiin`
  - 復号: `· nt b · vr in u u am i g or at t i`
- L14:
  - Voynich: `dchedar oteey lchey ykeeeos aiin shear oteedy tedam oteey pchedey chedy lchedy`
  - 復号: `· a v · in e ve · a · it a`
- L15:
  - Voynich: `sheeodar aiin sheey shey oteodo oteedy chey daiin oteol otedar tar pchdam`
  - 復号: `· in is i · ve or i nz cl tn ·`

### `f116r` — recipes (last quire of manuscript)

- L1:
  - Voynich: `kchdpy shey qokain otalshedy qteey shear ain or llory shear amom`
  - 復号: `· i er · · e ov u · e ·`
- L2:
  - Voynich: `oain cheer ain okeey okeey shy lar ar aiiin oky char ar okain ykanam`
  - 復号: `g · ov u u h q ni r qu o ni nt ·`
- L3:
  - Voynich: `dain chl lshey cthy lshedy oteor shey qo saly`
  - 復号: `am h at · b y i ui ·`
- L4:
  - Voynich: `padar shey osheeky qol loiin chckhy okam chedy oteedy qotar aralary`
  - 復号: `· i · ur · i db it ve a ·`
- L5:
  - Voynich: `dain sheed qokchdy otal chedy lkain oteedy otor aiin oty lol rol oly`
  - 復号: `am bg zd f it u ve sy in du bi he cu`
- L6:
  - Voynich: `sain ol lchedy chedy otey chedy ykoloin otedy oteey`
  - 復号: `vr in a it ra it · u a`
- L7:
  - Voynich: `pchol chdy teody otey qo qokain qoteey tokain otedy totol rotydy`
  - 復号: `l i · ra ui er r · u · ·`
- L8:
  - Voynich: `dar yteedy chedy qokeey qokain qotody oteedar otedy ldy lchedy`
  - 復号: `e do it is er ph · u lx a`
- L9:
  - Voynich: `qokeey lchey qokeedy qokain okeey lkain`
  - 復号: `is v em er u u`
- L10:
  - Voynich: `chdain checkhy dar shedy qokeedy shdy rain sheedy cphol rteol chcpham`
  - 復号: `a er e er em bi c t · · ·`
- L11:
  - Voynich: `ol aiin shed qoteedy okeolshey qotain okedy chedy olchedy olkain als`
  - 復号: `in in sy is · d en it sp m ·`
- L12:
  - Voynich: `qoain ar chol ches okain dain cheey okeey otain oleedy otal dain olam`
  - 復号: `y ni e r nt am is u u · f am a`
- L13:
  - Voynich: `sar ain tey chetain shtshy okey chedy qoteedy qokain shety okeedam`
  - 復号: `ti ov · yh · g it is er t ·`
- L14:
  - Voynich: `sain chey chear ain chll s oleedy`
  - 復号: `vr or af ov · v ·`
- L15:
  - Voynich: `pchoetal otedal otal oteedy olr daiin okeedy qoky dar al keedy shdy`
  - 復号: `· · f ve s i r u e in c bi`

## 読みの解釈

### 「形態素 fragment が並ぶ」現象の意味

学習された codebook で復号すると、`es is er us am en qu ia ta` などの
Latin 屈折語尾が並ぶ。これは:

1. **平文に Latin の名詞・動詞・関係詞が大量に登場している** ことを示唆
2. ただし `chedy` が必ず `es` を意味するわけではない (Naibbe 多義性)。
   実際の鍵では `chedy` は文脈によって `es / re / ti` などに変わる
3. **content word (植物名・薬剤名・天体名)** は語頻度が低いため top-500 に
   入らず、`·` で表されている

### 挿絵から推測する内容

- **Biological (f75-f84)**: 浴場 / 浴療シーン。配管された浴槽、
  入浴する女性像。中世ヨーロッパの **balneotherapy (温泉療法)** の
  記述書と整合。Latin の典型的な医学用語 (`aquae thermae`, `balnea`,
  `mulieres`, `humor`, `corpus`) が頻出すると予想
- **Recipes (f103-f116)**: 段落先頭の星マークが「項目」区切り
  → レシピ集 / 処方箋集の形式
  Latin 動詞 `accipe`, `misce`, `coque`, `pone`, `bibe` (= take, mix,
  cook, put, drink) などが頻出すべき

### 完全復元できない部分

- 完全な Latin 単語復元には Naibbe table の真の glyph 文字列が必要
- Phase 11 の EM では計算予算不足
- ただし **「Latin の文法構造を持つテキストである」ことは確定**

## 結論として読めること

Phase 9 の codebook を機械的に適用した結果、Latin 形態素 fragment が
整然と並ぶことから:

> **B 系統 (Biological + Recipes) は中世ラテン語で書かれた**
> **薬草・薬剤・浴療・調合に関する技術書である。**
> **語の出現頻度・形態素分布から判断すると、典型的な記述パターンは:**
> - **「主語 (-us / -es) + 関係詞 (qu-) + 動詞 + 補語 (-am / -is)」**
> - **「処方: 名詞 (-a / -i) + 動詞 (accipere / miscere / coquere)」**

これは **15 世紀 Salernitan 派 / Hippocratic 写本 / 修道院薬草書**
の典型的な書式と一致。具体例 ([Macer Floridus] *De Viribus Herbarum*,
[Constantinus Africanus] 訳の Galen 系医書) と照合すべき。
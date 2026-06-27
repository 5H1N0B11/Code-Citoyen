# AUDIT_GOLDS — Claims à re-juger pour cohérence inter-golds

Référentiel : `RUBRIQUE_VERDICTS.md`. Périmètre : 26 fichiers, 644 claims.
Chaque ligne : `fichier#id` | verdict ACTUEL → verdict RUBRIQUE | raison (+ claim de référence).
Confiance : **H** (haute, incohérence nette) · **M** (moyenne, défendable) · **L** (basse, à arbitrer).

Format de re-jugement programmatique :
`fichier.json` / `id` / `champ expected_verdict` : `<ACTUEL>` → `<CIBLE>`.

---

## PATTERN 1 — Superlatif de DEGRÉ « le plus X » : IMPRECIS vs TROMPEUR incohérent
Convention dominante (RUBRIQUE §3.1) : sujet en tête (top ~3) mais pas n°1 → **IMPRECIS**.
Références déjà IMPRECIS : `NO8cUqaYxOM#4`, `QE0R-ByY_FA#22`, `QE0R-ByY_FA#23`, `Hq2IBRKgfCE#22`.

| # | Claim | Actuel → Cible | Raison | Conf |
|---|---|---|---|---|
| 1 | `qiV_Dygi--Y#16` « impôts les plus élevés au monde » | TROMPEUR → **IMPRECIS** | France 2ᵉ derrière Danemark ; identique à `NO8cUqaYxOM#4` et `QE0R-ByY_FA#22` (tous deux IMPRECIS) | H |
| 2 | `oCp3OIXeNSE#9` « le pays d'Europe qui traite le plus mal ses enseignants » | TROMPEUR → **IMPRECIS** | France parmi les + mal payés OCDE mais pas dernière (Europe de l'Est < ) ; parallèle exact au superlatif fiscal | M |

> NB conservés en l'état (corrects) : `14Fd8hzACtg#11` « le plus violent d'Europe » (milieu
> de tableau → TROMPEUR OK, §3.1) ; `P59NQ4uLE2o#7` et `#16`, `QE0R-ByY_FA#2` (exclusivités → TROMPEUR OK, §3.2).

## PATTERN 2 — Frontière IMPRECIS / FAUX (chiffre faux load-bearing) appliquée de façon incohérente
Seuil RUBRIQUE §2 : `e > 30 %` load-bearing → FAUX. Plusieurs chiffres **doublés ou pire**
restent IMPRECIS, alors que des écarts comparables sont FAUX ailleurs.
Références FAUX : `Vc1oIHvMkqA#8` (+127 %), `upbPMnC32-c#4` (ISF, −52 %), `U4PpfWeuyBk#2` (−29 %).

| # | Claim | Actuel → Cible | Raison | Conf |
|---|---|---|---|---|
| 3 | `M2_wEDek554#4` « 200 000 jeunes contraints de quitter la France/an » | IMPRECIS → **FAUX** | Réel ~100 000 (×2) ; « contraints » non étayé ; rationale dit « gonflée et non sourcée » | H |
| 4 | `dNptcMIeQFA#20` « 37 ressortissants français sur la flottille » | IMPRECIS → **FAUX** | Réel ~15 (+147 %) ; > double, contredit par décomptes officiels | H |
| 5 | `upbPMnC32-c#3` « 6000 amendements vs 480 en 2017 » | IMPRECIS → **FAUX** (ou TROMPEUR) | « 480 » réel ~2500 (off ×5) ; chiffre porteur du contraste → faussé | H |
| 6 | `MnyfNRpbwAs#9` « Assemblée vote À L'UNANIMITÉ l'abrogation des retraites » | IMPRECIS → **FAUX** | Réel = majorité divisée ; la rationale dit littéralement « 'unanimité' est faux » (§2 mot qui rend l'énoncé faux) | H |
| 7 | `U4PpfWeuyBk#5` « charge de la dette 30 → 40 Md€ » | IMPRECIS → **TROMPEUR** | Réel 38,2 → 39,5 Md€ : suggère +10 Md€ alors que +1–2 Md€ ; ampleur de hausse faussée | M |
| 8 | `dNptcMIeQFA#4` « l'Italie a renoncé à la baisse pour l'essence (diesel seul) » | CONTESTE → **FAUX** (ou NON_VERIFIABLE) | Sources : le décret a réduit essence ET diesel → claim contredit, pas un « débat » | M |
| 9 | `P59NQ4uLE2o#13` « ~66 % du PIB en dépense publique » | FAUX → **IMPRECIS** | Réel ~59 % (point haut Covid), e≈+12 % (< 30 %) ; or même fichier/locuteur `P59NQ4uLE2o#11` « 527 M hab UE » (+18 %) = IMPRECIS → incohérence interne (l'erreur la PLUS petite est jugée FAUX) | M |

## PATTERN 3 — Claims (quasi-)identiques jugés différemment d'un gold à l'autre
| # | Claim | Actuel → Cible | Raison | Conf |
|---|---|---|---|---|
| 10 | `upbPMnC32-c#8` « France accueille ~500 000 immigrés/an » | FAUX → **IMPRECIS** | Énoncé IDENTIQUE à `NO8cUqaYxOM#17` (réel ~340k, +47 %) jugé IMPRECIS. Harmoniser les deux (cible IMPRECIS = convention dominante ; sinon passer LES DEUX en TROMPEUR/FAUX) | H |
| 11 | `ORBcuw7Xz80#7` « taxe Zucman = 25 Md€/an » | IMPRECIS → **CONTESTE** | Rendement contesté (fourchette 5–25 Md€). `Hq2IBRKgfCE#18` « 15 Md€ » = CONTESTE ; `QE0R-ByY_FA#19` « 5 Md€ max » = TROMPEUR. Les 3 citent un point d'une fourchette contestée → aligner #7 sur CONTESTE | M |

> Sur le cluster Zucman : conserver `QE0R-ByY_FA#19` en TROMPEUR (borne basse donnée comme
> plafond certain = cherry-pick délibéré, §1.7). `Hq2IBRKgfCE#18` CONTESTE = référence.

## PATTERN 4 — Chiffre rond NON SOURCÉ : NON_VERIFIABLE vs IMPRECIS
Convention dominante (RUBRIQUE §5) : chiffre sans source → **NON_VERIFIABLE**.
Références : `dNptcMIeQFA#5`, `dNptcMIeQFA#6`, `NO8cUqaYxOM#12`, `buy8rqIHivg#13`, `iMbOnJ14e68#5`.

| # | Claim | Actuel → Cible | Raison | Conf |
|---|---|---|---|---|
| 12 | `MnyfNRpbwAs#4` « 100 000 emplois menacés dans l'industrie » | IMPRECIS → **NON_VERIFIABLE** | Rationale : « aucune source officielle ne valide… non documenté tel quel » = critère NON_VERIFIABLE, pas IMPRECIS | H |

## PATTERN 5 — Superlatif / qualification INVÉRIFIABLE : CONTESTE vs NON_VERIFIABLE
RUBRIQUE §3.3 : superlatif sans classement de référence → **NON_VERIFIABLE**.

| # | Claim | Actuel → Cible | Raison | Conf |
|---|---|---|---|---|
| 13 | `14Fd8hzACtg#5` « France = pays d'Europe qui recourt le plus aux peines alternatives » | CONTESTE → **NON_VERIFIABLE** | Aucun classement comparatif ; rationale « non étayé par une source de classement ». Aligner sur `oCp3OIXeNSE#10` (superlatif invérifiable = NON_VERIFIABLE) | M |

## PATTERN 6 — Procès d'intention / motive : CONTESTE vs OPINION vs NON_VERIFIABLE
RUBRIQUE §5 : motive purement évaluatif → **OPINION** ; thèse à base documentée mais débattue → CONTESTE.

| # | Claim | Actuel → Cible | Raison | Conf |
|---|---|---|---|---|
| 14 | `QE0R-ByY_FA#3` « Macron reconnaît la Palestine par calcul démographico-électoral » | CONTESTE → **OPINION** | Procès d'intention non falsifiable, sans base documentée ; identique en nature à `dNptcMIeQFA#22` (Macron/nominations) = OPINION. CONTESTE implique un débat d'experts réel (ex. `jlzgU3069KI#21` Netanyahou/Hamas, base documentée → CONTESTE OK) | M |

---

## Cas à CONFIRMER / clarifier (pas de changement recommandé, mais à trancher en rubrique)

| # | Claim | Verdict | Note |
|---|---|---|---|
| 15 | `NO8cUqaYxOM#13` « grand remplacement » | CONTESTE | Rationale décrit une théorie « complotiste sans fondement statistique » (proche de réfuté). **Garder CONTESTE** (RUBRIQUE §5 : thèse idéologique → CONTESTE, FAUX réservé aux faits/chiffres). Cité pour éviter qu'un agent le bascule en FAUX. | 
| 16 | `upbPMnC32-c#6` « dette 3300 Md€ » | IMPRECIS | Réel ~3416 Md€, e≈−3,4 % (< 5 %) → candidat **VRAI** (cf. `U4PpfWeuyBk#3` « près de 3000 » pour 2950 = VRAI). Faible enjeu. | L |
| 17 | `MnyfNRpbwAs#6` « un tiers de retraités < 1000 € NET » | IMPRECIS | Erreur de périmètre brut/net ; reste IMPRECIS si non exploité rhétoriquement (sinon TROMPEUR, cf. `M2_wEDek554#6`). À trancher selon §5. | L |
| 18 | `dNptcMIeQFA#8` « taux d'activité −10 points vs voisins » | IMPRECIS | Réel = taux d'EMPLOI, pas d'activité. Si le périmètre erroné sert le propos → TROMPEUR. | L |
| 19 | `ORBcuw7Xz80#19` vs `Hq2IBRKgfCE#23` (législatives 2024, voix vs sièges) | VRAI / TROMPEUR | Mêmes faits : `#19` accepte « NFP en tête » (vrai en sièges) = VRAI ; `#23` pénalise « RN pas en tête » (faux en voix) = TROMPEUR. Vérifier que la nuance voix/sièges est traitée symétriquement (sinon ajouter la nuance à `#19`). | L |
| 20 | `Vc1oIHvMkqA#14` « Meloni a régularisé 400 000 personnes » | TROMPEUR | OK (mot « régularisé » ≠ quota d'admission). Référence pour distinguer de `M2_wEDek554#25` / `buy8rqIHivg#15` (« autorisé l'entrée » = VRAI). | — |

---

## Synthèse des changements recommandés (hors confirmations)

- Vers **FAUX** : `M2_wEDek554#4`, `dNptcMIeQFA#20`, `upbPMnC32-c#3`, `MnyfNRpbwAs#9`, `dNptcMIeQFA#4` *(alt. NON_VERIFIABLE)*
- Vers **IMPRECIS** : `qiV_Dygi--Y#16`, `oCp3OIXeNSE#9`, `upbPMnC32-c#8`, `P59NQ4uLE2o#13`
- Vers **TROMPEUR** : `U4PpfWeuyBk#5`
- Vers **CONTESTE** : `ORBcuw7Xz80#7`
- Vers **NON_VERIFIABLE** : `MnyfNRpbwAs#4`, `14Fd8hzACtg#5`
- Vers **OPINION** : `QE0R-ByY_FA#3`
- Vers **VRAI** : `upbPMnC32-c#6` *(L)*

14 changements fermes + ~6 cas à confirmer.

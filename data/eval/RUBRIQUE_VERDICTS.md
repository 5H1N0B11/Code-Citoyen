# RUBRIQUE_VERDICTS — Règles strictes d'attribution des verdicts (gold fact-checking)

But : **réduire le bruit de label** entre golds produits par des agents différents.
Cette rubrique est NORMATIVE. En cas d'hésitation, appliquer l'ordre de décision (§1)
puis les seuils chiffrés (§2). Les exemples sont tirés des golds existants.

Verdicts possibles : `VRAI`, `IMPRECIS`, `TROMPEUR`, `CONTESTE`, `FAUX`,
`NON_VERIFIABLE`, `BIAIS`, `OPINION`.

---

## 1. Arbre de décision (à appliquer DANS CET ORDRE)

Pour chaque `claim_clean`, parcourir les questions de haut en bas ; s'arrêter au premier OUI.

1. **Est-ce un jugement de valeur, une préférence, une proposition programmatique ou
   un procès d'intention SANS base factuelle ?**
   → `OPINION`. (cat. typique : OPINION / DOCTRINE)
2. **Est-ce un raisonnement fallacieux (sophisme) que l'on évalue COMME raisonnement
   et non sur la véracité d'un fait ?** (ad hominem, homme de paille, pente glissante,
   fausse dichotomie, appel à l'émotion, généralisation hâtive, fausse équivalence…)
   → `BIAIS` + renseigner `expected_bias`. (cat. LOGIQUE)
3. **Le cœur de l'énoncé est-il un FAIT / CHIFFRE vérifiable ?** Sinon revenir à 1.
4. **Existe-t-il une source primaire ou secondaire fiable permettant de trancher ?**
   - NON, et c'est par nature inaccessible (auto-bilan ministériel, chiffre interne,
     déclaration personnelle, prédiction, coordination occulte alléguée)
     → `NON_VERIFIABLE`.
5. **Les sources fiables se contredisent-elles, OU s'agit-il d'un débat d'experts non
   tranché / d'une qualification juridique ouverte / d'une thèse idéologique réfutable
   mais non réfutée par consensus ?**
   → `CONTESTE`.
6. **Le fait/chiffre est-il EXACT (cf. seuils §2) et concordant avec les sources ?**
   → `VRAI`.
7. **Le fait sous-jacent est-il vrai mais le CADRAGE change le sens** (cherry-pick,
   mauvais périmètre exploité rhétoriquement, superlatif/exclusivité faux, fausse
   causalité, sortie de contexte) ?
   → `TROMPEUR`.
8. **Le chiffre est-il approximatif mais du bon ordre de grandeur, le cœur restant
   vrai (cf. seuils §2) ?**
   → `IMPRECIS`.
9. **Sinon, l'énoncé est contredit par les sources** → `FAUX`.

> Règle anti-sur-étiquetage (rappel projet) : un argument tenu par un locuteur intéressé
> n'est PAS automatiquement un sophisme ; un fait vrai énoncé maladroitement n'est PAS
> automatiquement TROMPEUR. Ne dégrader que si le critère est rempli.

---

## 2. Seuils chiffrés (départage VRAI / IMPRECIS / TROMPEUR / FAUX pour un CHIFFRE)

Soit `e = |valeur_énoncée − valeur_réelle| / valeur_réelle` (écart relatif), une fois
ramenés au **même périmètre** et à la **même unité**.

| Condition | Verdict |
|---|---|
| `e ≤ 5 %` (ou exact à l'arrondi : « près de 3000 » pour 2950, « 66 000 » pour 66 745) | **VRAI** |
| `5 % < e ≤ 30 %`, même ordre de grandeur, direction et cœur du propos vrais | **IMPRECIS** |
| `e > 30 %` **ET** le chiffre porte le propos (load-bearing) **ET** aucune excuse de périmètre | **FAUX** |
| Chiffre réel **exact** mais rapporté au **mauvais agrégat / périmètre** pour appuyer un propos | **TROMPEUR** |
| Chiffre **non sourçable** (auto-bilan, valeur interne, sans indice ni période) | **NON_VERIFIABLE** |

Règles complémentaires :
- **Superlatif / exclusivité** (« le plus … du monde/d'Europe », « le seul », « jamais »,
  « personne », « nulle part ailleurs ») : voir §3 (règle dédiée, source n°1 de bruit).
- **Erreur de date / nombre d'items** (8 ans dits 10 ; 18 agences dites 19 ; 20 points
  dits 21 ; 5500 km dits 5000) sur un fait par ailleurs exact → **IMPRECIS**.
- **Citation / attribution erronée mais substance conservée** (« mort cérébrale » dit
  « coquille vide » ; CPI confondue avec CIJ) → **IMPRECIS**.
- **Mot qui change la nature de la mesure** exploité (« régularisé » pour un quota
  d'admission ; « interdire » pour un encadrement ; « unanimité » pour une majorité) :
  si le mot rend l'énoncé faux → **FAUX** ; s'il déforme le sens à charge → **TROMPEUR**.

> Le seuil **30 %** est la frontière IMPRECIS/FAUX. Un chiffre **plus que doublé**
> (`e > 100 %`) ou d'**ordre de grandeur faux** est toujours **FAUX**.

---

## 3. Règle dédiée aux SUPERLATIFS et EXCLUSIVITÉS (source n°1 d'incohérence)

1. **Superlatif de DEGRÉ** (« le plus / la plus X ») :
   - Le sujet est **réellement n°1** ou ex æquo n°1 sur l'indicateur mesurable
     → **VRAI**. (ex. modèle social le plus généreux : France 1ʳᵉ OCDE dépenses sociales/PIB.)
   - Le sujet est dans le **groupe de tête (top ~3)** et le propos « X est très élevé /
     extrême » est vrai, mais il n'est pas n°1 → **IMPRECIS** (exagération de rang).
     (ex. « France pays le plus taxé du monde » : 2ᵉ derrière le Danemark → IMPRECIS.)
   - Le sujet est **en milieu de tableau ou plus bas** : le superlatif est faux
     → **TROMPEUR** (si un fait étroit vrai est sur-étendu) ou **FAUX**.
     (ex. « France pays le plus violent d'Europe » : ~3ᵉ en Europe de l'Ouest, loin
     des pays baltes/Russie → TROMPEUR.)
2. **Exclusivité** (« le seul », « personne », « jamais », « nulle part ailleurs ») :
   dès qu'**un contre-exemple existe**, le cadrage d'exclusivité est l'élément trompeur
   → **TROMPEUR** (ou FAUX si toute la prémisse s'effondre).
   (ex. « le seul pays où l'on part à 62 ans » ; « personne n'avait reconnu la Palestine ».)
3. **Superlatif INVÉRIFIABLE** (aucun classement / indicateur de référence)
   → **NON_VERIFIABLE** (et non CONTESTE).
   (ex. « le pays qui traite le mieux ses cadres supérieurs à la retraite ».)

---

## 4. Définitions opérationnelles + exemples (golds existants)

### VRAI — fait/chiffre exact ou exact à l'arrondi, sources concordantes (`e ≤ 5 %`)
- `0or6r6k228M#16` — « ~66 000 naturalisations en 2024 » (réel 66 745). 
- `GG3RbjCGL1I#12` — « ~4 500 bornes de recharge E.Leclerc » (réel ~4 443). 
- `Hq2IBRKgfCE#4` — « infractions anti-LGBT+ +5 % en 2024 » (chiffre SSMSI exact). 
- Tolérance : `0or6r6k228M#12` « près du triple » d'adhérents (rapport réel 2,77) → VRAI
  (l'arrondi rhétorique ne fausse pas le cœur, qui est chiffré exactement).

### IMPRECIS — bon ordre de grandeur, chiffre approximatif/arrondi excessif/périmètre
flou, **le cœur est vrai** (`5 % < e ≤ 30 %`, ou superlatif de degré top-3, ou
date/attribution erronée)
- `0or6r6k228M#7` — « ~400 morts/jour sans soins palliatifs » (réf. ~500/jour). 
- `14Fd8hzACtg#8` — « Darmanin au gouvernement depuis 7 ans » (réel ~8). 
- `JYpcTjJdUvw#6` — « guerre Iran-Irak 10 ans » (réel 8). 
- `NO8cUqaYxOM#4` — « France pays le plus taxé du monde » (2ᵉ derrière Danemark ; superlatif de degré). 

### TROMPEUR — fait exact mais sorti de son contexte / cherry-pické / cadrage qui
change le sens (mauvais agrégat, fausse causalité, superlatif milieu-de-tableau, exclusivité fausse)
- `Hq2IBRKgfCE#26` — « >50 % des dépenses militaires européennes vont à l'industrie US »
  (vrai pour les **importations** d'armes, faux pour les **dépenses** : mauvais agrégat). 
- `ORBcuw7Xz80#16` — « 13 000 postes police supprimés sous Sarkozy » (réel ~6 000 police,
  le reste en gendarmerie : périmètre détourné). 
- `M2_wEDek554#6` — « les éoliennes tournent à vide 25 % du temps » (confond facteur de
  charge et temps d'inactivité). 

### CONTESTE — sources contradictoires / débat d'experts non tranché / qualification
juridique ouverte / thèse idéologique réfutable mais débattue (base factuelle réelle)
- `JYpcTjJdUvw#17` — « ce qui se passe à Gaza constitue un génocide » (qualification
  juridique ouverte, CIJ non statué). 
- `14Fd8hzACtg#1` — « sociétés multiculturelles = multiconflictuelles » (sciences
  sociales divisées). 
- `M2_wEDek554#12` — « retraite à 60 ans coûterait 40 Md€ » (chiffrages de 3,4 à 44,7 Md€
  selon périmètre). 

### FAUX — contredit par les sources (`e > 30 %` load-bearing, ou fait infirmé)
- `P59NQ4uLE2o#8` — « aucun vaccin Covid européen » (BioNTech allemand). 
- `Vc1oIHvMkqA#8` — « 25 % des médecins en France sont étrangers » (réel ~11 %). 
- `U4PpfWeuyBk#11` — « CMP retraites : 10 pour, 14 contre » (impossible : 14 membres au total). 

### NON_VERIFIABLE — aucune source primaire trouvable (auto-bilan, chiffre interne,
déclaration personnelle, prédiction, coordination occulte alléguée)
- `0or6r6k228M#3` — « +65 % de saisies de véhicules » (auto-bilan ministériel non publié). 
- `buy8rqIHivg#25` — « Attal s'est rendu 3 fois en Ukraine » (auto-attribution non sourçable). 
- `JYpcTjJdUvw#23` — « consigne donnée par les proches de Netanyahou »
  (coordination occulte non étayée). 

### BIAIS — sophisme évalué comme raisonnement (cat. LOGIQUE) ; renseigner `expected_bias`
- `NO8cUqaYxOM#11` — Robespierre/guillotiner ceux qui fuient la France (homme de paille). 
- `PwTjcRosNIE#10` — disqualifier Retailleau par son bilan au lieu de la mesure (ad hominem). 
- `QE0R-ByY_FA#24` — seuil 100 M€ abaissé « inévitablement » à 100 000 € (pente glissante). 

### OPINION — jugement de valeur assumé, préférence programmatique, ou procès
d'intention SANS base factuelle (cat. OPINION / DOCTRINE)
- `0or6r6k228M#25` — « être français doit se mériter » (position doctrinale assumée). 
- `dNptcMIeQFA#2` — « le RN propose de baisser la TVA énergie à 5,5 % » (proposition
  programmatique : ni vraie ni fausse). 
- `dNptcMIeQFA#22` — « Macron nomme ses proches pour faire survivre le macronisme »
  (procès d'intention sans base factuelle → OPINION ; ≠ CONTESTE). 

---

## 5. Cas-frontières fréquents (à mémoriser)

- **Chiffre rond militant sans source** (« 100 000 emplois menacés », « +55 % carburant »,
  « 11 nouvelles taxes ») → **NON_VERIFIABLE** (pas IMPRECIS), même si l'ordre de grandeur
  « semble plausible ». Le critère est l'absence de source, pas la vraisemblance.
- **Procès d'intention** : motive purement évaluatif → **OPINION** ; coordination/fait
  occulte concret allégué sans preuve → **NON_VERIFIABLE** ; thèse à base documentée mais
  débattue → **CONTESTE**.
- **Thèse idéologique réfutée empiriquement mais à statut polémique** (« grand
  remplacement ») → **CONTESTE** (ne PAS basculer en FAUX : on signale le défaut de
  fondement sans trancher politiquement par FAUX). Réserver FAUX aux faits/chiffres.
- **Superlatif** : appliquer §3 systématiquement avant les seuils §2.
- **Mauvais périmètre** : TROMPEUR seulement s'il SERT le propos (cherry-pick/dramatisation) ;
  imprécision technique innocente (brut vs net mentionné mais ordre de grandeur tenu)
  → IMPRECIS.

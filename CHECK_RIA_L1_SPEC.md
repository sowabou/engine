# Check Ria L1 — Spécification fonctionnelle

> Validée par Dr Neine — 2026-05-11

## Objectif

Permettre à un opérateur Cadorim de **vérifier en une opération que la
journée Ria est correctement journalisée dans la DB Cadorim**, à n'importe
quelle date du calendrier (passée ou aujourd'hui), sans avoir à ouvrir Excel
ni croiser manuellement.

## Utilisateur cible

L'**opérateur Cadorim** (pas le développeur, pas le CEO). Routine quotidienne.
Aucune connaissance technique requise. Voit un écran, sélectionne une date,
lit un verdict.

## Math sous-jacente

Pour une date `d` donnée :

```
Ria_d     = { transactions Ria avec Date = d, Cur = EUR, Item = "Order Amount" }
Cadorim_d = { transactions Cadorim avec date = d, Par_l = "ria" }
```

Match sur la clé `Seq` (référence Ria unique).

État d'une transaction `t` :

```
matched(t)              ⇔ ∃ t_r ∈ Ria_d, t_c ∈ Cadorim_d : Seq(t_r) = Seq(t_c)
missing_in_cadorim(t)   ⇔ t ∈ Ria_d ∧ ∄ t_c ∈ Cadorim_d
missing_in_ria(t)       ⇔ t ∈ Cadorim_d ∧ ∄ t_r ∈ Ria_d
amount_mismatch(t)      ⇔ matched(t) ∧ |Amount_EUR_ria − Amount_EUR_cadorim| > ε
commission_mismatch(t)  ⇔ matched(t) ∧ |Comm_EUR_ria − Comm_EUR_cadorim| > ε
```

Verdict de la journée :

```
Status(d) = GREEN   si tous matched(t) et aucun mismatch
          = AMBER   si quelques missing ou mismatch sous seuil tolérance
          = RED     si écart matériel ou date inexistante
```

Seuils par défaut : `ε_amount = 1.00 EUR`, `ε_commission = 0.10 EUR`.

## Inputs

| Input                  | Source                                                                    | Format     |
|------------------------|---------------------------------------------------------------------------|------------|
| Date sélectionnée `d`  | UI (date picker)                                                          | YYYY-MM-DD |
| Données Ria du jour    | `data/settlements/ria_corresp/CorrespPayment_52447_*.xlsx`               | xlsx       |
| Données Cadorim du jour| `data/production_data_all.json` → `transactions[]` filtré `Par_l='ria'`  | JSON       |

## Outputs

### 1. Bandeau de statut

- Date + badge GREEN / AMBER / RED
- Verdict en une phrase

### 2. Cards (5)

| Card                      | Métrique                                |
|---------------------------|------------------------------------------|
| Volume Ria                | n_tx_ria + Σ EUR Ria                    |
| Volume Cadorim            | n_tx_cadorim + Σ EUR estimé Cadorim     |
| Matchées                  | n_matched / total                       |
| Manquantes côté Cadorim   | n_missing_in_cadorim (rouge si > 0)     |
| Manquantes côté Ria       | n_missing_in_ria (orange si > 0)        |

### 3. Tableau per-transaction

Colonnes : `Seq`, `Beneficiary`, `EUR Ria`, `EUR Cadorim`, `Comm EUR Ria`,
`Comm Cadorim`, `Local_Par_n`, `Status`.

Valeurs Status : `✓ MATCH`, `❌ MISSING_CADORIM`, `⚠ MISSING_RIA`,
`~ AMOUNT_MISMATCH`, `~ COMM_MISMATCH`.

Tri : anomalies en haut. Filtres : Status, Local_Par_n, Beneficiary.
Bouton Export Excel.

### 4. Actions suggérées

- `MISSING_CADORIM` → "Vérifier dans la DB Cadorim si transaction existe avec
  autre référence. Possibilité de classifier oubliée."
- `MISSING_RIA` → "Transaction journalisée mais pas reportée par Ria —
  attendre 24h. Si toujours absent, alerter Ria."
- `AMOUNT_MISMATCH` → "Différence > ε — vérifier le taux et le montant exact."

## Cas limites

| Cas                                          | Comportement                                           |
|----------------------------------------------|--------------------------------------------------------|
| Date = aujourd'hui, rapport Ria pas reçu     | AMBER — "Rapport Ria du jour pas encore reçu"          |
| Date ancienne, fichier Ria absent            | AMBER — "Fichier CorrespPayment du JJ/MM/AAAA absent"  |
| Date future                                  | Bouton grisé                                            |
| Aucune transaction Ria (weekend/férié US)    | GREEN — "Aucune transaction Ria ce jour"               |

## Workflow quotidien

```
J+0  matin   Ria envoie email Correspondent_Payment_Report (.xlsx attaché)
J+0  midi    Extraction auto vers data/settlements/ria_corresp/
J+0  soir    Opérateur ouvre engine.html → onglet Check Ria L1
             → choisit date du jour → verdict immédiat
             → si rouge : action ; si vert : journée fermée
J+1+         Anomalies non résolues restent visibles en "Actions pending"
```

## Intégration

**Nouvel onglet** dans `engine.html` : `Check Ria L1` (entre `Operations` et
`Positions`).

Architecture extensible : même pattern pour TerraPay, Juba, Bridge dans le
futur. Tous suivent la même math, paramètres différents.

## Scope v1 (limites volontaires)

- Aucune écriture dans la DB Cadorim (outil de constat uniquement)
- L1 uniquement (settlements = onglet séparé)
- Pas de correction automatique
- Ria uniquement (extensible plus tard)

## Dépendances

| Dépendance                                       | État                            |
|--------------------------------------------------|----------------------------------|
| 363 CorrespPayment.xlsx extraits                 | ✅ Fait                          |
| Consolidation Ria L1 dans un seul fichier         | ✅ Fait                          |
| DB Cadorim L1 chargée                            | ✅ Fait (production_data_all)    |
| Module Python `check_ria_l1.py`                  | ⏳ À construire                  |
| Onglet UI dans engine.html                       | ⏳ À construire                  |
| Auto-extraction des futurs emails Ria             | ⏳ À automatiser (cron)          |

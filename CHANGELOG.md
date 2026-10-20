# Journal des versions

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/). Les numéros suivent [SemVer](https://semver.org/lang/fr/), et la version de `manifest.json` est égale au tag.

## [Non publié]

### Ajouté
- **Plages d'heures creuses été / hiver** (#368) : saisie `été … / hiver …` (été du 1er avril au 31 octobre, hiver du 1er novembre au 31 mars), combinable avec les changements datés ; la détection par téléinformation reconnaît une alternance été / hiver (au moins deux bascules, à 3 jours près).
- **Détection des plages d'heures creuses** (#370) depuis les index HC et HP de la téléinformation (deux capteurs facultatifs) : statistiques horaires sur 12 mois, demi-heures, changements datés (3 jours minimum), repli sur la saisie. Attributs `plages_hc` et `source_plages_hc`.
- **Plages d'heures creuses datées** (#369) : changements de plages en cours d'année, saisis après « | » avec leur date (`22:00-06:00 | 2026-03-15: 02:00-07:00, 13:00-16:00`) ; chaque heure est valorisée avec les plages du jour. Attribut `plages_hc` : périodes appliquées. Saisie d'un seul jeu de plages inchangée.
- **Tempo** (#340, #355) : option Tempo du TRV, offre-option distincte (grille CRE `Option_Tempo.csv`), calculée avec les couleurs réelles des jours passés (`tarifs/tempo_couleurs.csv`, 4 432 jours depuis le 1er septembre 2014) ; journée de 6h à 6h, heures creuses fixes 22h-6h. Jours absents estimés selon les règles Tempo (quotas, jours éligibles, jours les plus froids de la période), comptés dans l'attribut `jours_couleur_estimee`. Script `scripts/maj_tempo.py` : ajout des jours passés, contrôle des règles.
- **Offres de marché à prix fixe** (#5, #6) : grilles des fournisseurs en YAML dans `offres/`, comparées comme les tarifs réglementés — abonnement mensuel converti en €/an, puissances non proposées signalées indisponibles, grilles datées appliquées au jour le jour. Lot 1 (#40, #44, #63, #64) : la bellenergie Prudence et Garance, Ohm Sérénité Fixe 1 an, Alterna fixe 1 an. Lot 2 (#38, #43, #56, #57, #61, #62, #65, #68) : Ohm Fixe 2 ans, Alterna Mon électricité du coin, GEG Elec Verte 3 ans, ilek ÉnRFixe+, Primeo Fixe Confort, la bellenergie Constance, Plenitude Pleniweb 1 an, SÉLIA élec vert Fixe.
- **Squelette d'éligibilité territoriale** (#345) : champ facultatif `territoire` (`enedis` ou `eld:<id>`) ; une offre-option d'un autre territoire est écartée avec la raison. Le territoire du site reste Enedis tant que la configuration ne le demande pas (#347).
- **Tests de non-régression des coûts** (#359) : coûts de référence de chaque offre-option sur deux profils de 12 mois, calculés avant le découpage (`tests/donnees/reference_couts.json`).
- **Capteurs par offre** : un capteur de coût sur 12 mois par option de chaque offre, classement mélangé TRV + offres avec libellés.
- **Grilles CRE** (#2) : tarifs réglementés TTC Base et Heures creuses depuis 2012, toutes puissances publiées, copiés depuis l'open data de la CRE (`scripts/maj_tarifs_cre.py`).
- **Moteur de calcul** (#2) : chaque heure consommée est valorisée au prix en vigueur ce jour-là, abonnement compté au jour, heure à cheval sur une limite d'heures creuses répartie au prorata des minutes.
- **Comparaison sur 12 mois** (#2) : lecture des statistiques horaires du capteur d'énergie (recorder), recalcul toutes les 6 h.
- **Capteurs** (#2) : coût de chaque option, option la moins chère (avec classement), économie possible, consommation et part en heures creuses.
- **Configuration depuis l'interface** (#2) : capteur, puissance, option actuelle, plages d'heures creuses (plusieurs plages possibles).

### Modifié
- **Une offre-option par fichier** (#343) : les 12 fichiers d'offres sont découpés en 24 fichiers `offres/<offre>_<option>.yaml`, chacun rattaché à l'issue de son offre-option (inventaire #6). Un fichier qui regroupe plusieurs options, deux fichiers pour la même issue, des postes qui ne correspondent pas à l'option ou un champ inconnu sont refusés. Les clés de comparaison deviennent `<offre>_<option>` (état du capteur « option la moins chère ») ; les identifiants des capteurs de coût ne changent pas.
- **Moteur** (#339) : chaque offre-option est calculée séparément avec son calendrier (`calendrier.py` : Base, HP/HC), point d'entrée des futurs Tempo, heures super creuses et week-end ; une structure pas encore prise en charge est signalée indisponible avec la raison.
- `cout_option` se règle sur les postes de la grille (`base` ou `hp`/`hc`) au lieu de la clé d'option : prépare les offres de marché sans changer les résultats du TRV.

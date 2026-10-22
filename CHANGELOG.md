# Journal des versions

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/). Les numéros suivent [SemVer](https://semver.org/lang/fr/), et la version de `manifest.json` est égale au tag.

## [Non publié]

### Ajouté
- **Offres Hunélec** (#325, #326, #327, #328) : Offre à prix fixe 1 an, Base et Heures creuses, et sa variante 100 % énergie verte. Grilles TTC du 01/07/2026, lues dans les fiches descriptives page 4. Le supplément « vert » de 2,27 € TTC/mois est ajouté à l'abonnement. Ces offres sont réservées au réseau Hunélec (Haut-Rhin) : le moteur ne filtre pas encore par zone, comme pour GEG.

## [0.1.0] - 2026-10-22

### Ajouté
- **Offres de marché à prix fixe** (#5, #6) : grilles des fournisseurs en YAML dans `offres/`, comparées comme les tarifs réglementés — abonnement mensuel converti en €/an, puissances non proposées signalées indisponibles, grilles datées appliquées au jour le jour. Lot 1 (#40, #44, #63, #64) : la bellenergie Prudence et Garance, Ohm Sérénité Fixe 1 an, Alterna fixe 1 an. Lot 2 (#38, #43, #56, #57, #61, #62, #65, #68) : Ohm Fixe 2 ans, Alterna Mon électricité du coin, GEG Elec Verte 3 ans, ilek ÉnRFixe+, Primeo Fixe Confort, la bellenergie Constance, Plenitude Pleniweb 1 an, SÉLIA élec vert Fixe.
- **Capteurs par offre** : un capteur de coût sur 12 mois par option de chaque offre, classement mélangé TRV + offres avec libellés.
- **Grilles CRE** (#2) : tarifs réglementés TTC Base et Heures creuses depuis 2012, toutes puissances publiées, copiés depuis l'open data de la CRE (`scripts/maj_tarifs_cre.py`).
- **Moteur de calcul** (#2) : chaque heure consommée est valorisée au prix en vigueur ce jour-là, abonnement compté au jour, heure à cheval sur une limite d'heures creuses répartie au prorata des minutes.
- **Comparaison sur 12 mois** (#2) : lecture des statistiques horaires du capteur d'énergie (recorder), recalcul toutes les 6 h.
- **Capteurs** (#2) : coût de chaque option, option la moins chère (avec classement), économie possible, consommation et part en heures creuses.
- **Configuration depuis l'interface** (#2) : capteur, puissance, option actuelle, plages d'heures creuses (plusieurs plages possibles).

### Modifié
- `cout_option` se règle sur les postes de la grille (`base` ou `hp`/`hc`) au lieu de la clé d'option : prépare les offres de marché sans changer les résultats du TRV.

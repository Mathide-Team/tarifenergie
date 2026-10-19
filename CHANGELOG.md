# Journal des versions

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/). Les numéros suivent [SemVer](https://semver.org/lang/fr/), et la version de `manifest.json` est égale au tag.

## [Non publié]

### Ajouté
- **Grilles CRE** (#2) : tarifs réglementés TTC Base et Heures creuses depuis 2012, toutes puissances publiées, copiés depuis l'open data de la CRE (`scripts/maj_tarifs_cre.py`).
- **Moteur de calcul** (#2) : chaque heure consommée est valorisée au prix en vigueur ce jour-là, abonnement compté au jour, heure à cheval sur une limite d'heures creuses répartie au prorata des minutes.
- **Comparaison sur 12 mois** (#2) : lecture des statistiques horaires du capteur d'énergie (recorder), recalcul toutes les 6 h.
- **Capteurs** (#2) : coût de chaque option, option la moins chère (avec classement), économie possible, consommation et part en heures creuses.
- **Configuration depuis l'interface** (#2) : capteur, puissance, option actuelle, plages d'heures creuses (plusieurs plages possibles).

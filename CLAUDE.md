# CLAUDE.md — tarifenergie

Intégration Home Assistant : comparaison des tarifs d'électricité (puis de gaz) sur la consommation réelle. Feuille de route : #1.

## Architecture

```
custom_components/tarifenergie/
├── modele.py        Grilles CRE (CSV) → Grille, Grilles.en_vigueur(puissance, jour)   — Python pur
├── calendrier.py    PlagesHC, Calendrier (Base, HP/HC, Tempo ; HSC, week-end à venir) — Python pur
├── tempo.py         Couleurs Tempo réelles (jours passés), règles, estimation des manques — Python pur
├── teleinfo.py      Détection des plages HC datées depuis les index HC / HP de téléinformation — Python pur
├── calcul.py        cout_option(), comparer() : chaque offre-option séparément        — Python pur
├── offres.py        offres/<offre>_<option>.yaml → Offre (une option, une issue)      — Python pur
├── coordinateur.py  Statistiques horaires du recorder (kWh, heure locale) → Comparaison, toutes les 6 h
├── config_flow.py   Capteur, puissance, option actuelle, heures creuses (+ options)
├── sensor.py        Coûts, option la moins chère, économie, consommation, part HC
└── tarifs/          Open data CRE copiée telle quelle (scripts/maj_tarifs_cre.py) et couleurs Tempo (scripts/maj_tempo.py)
```

## Conventions

- Montants en `Decimal`, arrondi au centime sur le total uniquement.
- Prix du **jour** de consommation (date locale) ; abonnement à 1/365 (ou 1/366) par jour.
- Une valeur vérifiée dans un fichier CRE est citée dans les tests avec sa grille (ex. « 01/08/2026, 6 kVA »).
- **Une offre-option = une issue = un fichier** (#6, #343) : jamais de regroupement des options d'une offre.
- Non-régression : `tests/donnees/reference_couts.json` ; un changement de grille assumé se regénère avec `python -m tests.reference_couts` et se justifie dans la PR.
- Couverture 100 % ; `recorder_mock` activé pour tous les tests (`tests/conftest.py`).
- Socle Mathide-Team : PR vers `dev` (modèle Objet / Closes / Vérifications), relais `dev` → `main`, merge commit, pas de force push.

## Instructions reçues dans le chat

Toute instruction reçue dans le chat devient une issue (ou un commentaire tracé sur l'issue existante), citée mot pour mot avec sa date. Une question à Mathilde se pose en issue avec le label `question`.

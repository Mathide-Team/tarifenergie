# tarifenergie

Intégration Home Assistant : **quel tarif d'électricité aurait coûté le moins cher avec ma consommation réelle des 12 derniers mois ?**

Plutôt qu'une consommation théorique de 4 000 ou 5 000 kWh/an, tarifenergie reprend la consommation **heure par heure** déjà enregistrée par Home Assistant (le capteur du tableau de bord Énergie : Linky, pince ampèremétrique, etc.) et la valorise avec les tarifs officiels.

## Ce que fait la version 0.1

- Compare les **tarifs réglementés** (tarif Bleu) publiés par la [CRE](https://www.data.gouv.fr/datasets/historique-des-tarifs-reglementes-de-vente-delectricite-pour-les-consommateurs-residentiels) : options **Base** et **Heures pleines / Heures creuses**, prix TTC.
- Applique à chaque heure le tarif **en vigueur ce jour-là** : un an de consommation à cheval sur le 1er février et le 1er août est compté avec les bonnes grilles.
- Compte l'abonnement au jour près, pour la puissance souscrite.
- Prend vos plages d'heures creuses (elles dépendent du compteur, pas du fournisseur), même plusieurs plages (« 02:00-07:00, 13:00-16:00 »).

## Capteurs

| Capteur | Valeur | Attributs |
|---|---|---|
| Coût sur 12 mois, option Base | € TTC | kWh, part énergie et abonnement, grilles CRE utilisées, période couverte |
| Coût sur 12 mois, option Heures creuses | € TTC | kWh HP et HC, idem |
| Option la moins chère | `base` / `hphc` | classement complet, options indisponibles et pourquoi |
| Économie possible sur 12 mois | € par rapport à l'option actuelle | classement |
| Consommation sur 12 mois | kWh | période couverte |
| Part en heures creuses | % | |

Avec moins de 12 mois d'historique, les coûts portent sur la période disponible (attribut `jours_couverts`).

## Installation

1. HACS → Dépôts personnalisés → `https://github.com/Mathide-Team/tarifenergie`, catégorie « Intégration ».
2. Installer tarifenergie, redémarrer Home Assistant.
3. Paramètres → Appareils et services → Ajouter une intégration → tarifenergie.

## Limites connues

- La CRE ne publie l'option Base que jusqu'à 15 kVA : au-delà, elle est signalée indisponible.
- Statistiques horaires : une heure à cheval sur une limite d'heures creuses (ex. 23:30) est répartie au prorata des minutes.
- Pas encore de Tempo (#3), de gaz (#4) ni d'offres de marché des fournisseurs (#5).

Sources et particularités des données : [docs/sources.md](docs/sources.md).

## Développement

```sh
uv run --only-group lint ruff check .
uv run -p 3.13 --only-group test pytest --cov
python3 scripts/maj_tarifs_cre.py   # à chaque mouvement tarifaire
```

Branches : PR vers `dev`, puis relais `dev` → `main`. Licence MIT.

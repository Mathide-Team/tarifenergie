# tarifenergie

Intégration Home Assistant : **quel tarif d'électricité aurait coûté le moins cher avec ma consommation réelle des 12 derniers mois ?**

Plutôt qu'une consommation théorique de 4 000 ou 5 000 kWh/an, tarifenergie reprend la consommation **heure par heure** déjà enregistrée par Home Assistant (le capteur du tableau de bord Énergie : Linky, pince ampèremétrique, etc.) et la valorise avec les tarifs officiels.

## Ce que fait la version 0.1

Elle compare, sur les 12 derniers mois de consommation réelle, le coût TTC des options
de tarification des tarifs réglementés (Base, Heures creuses) : abonnement au prorata
du jour, kWh au prix en vigueur à la date de la consommation, heures creuses réparties
au prorata des minutes. La v0.2 y ajoute les offres de marché (voir ci-dessous).

- Compare les **tarifs réglementés** (tarif Bleu) publiés par la [CRE](https://www.data.gouv.fr/datasets/historique-des-tarifs-reglementes-de-vente-delectricite-pour-les-consommateurs-residentiels) : options **Base** et **Heures pleines / Heures creuses**, prix TTC.
- Applique à chaque heure le tarif **en vigueur ce jour-là** : un an de consommation à cheval sur le 1er février et le 1er août est compté avec les bonnes grilles.
- Compte l'abonnement au jour près, pour la puissance souscrite.
- Prend vos plages d'heures creuses (elles dépendent du compteur, pas du fournisseur), même plusieurs plages (« 02:00-07:00, 13:00-16:00 »).

## Capteurs

| Capteur | Valeur | Attributs |
|---|---|---|
| Coût sur 12 mois, option Base (TRV) | € TTC | kWh, part énergie et abonnement, grilles CRE utilisées, période couverte |
| Coût sur 12 mois, option Heures creuses (TRV) | € TTC | kWh HP et HC, idem |
| Coût sur 12 mois, chaque option de chaque offre de marché | € TTC | idem |
| Option la moins chère | `base` / `hphc` ou `<offre>:<option>` (ex. `la_bellenergie_prudence:hphc`) | classement complet avec libellés, options indisponibles et pourquoi |
| Économie possible sur 12 mois | € par rapport à l'option actuelle | classement |
| Consommation sur 12 mois | kWh | période couverte |
| Part en heures creuses | % | |

Avec moins de 12 mois d'historique, les coûts portent sur la période disponible (attribut `jours_couverts`).

## Offres de marché (v0.2)

Les grilles des fournisseurs sont livrées dans `custom_components/tarifenergie/offres/*.yaml`
(inventaire [#6](https://github.com/Mathide-Team/tarifenergie/issues/6), moteur [#5](https://github.com/Mathide-Team/tarifenergie/issues/5)) :
une issue par offre documente la grille, sa date d'effet et ses sources. La v0.2 couvre
les offres **à prix fixe** avec options Base et Heures creuses — 17 offres :

- la bellenergie Prudence 1 an, Constance 2 ans et Garance 3 ans,
- Ohm Énergie Sérénité Fixe 1 an et Fixe 2 ans,
- Alterna Mon électricité française fixe 1 an et Mon électricité du coin 1 an,
- ÉS Énergies Électricité verte à prix fixe 1 an et sa variante 100 % régionale (Strasbourg Électricité Réseaux),
- GEDIA All Inclusive GES Électricité (réseau GEDIA, Dreux ; abonnement publié en €/an),
- GEG Mon Offre Elec Verte fixe 3 ans (kWh HC/HP selon la puissance),
- Hunélec Offre à prix fixe 1 an et sa variante 100 % énergie verte (réseau Hunélec, Haut-Rhin),
- ilek ÉnRFixe+ Élec,
- Primeo Energie Offre Fixe Confort,
- Eni Plenitude Pleniweb 1 an,
- SÉLIA Mon Contrat élec vert Fixe.

S'y ajoutent les **TRV locaux** des entreprises locales de distribution (`type_prix: reglemente`,
sans durée de fixité, réseau dans `eld:`) : ÉS Énergies (Strasbourg Électricité Réseaux) et
SIEL Labergement-Sainte-Marie.

Chaque offre est comparée sur la consommation réelle comme les tarifs réglementés :
puissances non proposées (ex. Heures creuses en 3 kVA) signalées comme indisponibles,
grilles datées appliquées au jour le jour. Les offres indexées, dynamiques ou à
coloration de jours (OctoTempo) viendront ensuite. Pour ajouter une offre : un fichier
YAML sur le modèle des existants, une issue d'inventaire la documentant.

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

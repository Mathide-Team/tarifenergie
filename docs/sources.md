# Sources de données

Vérifiées le 18/10/2026. Découpage du projet : #1.

## Utilisées

| Donnée | Source | Format | Usage |
|---|---|---|---|
| Tarifs réglementés d'électricité (TRVE) Base, Heures creuses, Tempo, depuis 2012, HT et TTC, par puissance | CRE, [jeu de données sur data.gouv.fr](https://www.data.gouv.fr/datasets/historique-des-tarifs-reglementes-de-vente-delectricite-pour-les-consommateurs-residentiels) (fichiers [Option_Base.csv](https://www.cre.fr/fileadmin/Documents/Open_data/Marches_de_detail/Option_Base.csv), [Option_HPHC.csv](https://www.cre.fr/fileadmin/Documents/Open_data/Marches_de_detail/Option_HPHC.csv), [Option_Tempo.csv](https://www.cre.fr/fileadmin/Documents/Open_data/Marches_de_detail/Option_Tempo.csv), [Notice.txt](https://www.cre.fr/fileadmin/Documents/Open_data/Marches_de_detail/Notice.txt)) | CSV `;`, virgule décimale, dates JJ/MM/AAAA | `tarifs/*.csv`, copiés tels quels ; `scripts/maj_tarifs_cre.py` les remet à jour |
| Consommation réelle | Statistiques horaires du recorder Home Assistant (capteur d'énergie cumulée) | `change` par heure, converti en kWh | `coordinateur.py` |

Particularités constatées dans les fichiers CRE :
- l'option **Base** n'est publiée que de 3 à 15 kVA : au-delà, l'option est signalée indisponible ;
- l'option **Heures creuses** existe en 3 kVA depuis la grille du 01/08/2026 ;
- les prix TTC incluent CTA, accise (ex-CSPE), TCFE et TVA, selon la notice ;
- les abonnements TTC de l'option Heures creuses ont 7 décimales (ex. 239,8378787 €/an) : ils sont gardés tels quels, l'arrondi au centime se fait sur le total.

Le jeu de données data.gouv.fr indique une licence « non spécifiée » ; la CRE le publie comme données ouvertes sur son site. À confirmer avant toute redistribution hors de ce dépôt.

## Prévues

| Donnée | Source | Issue |
|---|---|---|
| Couleur des jours Tempo | RTE (API avec inscription) ou entité Home Assistant | #3 |
| Prix repère du gaz | CRE | #4 |
| Offres de marché des fournisseurs | Comparateur Énergie-Info du Médiateur national de l'énergie (sans API publique documentée : conditions de réutilisation à vérifier d'abord) | #5 |
| Distributeur par commune | Agence ORE | #5 |

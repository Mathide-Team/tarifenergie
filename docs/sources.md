# Sources de données

Vérifiées le 18/10/2026. Découpage du projet : #1.

## Utilisées

| Donnée | Source | Format | Usage |
|---|---|---|---|
| Tarifs réglementés d'électricité (TRVE) Base, Heures creuses, Tempo, depuis 2012, HT et TTC, par puissance | CRE, [jeu de données sur data.gouv.fr](https://www.data.gouv.fr/datasets/historique-des-tarifs-reglementes-de-vente-delectricite-pour-les-consommateurs-residentiels) (fichiers [Option_Base.csv](https://www.cre.fr/fileadmin/Documents/Open_data/Marches_de_detail/Option_Base.csv), [Option_HPHC.csv](https://www.cre.fr/fileadmin/Documents/Open_data/Marches_de_detail/Option_HPHC.csv), [Option_Tempo.csv](https://www.cre.fr/fileadmin/Documents/Open_data/Marches_de_detail/Option_Tempo.csv), [Notice.txt](https://www.cre.fr/fileadmin/Documents/Open_data/Marches_de_detail/Notice.txt)) | CSV `;`, virgule décimale, dates JJ/MM/AAAA | `tarifs/*.csv`, copiés tels quels ; `scripts/maj_tarifs_cre.py` les remet à jour |
| Couleurs des jours Tempo passés, depuis le 1er septembre 2014 | RTE ([calendrier Tempo](https://www.services-rte.com/fr/visualisez-les-donnees-publiees-par-rte/calendrier-des-offres-de-fourniture-de-type-tempo.html), API avec compte), via le miroir public sans clé [jourtempo/tempo-historique](https://github.com/jourtempo/tempo-historique) ([CSV](https://jourtempo.fr/api/v1/tempo-historique.csv)) ; recoupé le 19/10/2026 avec [calendrier-tempo.fr](https://www.calendrier-tempo.fr/historique-previsions.csv) (246 jours communs, aucun écart) | CSV `date;couleur` (ISO, bleu/blanc/rouge) | `tarifs/tempo_couleurs.csv` ; `scripts/maj_tempo.py` ajoute les jours passés et contrôle les règles (#355) |
| Consommation réelle | Statistiques horaires du recorder Home Assistant (capteur d'énergie cumulée) | `change` par heure, converti en kWh | `coordinateur.py` |

Particularités constatées dans l'historique Tempo : toutes les saisons complètes comptent 22 rouges et 43 blancs, sauf 2019-2020 (18 rouges, 47 blancs : la CRE a fait remplacer les rouges par des blancs à partir du 19 mars 2020, crise sanitaire ; synthèse de saison de RTE). Aucun rouge un week-end, un jour férié national ou hors novembre-mars ; aucun blanc un dimanche ; 5 rouges consécutifs au plus.

Particularités constatées dans les fichiers CRE :
- l'option **Base** n'est publiée que de 3 à 15 kVA : au-delà, l'option est signalée indisponible ;
- l'option **Heures creuses** existe en 3 kVA depuis la grille du 01/08/2026 ;
- les prix TTC incluent CTA, accise (ex-CSPE), TCFE et TVA, selon la notice ;
- les abonnements TTC de l'option Heures creuses ont 7 décimales (ex. 239,8378787 €/an) : ils sont gardés tels quels, l'arrondi au centime se fait sur le total.

Le jeu de données data.gouv.fr indique une licence « non spécifiée » ; la CRE le publie comme données ouvertes sur son site. À confirmer avant toute redistribution hors de ce dépôt.

## Prévues

| Donnée | Source | Issue |
|---|---|---|
| Prix repère du gaz | CRE | #4 |
| Offres de marché des fournisseurs | Comparateur Énergie-Info du Médiateur national de l'énergie (sans API publique documentée : conditions de réutilisation à vérifier d'abord) | #5 |
| Distributeur par commune | Agence ORE | #5 |

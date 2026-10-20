"""Détection des plages HP/HC depuis les index de téléinformation (#370)."""

from datetime import date, datetime, timedelta

import pytest

from custom_components.tarifenergie.calendrier import PlagesDatees
from custom_components.tarifenergie.teleinfo import detecter_plages, signatures_par_jour

DEBUT = datetime(2026, 1, 1)


def _creuse(texte_ou_plages):
    plages = PlagesDatees.lire(texte_ou_plages) if isinstance(texte_ou_plages, str) else texte_ou_plages
    return lambda heure: plages.du_jour(heure.date()).fraction_hc(heure.hour)


def _index(jours: int, part_hc, kwh: float = 1.0, debut: datetime = DEBUT):
    """Index HC et HP horaires d'une consommation régulière, ventilée selon ``part_hc``."""
    hc, hp = [], []
    for i in range(jours * 24):
        heure = debut + timedelta(hours=i)
        part = float(part_hc(heure))
        hc.append((heure, kwh * part))
        hp.append((heure, kwh * (1 - part)))
    return hc, hp


@pytest.mark.parametrize(
    "texte", ["22:00-06:00", "23:30-07:30", "02:00-07:00, 13:00-16:00", "12:00-14:00, 20:00-02:00"]
)
def test_plages_retrouvees(texte):
    detectees = detecter_plages(*_index(10, _creuse(texte)))
    assert detectees == PlagesDatees.lire(texte)


def test_changement_en_cours_d_annee():
    texte = "23:30-07:30 | 2026-03-15: 02:00-07:00, 13:00-16:00"
    detectees = detecter_plages(*_index(120, _creuse(texte)))
    assert detectees is not None
    assert detectees.texte() == texte


def test_jour_atypique_ignore():
    """Deux jours avec d'autres plages (moins de 3) ne créent pas de changement."""
    normal = _creuse("22:00-06:00")
    atypique = _creuse("12:00-20:00")
    jours_atypiques = {date(2026, 1, 5), date(2026, 1, 6)}
    detectees = detecter_plages(
        *_index(20, lambda h: (atypique if h.date() in jours_atypiques else normal)(h))
    )
    assert detectees == PlagesDatees.lire("22:00-06:00")


def test_heures_muettes_reprises_de_la_veille():
    """Absence la journée (aucune consommation de 8h à 18h) : plages reprises du jour précédent."""
    hc, hp = _index(6, _creuse("02:00-07:00, 13:00-16:00"))
    absent = {date(2026, 1, 3), date(2026, 1, 4)}

    def muet(serie):
        return [(h, 0.0 if h.date() in absent and 8 <= h.hour < 18 else v) for h, v in serie]

    jours = signatures_par_jour(muet(hc), muet(hp))
    assert len(jours) == 6
    assert detecter_plages(muet(hc), muet(hp)) == PlagesDatees.lire("02:00-07:00, 13:00-16:00")


def test_premier_jour_incomplet_ignore():
    hc, hp = _index(5, _creuse("22:00-06:00"))
    premier = DEBUT.date()

    def muet(serie):
        return [(h, 0.0 if h.date() == premier and h.hour < 12 else v) for h, v in serie]

    jours = signatures_par_jour(muet(hc), muet(hp))
    assert jours[0][0] == premier + timedelta(days=1)


def test_heure_mixte_sans_voisine_pour_trancher():
    """23h mixte, 22h et 0h muettes : jour incomplet sans veille, donc ignoré."""
    heure = DEBUT.replace(hour=23)
    hc = [(heure, 0.5)] + [(DEBUT.replace(hour=h), 1.0) for h in range(1, 7)]
    hp = [(heure, 0.5)] + [(DEBUT.replace(hour=h), 1.0) for h in range(7, 22)]
    assert signatures_par_jour(hc, hp) == []


@pytest.mark.parametrize(
    "part_hc",
    [lambda h: 0.0, lambda h: 1.0],  # compteur en Base (tout en HP) ; tout en HC
)
def test_pas_d_heures_creuses(part_hc):
    assert detecter_plages(*_index(10, part_hc)) is None


def test_aucune_donnee():
    assert detecter_plages([], []) is None


def test_peu_de_jours_mais_stables():
    """Deux jours seulement : moins que le minimum, mais rien d'autre à opposer."""
    assert detecter_plages(*_index(2, _creuse("22:00-06:00"))) == PlagesDatees.lire("22:00-06:00")


def test_retour_aux_plages_precedentes():
    texte = "22:00-06:00 | 2026-02-01: 23:00-07:00 | 2026-03-01: 22:00-06:00"
    assert detecter_plages(*_index(90, _creuse(texte))).texte() == texte


def test_periode_sans_heures_creuses_omise():
    """Un mois sans HC (index HP seul) entre deux périodes identiques : une seule période."""
    hc_hp = _creuse("22:00-06:00")
    detectees = detecter_plages(*_index(90, lambda h: 0.0 if h.month == 2 else hc_hp(h)))
    assert detectees == PlagesDatees.lire("22:00-06:00")


def test_variation_negative_ignoree():
    hc, hp = _index(5, _creuse("22:00-06:00"))
    hc[3] = (hc[3][0], -50.0)
    assert detecter_plages(hc, hp) == PlagesDatees.lire("22:00-06:00")


# --- Saisons été / hiver (#368) -----------------------------------------------------------

SAISONS = "été 02:00-07:00, 13:00-16:00 / hiver 23:00-07:00"


def test_saisons_reconnues_sur_douze_mois():
    """Bascules au 1er novembre puis au 1er avril : plages saisonnières, reconduites."""
    detectees = detecter_plages(*_index(365, _creuse(SAISONS), debut=datetime(2025, 10, 20)))
    assert detectees == PlagesDatees.lire(SAISONS)


def test_une_seule_bascule_reste_datee():
    """Une seule bascule visible : plages datées (même calcul sur la fenêtre mesurée)."""
    detectees = detecter_plages(*_index(200, _creuse(SAISONS), debut=datetime(2026, 1, 1)))
    assert detectees.texte() == "23:00-07:00 | 2026-04-01: 02:00-07:00, 13:00-16:00"


def test_bascule_a_quelques_jours_pres():
    texte = "02:00-07:00, 13:00-16:00 | 2025-11-03: 23:00-07:00 | 2026-03-30: 02:00-07:00, 13:00-16:00"
    detectees = detecter_plages(*_index(365, _creuse(texte), debut=datetime(2025, 10, 20)))
    assert detectees == PlagesDatees.lire(SAISONS)


def test_changements_hors_saison_restent_dates():
    texte = "02:00-07:00, 13:00-16:00 | 2025-12-15: 23:00-07:00 | 2026-04-01: 02:00-07:00, 13:00-16:00"
    detectees = detecter_plages(*_index(365, _creuse(texte), debut=datetime(2025, 10, 20)))
    assert detectees.texte() == texte


def test_trois_jeux_de_plages_pas_de_saison():
    """Bascules aux bonnes dates, mais sans alternance (A, B puis C) : plages datées."""
    texte = "22:00-06:00 | 2025-11-01: 23:00-07:00 | 2026-04-01: 02:00-07:00, 13:00-16:00"
    detectees = detecter_plages(*_index(365, _creuse(texte), debut=datetime(2025, 10, 20)))
    assert detectees.texte() == texte


def test_changement_puis_saisons():
    """22h-6h, puis (redéploiement) plages été / hiver vues sur deux bascules."""
    texte = f"22:00-06:00 | 2025-12-15: {SAISONS}"
    detectees = detecter_plages(*_index(500, _creuse(texte), debut=datetime(2025, 9, 1)))
    assert detectees.texte() == texte

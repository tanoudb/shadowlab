"""Le bilan d'une soirée déjà faite (campagnes 128 à 131) ne change pas avec la course de 7 jours (I9).

Test de caractérisation : il passe avant et après les changements d'I9. Deux soirées fabriquées (aucune donnée de
visiteur réelle), l'une tenue comme la 131, l'autre non tenue comme la 128 (sujet arrêté à la 4e visite, banni, puis
refusé par l'outil ; sentinelle arrêtée à la 2e visite) ; le rapport complet de `soiree.bilan` est figé ici, octet pour
octet, une fois l'identifiant de la campagne remplacé par `{x}`.
"""

# ruff: noqa: E501  (rapports figés en ligne)
from __future__ import annotations

import json

from test_soiree import bannir, base, soiree_reussie, visite  # noqa: F401 (fixture `base`)

from shadowlab import soiree


def soiree_comme_la_128(cx, x):
    for n in range(1, 4):
        visite(cx, x, "sujet", n, defi=1 if n == 1 else 0)
    visite(cx, x, "sujet", 4, reussie=False, bloque=True, arret=True, identite="alerte")
    for n in range(5, 10):  # identité en alerte : l'outil refuse de lancer Chrome
        visite(cx, x, "sujet", n, visiteur=None, e=None, reussie=False, identite=None)
    visite(cx, x, "sujet", 10, reussie=False, bloque=True, arret=True, identite="banni")
    for n in range(11, 25):
        visite(cx, x, "sujet", n, visiteur=None, e=None, reussie=False, identite=None)
    bannir(cx, x, "sujet", visiteur="v1", empreinte="e1", motif="detecte:comportement")
    for n in range(1, 25):
        visite(cx, x, "temoin-negatif", n, visiteur=f"n{n}", reussie=n < 5, bloque=n >= 5)
    bannir(cx, x, "temoin-negatif", visiteur="n5", empreinte="e1", motif="detecte:correlation-session")
    visite(cx, x, "temoin-sentinelle", 1, visiteur="s1", e="E3", defi=1)
    visite(
        cx,
        x,
        "temoin-sentinelle",
        2,
        visiteur="s1",
        e="E3",
        reussie=False,
        bloque=True,
        arret=True,
        identite="alerte",
        pages_apres=2,
    )
    bannir(cx, x, "temoin-sentinelle", visiteur="s1")
    for n in range(3, 7):
        visite(cx, x, "temoin-sentinelle", n, visiteur=None, e=None, reussie=False, identite=None)
    for n in range(1, 5):
        visite(
            cx,
            x,
            "temoin-classique",
            n,
            visiteur=f"p{n}",
            e="E4",
            reussie=False,
            bloque=True,
            arret=True,
            identite=None,
        )


def fige(rapport, x):
    return json.loads(
        json.dumps(rapport, ensure_ascii=False)
        .replace(f"c{x}:", "c{x}:")
        .replace(f'"campagne": {x}', '"campagne": "{x}"')
    )


ATTENDU_131 = {
    "campagne": "{x}",
    "bras": {
        "sujet": {
            "label": "sujet",
            "monde": "c{x}:sujet:endurance",
            "visites_prevues": 24,
            "visites_faites": 24,
            "visites_reussies": 24,
            "bannissements": 0,
            "criteres": {
                "visites_reussies": {"statut": "tenu", "detail": "24 réussies sur 24 faites, 24 prévues"},
                "meme_visiteur": {"statut": "tenu", "detail": "1 visiteur distinct(s) sur 24 visites"},
                "meme_empreinte": {"statut": "tenu", "detail": "1 empreinte E distinct(s) sur 24 visites"},
                "defi_premiere_visite_seulement": {
                    "statut": "tenu",
                    "detail": "défis émis à la 1re visite : 1 ; revenus aux visites : aucune",
                },
                "aucune_alerte": {
                    "statut": "tenu",
                    "detail": "visites en alerte ou arrêtées : aucune ; bannissements dans le monde : 0",
                },
            },
        },
        "temoin-negatif": {
            "label": "temoin-negatif",
            "monde": "c{x}:temoin-negatif:endurance",
            "visites_prevues": 24,
            "visites_faites": 24,
            "visites_reussies": 4,
            "bannissements": 1,
            "criteres": {
                "arrete_a_la_visite_5": {"statut": "tenu", "detail": "première visite arrêtée : 5 (attendue : 5)"},
                "banni": {"statut": "tenu", "detail": "1 bannissement(s) dans le monde du bras"},
            },
            "premiere_visite_arretee": 5,
        },
        "temoin-sentinelle": {
            "label": "temoin-sentinelle",
            "monde": "c{x}:temoin-sentinelle:endurance",
            "visites_prevues": 6,
            "visites_faites": 6,
            "visites_reussies": 2,
            "bannissements": 1,
            "criteres": {
                "bannissement_ecrit": {"statut": "tenu", "detail": "visiteur s1 banni (motif manuel)"},
                "refus_a_la_visite_voulue": {"statut": "tenu", "detail": "premier refus à la visite 3 (voulue : 3)"},
                "aucune_requete_apres_403": {
                    "statut": "tenu",
                    "detail": "0 page(s) demandée(s) après le premier refus (0 requête(s) toutes ressources comprises)",
                },
                "identite_bannie": {"statut": "tenu", "detail": "identité notée `banni`"},
            },
            "premiere_visite_refusee": 3,
            "requetes_apres_403": 0,
        },
        "temoin-classique": {
            "label": "temoin-classique",
            "monde": "c{x}:temoin-classique:endurance",
            "visites_prevues": 4,
            "visites_faites": 4,
            "visites_reussies": 0,
            "bannissements": 0,
            "criteres": {
                "toujours_arrete": {"statut": "tenu", "detail": "visites réussies : aucune sur 4"},
                "refus_par_l_arena": {"statut": "tenu", "detail": "refus ou bannissement enregistré par l'Arena"},
            },
        },
    },
    "verdict": "tenu",
}

ATTENDU_128 = {
    "campagne": "{x}",
    "bras": {
        "sujet": {
            "label": "sujet",
            "monde": "c{x}:sujet:endurance",
            "visites_prevues": 24,
            "visites_faites": 24,
            "visites_reussies": 3,
            "bannissements": 1,
            "criteres": {
                "visites_reussies": {"statut": "non tenu", "detail": "3 réussies sur 24 faites, 24 prévues"},
                "meme_visiteur": {"statut": "non tenu", "detail": "19 visite(s) sans visiteur noté"},
                "meme_empreinte": {"statut": "non tenu", "detail": "19 visite(s) sans empreinte E noté"},
                "defi_premiere_visite_seulement": {
                    "statut": "tenu",
                    "detail": "défis émis à la 1re visite : 1 ; revenus aux visites : aucune",
                },
                "aucune_alerte": {
                    "statut": "non tenu",
                    "detail": "visites en alerte ou arrêtées : [4, 10] ; bannissements dans le monde : 1",
                },
            },
        },
        "temoin-negatif": {
            "label": "temoin-negatif",
            "monde": "c{x}:temoin-negatif:endurance",
            "visites_prevues": 24,
            "visites_faites": 24,
            "visites_reussies": 4,
            "bannissements": 1,
            "criteres": {
                "arrete_a_la_visite_5": {"statut": "tenu", "detail": "première visite arrêtée : 5 (attendue : 5)"},
                "banni": {"statut": "tenu", "detail": "1 bannissement(s) dans le monde du bras"},
            },
            "premiere_visite_arretee": 5,
        },
        "temoin-sentinelle": {
            "label": "temoin-sentinelle",
            "monde": "c{x}:temoin-sentinelle:endurance",
            "visites_prevues": 6,
            "visites_faites": 6,
            "visites_reussies": 1,
            "bannissements": 1,
            "criteres": {
                "bannissement_ecrit": {"statut": "tenu", "detail": "visiteur s1 banni (motif manuel)"},
                "refus_a_la_visite_voulue": {
                    "statut": "non tenu",
                    "detail": "premier refus à la visite 2 (voulue : 3)",
                },
                "aucune_requete_apres_403": {
                    "statut": "non tenu",
                    "detail": "2 page(s) demandée(s) après le premier refus (2 requête(s) toutes ressources comprises)",
                },
                "identite_bannie": {"statut": "non tenu", "detail": "états notés : ['alerte', 'ok'], jamais `banni`"},
            },
            "premiere_visite_refusee": 2,
            "requetes_apres_403": 2,
        },
        "temoin-classique": {
            "label": "temoin-classique",
            "monde": "c{x}:temoin-classique:endurance",
            "visites_prevues": 4,
            "visites_faites": 4,
            "visites_reussies": 0,
            "bannissements": 0,
            "criteres": {
                "toujours_arrete": {"statut": "tenu", "detail": "visites réussies : aucune sur 4"},
                "refus_par_l_arena": {"statut": "tenu", "detail": "refus ou bannissement enregistré par l'Arena"},
            },
        },
    },
    "verdict": "non tenu",
}


def test_le_bilan_d_une_soiree_tenue_comme_la_131_ne_change_pas(base):  # noqa: F811
    cx, x = base
    soiree_reussie(cx, x)
    assert fige(soiree.bilan(cx, x), x) == ATTENDU_131
    assert soiree.texte(soiree.bilan(cx, x)).splitlines()[0] == f"Soirée, campagne {x} : TENU"


def test_le_bilan_d_une_soiree_non_tenue_comme_la_128_ne_change_pas(base):  # noqa: F811
    cx, x = base
    soiree_comme_la_128(cx, x)
    assert fige(soiree.bilan(cx, x), x) == ATTENDU_128

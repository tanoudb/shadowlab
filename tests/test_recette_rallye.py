"""La recette du site de rallye factice est valide et vise le port du labo par défaut."""

from pathlib import Path

from shadowlab.engines.noezia import recettes

RECETTE = Path(__file__).resolve().parents[1] / "configs" / "recettes" / "rallye-demo.yaml"


def test_la_recette_du_rallye_est_valide() -> None:
    recette = recettes.lire(RECETTE)
    assert recette.nom == "rallye-demo"
    assert recette.depart[0].url == "http://127.0.0.1:8770/lab/rallye/saisons"
    assert set(recette.variables) == {"saison", "championnat"}
    collections = {r.collection for page in recette.pages.values() for r in page.enregistrements}
    assert collections == {
        "rallyes", "speciales", "temps", "classements", "engages", "pilotes", "chassis", "historique",
    }  # fmt: skip


def test_les_pages_de_fin_de_parcours_ne_suivent_aucun_lien() -> None:
    """Pilote et châssis renvoient vers d'autres saisons : les suivre ferait déborder toute tranche."""
    recette = recettes.lire(RECETTE)
    assert recette.pages["pilote"].suivre == []
    assert recette.pages["chassis"].suivre == []

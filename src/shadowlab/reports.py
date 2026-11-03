"""Exports d'une expérience : JSON (statistiques), CSV (un passage par ligne), rapport HTML autonome."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from html import escape
from pathlib import Path
from typing import Any

from . import database as db
from .analytics import statistiques


def lignes_csv(cx: sqlite3.Connection, experiment_id: int) -> str:
    passages = cx.execute(
        """
        SELECT r.id, COALESCE(json_extract(e.configuration, '$.label'), e.name) AS moteur, s.name AS scenario,
               r.repetition, r.status, r.success, r.duration_ms, r.started_at,
               m.cpu_usage, m.cpu_time_ms, m.memory_usage, m.navigation_time, m.request_count, m.error_count, r.error
        FROM runs r JOIN engines e ON e.id = r.engine_id JOIN scenarios s ON s.id = r.scenario_id
        LEFT JOIN metrics m ON m.run_id = r.id
        WHERE r.experiment_id = ? ORDER BY r.id
        """,
        (experiment_id,),
    ).fetchall()
    detecteurs = sorted(
        {
            d["detector_name"]
            for d in cx.execute(
                "SELECT DISTINCT detector_name FROM detections JOIN runs ON runs.id = detections.run_id"
                " WHERE runs.experiment_id = ?",
                (experiment_id,),
            )
        }
    )
    classements: dict[int, dict[str, str]] = {}
    for d in cx.execute(
        "SELECT d.run_id, d.detector_name, d.classification FROM detections d JOIN runs r ON r.id = d.run_id"
        " WHERE r.experiment_id = ?",
        (experiment_id,),
    ):
        classements.setdefault(d["run_id"], {})[d["detector_name"]] = d["classification"]
    sortie = io.StringIO()
    ecrivain = csv.writer(sortie)
    colonnes = [
        "run_id",
        "moteur",
        "scenario",
        "repetition",
        "status",
        "success",
        "duration_ms",
        "started_at",
        "cpu_pct",
        "cpu_ms",
        "memoire_mo",
        "navigation_ms",
        "requetes",
        "erreurs",
        "detail",
    ]
    ecrivain.writerow(colonnes + [f"detection_{d}" for d in detecteurs])
    for p in passages:
        ecrivain.writerow(list(p) + [classements.get(p["id"], {}).get(d, "") for d in detecteurs])
    return sortie.getvalue()


def _pct(bloc: dict[str, float] | None) -> str:
    if not bloc:
        return "<span class='nm'>n. m.</span>"
    return (
        f"<span class='val'>{bloc['taux'] * 100:.1f} %</span>"
        f"<span class='ic'>[{bloc['bas'] * 100:.1f} – {bloc['haut'] * 100:.1f}]</span>"
    )


def _barre(bloc: dict[str, float] | None, classe: str) -> str:
    if not bloc:
        return ""
    return f"<span class='barre {classe}'><i style='width:{bloc['taux'] * 100:.1f}%'></i></span>"


def _ms(valeur: float | None) -> str:
    return "—" if valeur is None else f"{valeur:,.0f}".replace(",", " ")


def rapport_html(stats: dict[str, Any]) -> str:
    e = stats["experience"]
    detecteurs = sorted({d for m in stats["moteurs"] for d in m["detection"]})
    entete_det = "".join(f"<th>{escape(d)}</th>" for d in detecteurs)
    lignes_moteurs = "".join(
        f"""<tr><th scope="row">{escape(m["label"])}<small>{escape(m["runtime"])} · {
            escape(", ".join(f"{k} {v}" for k, v in (m["versions"] or {}).items()))
        }</small></th>
<td>{m["passages"]}</td><td>{_barre(m["reussite"], "ok")}{_pct(m["reussite"])}</td>
<td>{_pct(m["taux_erreur"])}</td>
<td>{_ms(m["duree_ms"]["mediane"])}</td><td>{_ms(m["duree_ms"]["p95"])}</td><td>{_ms(m["duree_ms"]["p99"])}</td>
<td>{_ms(m["cpu_ms"]["moyenne"])} ms<small>{_ms(m["cpu_pct"]["moyenne"])} % d'un cœur</small></td><td>{
            _ms(m["memoire_mo"]["moyenne"])
        } / {_ms(m["memoire_mo"]["max"])}</td></tr>"""
        for m in stats["moteurs"]
    )
    lignes_detection = "".join(
        "<tr><th scope='row'>"
        + escape(m["label"])
        + "</th>"
        + "".join(
            f"<td>{_barre(m['detection'][d]['taux_detection'], 'det')}{_pct(m['detection'][d]['taux_detection'])}"
            f"<small>indéterminé {(m['detection'][d]['taux_indetermine'] or {}).get('taux', 0) * 100:.0f} %</small></td>"
            if d in m["detection"]
            else "<td>—</td>"
            for d in detecteurs
        )
        + "</tr>"
        for m in stats["moteurs"]
    )
    qualite = stats["qualite_detecteurs"]
    lignes_qualite = "".join(
        f"<tr><th scope='row'>{escape(d)}</th><td>{q['rappel'] if q['rappel'] is not None else 'n. m.'}</td>"
        f"<td>{q['precision'] if q['precision'] is not None else 'n. m.'}</td>"
        f"<td>{q['f1'] if q['f1'] is not None else 'n. m.'}</td><td>{_pct(q['faux_positifs'])}</td>"
        f"<td>{q['sessions_humaines']}</td></tr>"
        for d, q in sorted(qualite.items())
    )
    lignes_scenarios = "".join(
        f"<tr><th scope='row'>{escape(s['label'])}</th><td>{escape(s['scenario'])}</td><td>{s['passages']}</td>"
        f"<td>{_barre(s['reussite'], 'ok')}{_pct(s['reussite'])}</td><td>{_ms(s['duree_ms']['mediane'])}</td>"
        f"<td>{_ms(s['duree_ms']['p95'])}</td></tr>"
        for s in stats["scenarios"]
    )
    environnement = e["environment"] or {}
    limites = "".join(f"<li>{escape(limite)}</li>" for limite in stats["limites"])
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rapport ShadowLab — {escape(e["name"])}</title>
<style>
:root {{ --fond:#0f1218; --carte:#171b23; --trait:#262c38; --texte:#e6e8ee; --doux:#9aa3b2; --ok:#3fb27f;
  --det:#e5735a; --accent:#7aa2ff; }}
@media (prefers-color-scheme: light) {{ :root {{ --fond:#f6f7f9; --carte:#fff; --trait:#dde1e8; --texte:#1b2130;
  --doux:#5d6677; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--fond); color:var(--texte); font:14px/1.5 system-ui,-apple-system,sans-serif; }}
main {{ max-width:1180px; margin:0 auto; padding:32px 16px 64px; }}
h1 {{ font-size:24px; margin:0 0 4px; }} h2 {{ font-size:16px; margin:32px 0 10px; color:var(--doux);
  text-transform:uppercase; letter-spacing:.06em; }}
.meta {{ color:var(--doux); }}
.cartes {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin-top:20px; }}
.carte {{ background:var(--carte); border:1px solid var(--trait); border-radius:10px; padding:14px; }}
.carte b {{ display:block; font-size:22px; }} .carte span {{ color:var(--doux); font-size:12px; }}
.tableau {{ overflow-x:auto; background:var(--carte); border:1px solid var(--trait); border-radius:10px; }}
table {{ border-collapse:collapse; width:100%; min-width:720px; }}
th, td {{ padding:8px 12px; border-bottom:1px solid var(--trait); text-align:left; vertical-align:top; }}
thead th {{ color:var(--doux); font-weight:500; font-size:12px; }}
th small, td small {{ display:block; color:var(--doux); font-weight:400; font-size:11px; }}
.val {{ font-variant-numeric:tabular-nums; }} .ic {{ color:var(--doux); font-size:11px; margin-left:6px; }}
.nm {{ color:var(--doux); }}
.barre {{ display:block; height:4px; background:var(--trait); border-radius:2px; margin-bottom:4px; max-width:160px; }}
.barre i {{ display:block; height:100%; border-radius:2px; }}
.barre.ok i {{ background:var(--ok); }} .barre.det i {{ background:var(--det); }}
ul {{ color:var(--doux); }}
</style></head><body><main>
<h1>Rapport — {escape(e["name"])}</h1>
<p class="meta">Expérience n° {e["id"]} · {escape(e["status"])} · créée le {escape(e["created_at"][:19].replace("T", " "))}
 · graine {e["seed"]} · {escape(str(environnement.get("systeme", "")))} · Python {escape(str(environnement.get("python", "")))}</p>
<p>{escape(e["description"])}</p>
<div class="cartes">
<div class="carte"><b>{stats["passages"]}</b><span>passages</span></div>
<div class="carte"><b>{len(stats["moteurs"])}</b><span>moteurs</span></div>
<div class="carte"><b>{len({s["scenario"] for s in stats["scenarios"]})}</b><span>scénarios</span></div>
<div class="carte"><b>{stats["sessions_humaines"]["n"]}</b><span>sessions humaines de référence</span></div>
</div>
<h2>Moteurs : réussite et performances</h2>
<div class="tableau"><table><thead><tr><th>Moteur</th><th>Passages</th><th>Réussite [IC 95 %]</th><th>Erreurs</th>
<th>Médiane (ms)</th><th>p95</th><th>p99</th><th>CPU moyen / passage</th><th>Mémoire moy. / max (Mo)</th></tr></thead>
<tbody>{lignes_moteurs}</tbody></table></div>
<h2>Taux de détection par détecteur [IC 95 %]</h2>
<div class="tableau"><table><thead><tr><th>Moteur</th>{entete_det}</tr></thead><tbody>{lignes_detection}</tbody></table></div>
<h2>Qualité des détecteurs</h2>
<div class="tableau"><table><thead><tr><th>Détecteur</th><th>Rappel</th><th>Précision</th><th>F1</th>
<th>Faux positifs (humains)</th><th>Sessions humaines</th></tr></thead><tbody>{lignes_qualite}</tbody></table></div>
<h2>Par scénario</h2>
<div class="tableau"><table><thead><tr><th>Moteur</th><th>Scénario</th><th>Passages</th><th>Réussite</th>
<th>Médiane (ms)</th><th>p95</th></tr></thead><tbody>{lignes_scenarios}</tbody></table></div>
<h2>Limites</h2><ul>{limites}</ul>
<p class="meta">n. m. : non mesurable. Généré par NOEZIA ShadowLab.</p>
</main></body></html>"""


def exporter(cx: sqlite3.Connection, experiment_id: int, dossier: Path, formats: list[str]) -> list[Path]:
    dossier.mkdir(parents=True, exist_ok=True)
    stats = statistiques(cx, experiment_id)
    fichiers = []
    if "json" in formats:
        chemin = dossier / "statistiques.json"
        chemin.write_text(json.dumps(stats, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        fichiers.append(chemin)
    if "csv" in formats:
        chemin = dossier / "passages.csv"
        chemin.write_text(lignes_csv(cx, experiment_id), encoding="utf-8")
        fichiers.append(chemin)
    if "html" in formats:
        chemin = dossier / "rapport.html"
        chemin.write_text(rapport_html(stats), encoding="utf-8")
        fichiers.append(chemin)
    return fichiers


def supprimer(cx: sqlite3.Connection, experiment_id: int) -> int:
    """Supprime une expérience, ses passages, observations et artefacts. Renvoie le nombre de passages."""
    jetons = [
        r["session_token"]
        for r in cx.execute("SELECT session_token FROM runs WHERE experiment_id = ?", (experiment_id,))
    ]
    fichiers = [
        Path(r["file_path"])
        for r in cx.execute(
            "SELECT a.file_path FROM artifacts a JOIN runs r ON r.id = a.run_id WHERE r.experiment_id = ?",
            (experiment_id,),
        )
    ]
    with db.transaction(cx):
        for i in range(0, len(jetons), 500):
            lot = jetons[i : i + 500]
            marques = ",".join("?" * len(lot))
            cx.execute(f"DELETE FROM observations_http WHERE session_token IN ({marques})", lot)
            cx.execute(f"DELETE FROM observations_js WHERE session_token IN ({marques})", lot)
        cx.execute("DELETE FROM experiments WHERE id = ?", (experiment_id,))
    for f in fichiers:
        f.unlink(missing_ok=True)
    return len(jetons)

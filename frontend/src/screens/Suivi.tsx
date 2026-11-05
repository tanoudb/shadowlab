import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { obtenir, poster } from "../api";
import { terminal, usePousseeProgression } from "../hooks";
import type { PassageLigne, Progression } from "../types";
import { Etat } from "../ui";

const ms = (v: number | null) => (v == null ? "—" : `${Math.round(v)} ms`);
const secs = (v: number | null) => (v == null ? null : v < 90 ? `${Math.round(v)} s` : `${Math.round(v / 60)} min`);

function Tuile({ libelle, valeur, ton }: { libelle: string; valeur: number | string; ton?: string }) {
  return (
    <div className={`tuile ${ton ?? ""}`}>
      <span className="tuile-valeur">{valeur}</span>
      <span className="tuile-libelle">{libelle}</span>
    </div>
  );
}

export default function Suivi() {
  const { id } = useParams();
  const eid = Number(id);
  const qc = useQueryClient();

  const progQ = useQuery({
    queryKey: ["progression", eid],
    queryFn: () => obtenir<Progression>(`/experiences/${eid}/progression`),
    refetchInterval: (q) => (terminal(q.state.data?.etat) ? false : 2000),
  });
  usePousseeProgression(eid);

  const enCours = progQ.data ? !terminal(progQ.data.etat) : false;
  const passagesQ = useQuery({
    queryKey: ["passages", eid],
    queryFn: () => obtenir<PassageLigne[]>(`/experiences/${eid}/passages?limite=300`),
    refetchInterval: enCours ? 3000 : false,
  });

  const arreter = useMutation({
    mutationFn: () => poster("/arret"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["progression", eid] }),
  });
  const reprendre = useMutation({
    mutationFn: () => poster(`/experiences/${eid}/reprendre`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["progression", eid] }),
  });

  // Rafraîchir la table des passages à chaque avancement (y compris le dernier, une fois terminé).
  const faits = progQ.data?.faits ?? 0;
  useEffect(() => {
    if (eid > 0) qc.invalidateQueries({ queryKey: ["passages", eid] });
  }, [faits, eid, qc]);

  return (
    <section>
      <div className="section-titre">
        <h1>Suivi — expérience #{eid}</h1>
        <Link to="/experiences" className="lien">
          ← toutes les expériences
        </Link>
      </div>

      <Etat q={progQ}>
        {(p) => {
          const st = p.par_statut;
          const eta = secs(p.eta_secondes);
          return (
            <>
              <div className="suivi-entete">
                <span className={`pastille ${p.etat}`}>{p.etat}</span>
                {enCours && (
                  <button type="button" onClick={() => arreter.mutate()} disabled={arreter.isPending}>
                    {arreter.isPending ? "Arrêt demandé…" : "Arrêter"}
                  </button>
                )}
                {(p.etat === "interrompu" || p.etat === "termine_incomplet") && (
                  <button type="button" className="primaire" onClick={() => reprendre.mutate()} disabled={reprendre.isPending}>
                    {reprendre.isPending ? "Reprise…" : "Reprendre"}
                  </button>
                )}
                {arreter.isSuccess && <span className="info">Arrêt demandé : la campagne s'arrête après le passage en cours.</span>}
                {reprendre.isError && <span className="champ-erreur">Reprise impossible (campagne déjà en cours ?).</span>}
              </div>

              <div className="barre-progression" role="progressbar" aria-valuenow={p.pourcentage}>
                <div className="barre-remplissage" style={{ width: `${p.pourcentage}%` }} />
                <span className="barre-texte">
                  {p.faits} / {p.total} passages ({p.pourcentage}%){eta && enCours ? ` · ~${eta} restant` : ""}
                </span>
              </div>

              <div className="tuiles">
                <Tuile libelle="réussis" valeur={st.reussi ?? 0} ton="ok" />
                <Tuile libelle="échecs" valeur={st.echec ?? 0} ton="attention" />
                <Tuile libelle="erreurs" valeur={st.erreur ?? 0} ton={(st.erreur ?? 0) > 0 ? "ko" : ""} />
                <Tuile libelle="en cours" valeur={p.en_cours} />
                <Tuile libelle="durée moyenne" valeur={ms(p.duree_moyenne_ms)} />
              </div>

              {Object.keys(p.par_issue).length > 0 && (
                <div className="issues">
                  <h2>Issues</h2>
                  <div className="etiquettes">
                    {Object.entries(p.par_issue).map(([issue, n]) => (
                      <span key={issue} className="etiquette">
                        {issue} · {n}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {(st.erreur ?? 0) > 0 && (
                <p className="message avert">
                  {st.erreur} passage(s) en erreur technique : à exclure des taux de réussite. Ouvrez un passage pour la cause exacte.
                </p>
              )}
            </>
          );
        }}
      </Etat>

      <h2 style={{ marginTop: 22 }}>Passages</h2>
      <Etat q={passagesQ}>
        {(passages) =>
          passages.length === 0 ? (
            <p className="info">Aucun passage enregistré pour l'instant.</p>
          ) : (
            <table className="tableau">
              <thead>
                <tr>
                  <th className="num">#</th>
                  <th>Moteur</th>
                  <th>Scénario</th>
                  <th className="num">Rép.</th>
                  <th>Statut</th>
                  <th className="num">Durée</th>
                  <th className="num">Détections</th>
                </tr>
              </thead>
              <tbody>
                {passages.map((r) => (
                  <tr key={r.id}>
                    <td className="num">
                      <Link to={`/passages/${r.id}`}>{r.id}</Link>
                    </td>
                    <td className="mono">{r.moteur}</td>
                    <td className="mono">{r.scenario}</td>
                    <td className="num">{r.repetition}</td>
                    <td>
                      <span className={`pastille ${r.status}`}>{r.status}</span>
                    </td>
                    <td className="num">{ms(r.duration_ms)}</td>
                    <td className="num">{r.detections} / 4</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        }
      </Etat>
    </section>
  );
}

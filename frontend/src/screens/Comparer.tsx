import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { obtenir } from "../api";
import type { Cellule, ExperienceListe, Matrice } from "../types";
import { Etat } from "../ui";

// Intervalle de Wilson à 95 % : honnête sur les petits effectifs, contrairement à l'intervalle normal.
function wilson(reussis: number, n: number): [number, number] | null {
  if (n === 0) return null;
  const z = 1.96;
  const p = reussis / n;
  const d = 1 + (z * z) / n;
  const centre = (p + (z * z) / (2 * n)) / d;
  const demi = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d;
  return [Math.max(0, centre - demi), Math.min(1, centre + demi)];
}

// Taux de réussite sur les tentatives valides (réussis + échecs). Les erreurs techniques sont exclues.
function taux(c: Cellule): { valide: number; taux: number | null; ci: [number, number] | null } {
  const valide = c.reussis + c.echecs;
  const t = valide > 0 ? c.reussis / valide : null;
  return { valide, taux: t, ci: wilson(c.reussis, valide) };
}

function CelluleTaux({ c, meilleur }: { c: Cellule | undefined; meilleur: boolean }) {
  if (!c) return <td className="sous">—</td>;
  const { valide, taux: t, ci } = taux(c);
  if (t === null) return <td className="sous">pas de donnée valide{c.erreurs > 0 ? ` (${c.erreurs} err.)` : ""}</td>;
  return (
    <td className={`num ${meilleur ? "meilleur" : ""}`}>
      <b>{(t * 100).toFixed(0)}%</b>
      {ci && (
        <span className="ci">
          [{(ci[0] * 100).toFixed(0)}–{(ci[1] * 100).toFixed(0)}]
        </span>
      )}
      <span className="ci">n={valide}</span>
      {c.erreurs > 0 && <span className="ci avert-point" title={`${c.erreurs} erreurs techniques exclues`}>⚠{c.erreurs}</span>}
    </td>
  );
}

export default function Comparer() {
  const experiencesQ = useQuery({ queryKey: ["experiences"], queryFn: () => obtenir<ExperienceListe[]>("/experiences") });
  const [eid, setEid] = useState(0);
  useEffect(() => {
    if (eid === 0 && experiencesQ.data && experiencesQ.data.length > 0) setEid(experiencesQ.data[0].id);
  }, [eid, experiencesQ.data]);

  const matriceQ = useQuery({
    queryKey: ["matrice", eid],
    queryFn: () => obtenir<Matrice>(`/experiences/${eid}/matrice`),
    enabled: eid > 0,
  });

  return (
    <section>
      <div className="section-titre">
        <h1>Comparer les moteurs</h1>
        {experiencesQ.data && (
          <label className="sous">
            Expérience{" "}
            <select value={eid} onChange={(e) => setEid(Number(e.target.value))}>
              {experiencesQ.data.map((x) => (
                <option key={x.id} value={x.id}>
                  #{x.id} · {x.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <p className="chapeau">
        Comparaison à conditions identiques : les moteurs d'une même expérience, stratifiés par protection.
      </p>

      {eid > 0 && (
        <Etat q={matriceQ}>
          {(m) =>
            m.moteurs.length < 2 ? (
              <p className="message avert">
                Cette expérience n'a qu'un moteur. Pour comparer, lancez une campagne avec au moins deux moteurs.
              </p>
            ) : (
              <>
                <h2>Taux de réussite par protection</h2>
                <table className="tableau">
                  <thead>
                    <tr>
                      <th>Protection</th>
                      {m.moteurs.map((mo) => (
                        <th key={mo} className="num mono">
                          {mo}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {m.protections.map((prot) => {
                      const ligne = m.cellules[prot] ?? {};
                      const tauxParMoteur = m.moteurs.map((mo) => {
                        const c = ligne[mo];
                        return c ? taux(c).taux : null;
                      });
                      const meilleur = Math.max(...tauxParMoteur.map((t) => t ?? -1));
                      return (
                        <tr key={prot}>
                          <td>
                            <span className="niveau">{prot}</span>
                          </td>
                          {m.moteurs.map((mo, i) => (
                            <CelluleTaux key={mo} c={ligne[mo]} meilleur={meilleur > -1 && tauxParMoteur[i] === meilleur} />
                          ))}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>

                <h2 style={{ marginTop: 20 }}>Durée moyenne (ms, hors erreurs)</h2>
                <table className="tableau">
                  <thead>
                    <tr>
                      <th>Protection</th>
                      {m.moteurs.map((mo) => (
                        <th key={mo} className="num mono">
                          {mo}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {m.protections.map((prot) => (
                      <tr key={prot}>
                        <td>
                          <span className="niveau">{prot}</span>
                        </td>
                        {m.moteurs.map((mo) => {
                          const c = m.cellules[prot]?.[mo];
                          return (
                            <td key={mo} className="num">
                              {c?.duree_moy != null ? Math.round(c.duree_moy) : "—"}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>

                <div className="message avert" style={{ marginTop: 16 }}>
                  <b>Comment lire :</b> taux = réussis / (réussis + échecs) ; les erreurs techniques (⚠) sont exclues
                  du dénominateur. Intervalles de Wilson à 95 % : s'ils se recouvrent, l'écart n'est pas concluant.
                  {m.concurrence > 1
                    ? ` Concurrence ${m.concurrence} : les durées ne sont pas comparables à une exécution séquentielle.`
                    : " Concurrence 1 : durées comparables."}
                </div>
              </>
            )
          }
        </Etat>
      )}
    </section>
  );
}

import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { obtenir } from "../api";
import type { Detection, PassageDetail } from "../types";
import { Etat, Puce } from "../ui";

const ms = (v: number | null) => (v == null ? "—" : `${Math.round(v)} ms`);
const mo = (v: number | null | undefined) => (v == null ? "—" : `${(v / 1_048_576).toFixed(1)} Mo`);

function classement(c: string): string {
  return c === "automatise" ? "détecté automate" : c === "humain" ? "vu humain" : "indéterminé";
}

function JsonBloc({ titre, valeur }: { titre: string; valeur: unknown }) {
  return (
    <details className="repli">
      <summary>{titre}</summary>
      <pre className="json">{JSON.stringify(valeur, null, 2)}</pre>
    </details>
  );
}

function DetectionLigne({ d }: { d: Detection }) {
  return (
    <div className="detection">
      <div className="detection-tete">
        <code>{d.detector_name}</code>
        <Puce actif={d.classification !== "automatise"}>{classement(d.classification)}</Puce>
        <span className="sous">confiance {(d.confidence * 100).toFixed(0)}%</span>
      </div>
      {d.signals.length > 0 && (
        <ul className="signaux">
          {d.signals.map((s) => (
            <li key={s.code}>
              <code>{s.code}</code> — {s.description} <span className="sous">(poids {s.poids})</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function Passage() {
  const { id } = useParams();
  const rid = Number(id);
  const q = useQuery({ queryKey: ["passage", rid], queryFn: () => obtenir<PassageDetail>(`/passages/${rid}`) });

  return (
    <section>
      <Etat q={q}>
        {(d) => {
          const p = d.passage;
          const detections = d.detections ?? [];
          const decisions = d.decisions_couches ?? [];
          const requetes = d.requetes ?? [];
          const captures = (d.artefacts ?? []).filter((a) => a.type === "screenshot");
          return (
            <>
              <h1>
                Passage #{p.id} · <span className="mono">{p.moteur}</span> · <span className="mono">{p.scenario}</span>
              </h1>
              <p className="etiquettes">
                <span className="niveau">{p.protection}</span>
                <span className={`pastille ${p.status}`}>{p.status}</span>
                <span className="etiquette">répétition {p.repetition}</span>
                <span className="etiquette">{ms(p.duration_ms)}</span>
              </p>

              {/* Verdict : la raison précise, pas seulement réussi/échec. */}
              <div className="carte verdict">
                <h2>Verdict</h2>
                <p>
                  <b>Issue :</b> {p.issue ?? "—"}
                </p>
                {p.cause && (
                  <p>
                    <b>Cause :</b> {p.cause}
                  </p>
                )}
                {p.error && <p className="message erreur">{p.error}</p>}
              </div>

              {decisions.length > 0 && (
                <div className="carte">
                  <h2>Décisions des protections (par couche)</h2>
                  <table className="tableau">
                    <thead>
                      <tr>
                        <th>Couche</th>
                        <th>Décision</th>
                        <th>Motifs</th>
                      </tr>
                    </thead>
                    <tbody>
                      {decisions.map((c, i) => (
                        <tr key={`${c.couche}-${i}`}>
                          <td className="mono">{c.couche}</td>
                          <td>
                            <span className={`pastille ${c.decision === "bloque" ? "erreur" : "reussi"}`}>
                              {c.decision}
                            </span>
                          </td>
                          <td className="sous">
                            {(c.motifs ?? []).map((m) => m.code ?? m.description).filter(Boolean).join(", ") || "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {detections.length > 0 && (
                <div className="carte">
                  <h2>Détecteurs</h2>
                  {detections.map((det) => (
                    <DetectionLigne key={det.detector_name} d={det} />
                  ))}
                </div>
              )}

              {requetes.length > 0 && (
                <div className="carte">
                  <h2>Déroulé des requêtes ({requetes.length})</h2>
                  <table className="tableau">
                    <thead>
                      <tr>
                        <th>Méthode</th>
                        <th>Chemin</th>
                        <th className="num">Statut</th>
                        <th>HTTP</th>
                        <th>Source</th>
                        <th className="num">En-têtes</th>
                      </tr>
                    </thead>
                    <tbody>
                      {requetes.map((r, i) => (
                        <tr key={i}>
                          <td className="mono">{r.method}</td>
                          <td className="mono">{r.path}</td>
                          <td className="num">{r.status ?? "—"}</td>
                          <td>{r.http_version ?? "—"}</td>
                          <td className="sous">{r.source}</td>
                          <td className="num">{r.nb_entetes}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {captures.length > 0 && (
                <div className="carte">
                  <h2>Captures d'écran</h2>
                  {captures.map((a) => (
                    <a key={a.id} href={a.url} target="_blank" rel="noopener">
                      <img className="capture" src={a.url} alt={`capture du passage ${p.id}`} />
                    </a>
                  ))}
                </div>
              )}

              {d.mesures && (
                <div className="carte">
                  <h2>Mesures</h2>
                  <div className="tuiles">
                    <div className="tuile">
                      <span className="tuile-valeur">{ms(d.mesures.cpu_time_ms ?? null)}</span>
                      <span className="tuile-libelle">temps CPU</span>
                    </div>
                    <div className="tuile">
                      <span className="tuile-valeur">{mo(d.mesures.memory_usage)}</span>
                      <span className="tuile-libelle">mémoire</span>
                    </div>
                    <div className="tuile">
                      <span className="tuile-valeur">{d.mesures.request_count ?? "—"}</span>
                      <span className="tuile-libelle">requêtes</span>
                    </div>
                  </div>
                </div>
              )}

              {d.empreinte && (
                <div className="carte">
                  <h2>Empreinte</h2>
                  <JsonBloc titre="Propriétés navigateur (JS)" valeur={d.empreinte.browser_properties} />
                  <JsonBloc titre="En-têtes HTTP" valeur={d.empreinte.http_properties} />
                  <JsonBloc titre="TLS" valeur={d.empreinte.tls_properties} />
                  <JsonBloc titre="Session" valeur={d.empreinte.session_properties} />
                </div>
              )}
            </>
          );
        }}
      </Etat>
    </section>
  );
}

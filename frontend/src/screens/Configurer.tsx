import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ErreurApi, obtenir, poster } from "../api";
import type { MoteursReponse, ProtectionsReponse, Reglages, Scenario, Validation } from "../types";

const MOTIF_NOM = /^[a-z0-9][a-z0-9_-]*$/;

function basculer(liste: string[], valeur: string): string[] {
  return liste.includes(valeur) ? liste.filter((v) => v !== valeur) : [...liste, valeur];
}

export default function Configurer() {
  const navigate = useNavigate();
  const moteursQ = useQuery({ queryKey: ["moteurs"], queryFn: () => obtenir<MoteursReponse>("/moteurs") });
  const scenariosQ = useQuery({ queryKey: ["scenarios"], queryFn: () => obtenir<Scenario[]>("/scenarios") });
  const protectionsQ = useQuery({ queryKey: ["protections"], queryFn: () => obtenir<ProtectionsReponse>("/protections") });
  const reglagesQ = useQuery({
    queryKey: ["reglages"],
    queryFn: () => obtenir<Reglages>("/reglages"),
    refetchInterval: 5000,
  });

  const [nom, setNom] = useState("essai");
  const [moteurs, setMoteurs] = useState<string[]>([]);
  const [protections, setProtections] = useState<string[]>(["01"]);
  const [scenarios, setScenarios] = useState<string[]>([]);
  const [repetitions, setRepetitions] = useState(5);
  const [concurrence, setConcurrence] = useState(1);
  const [graine, setGraine] = useState("");

  const experiment = useMemo(() => {
    const e: Record<string, unknown> = { name: nom, engines: moteurs, protections, scenarios, repetitions };
    if (concurrence > 1) e.concurrency = concurrence;
    if (graine.trim() !== "") e.seed = Number(graine);
    return e;
  }, [nom, moteurs, protections, scenarios, repetitions, concurrence, graine]);

  const nomValide = MOTIF_NOM.test(nom);
  const complet = moteurs.length > 0 && protections.length > 0 && scenarios.length > 0 && repetitions >= 1 && nomValide;
  const totalLocal = moteurs.length * protections.length * scenarios.length * repetitions;
  const arenaRequise = protections.some((p) => p !== "01");

  const valideQ = useQuery({
    queryKey: ["valider", JSON.stringify(experiment)],
    queryFn: () => poster<Validation>("/experiences/valider", { experiment }),
    enabled: complet,
  });

  const lancer = useMutation({
    mutationFn: () => poster<{ id: number; statut: string }>("/experiences", { experiment }),
    onSuccess: (d) => navigate(`/experiences/${d.id}`),
  });

  const campagneEnCours = reglagesQ.data?.campagne_en_cours ?? false;
  const concurrenceMax = reglagesQ.data?.concurrence_max ?? 4;
  const serveurErreur = valideQ.data && !valideQ.data.valide ? valideQ.data.erreur : null;
  const peutLancer = complet && !campagneEnCours && !lancer.isPending && valideQ.data?.valide === true;

  return (
    <section className="configurer">
      <h1>Configurer une campagne</h1>
      <p className="chapeau">Choisissez quoi mesurer, contre quelles protections. Aucun YAML à écrire.</p>

      {campagneEnCours && (
        <p className="message avert">Une campagne est déjà en cours. Attendez sa fin ou arrêtez-la avant d'en lancer une autre.</p>
      )}

      <div className="section">
        <h2>Moteurs</h2>
        {moteursQ.data ? (
          <div className="liste-cases">
            {moteursQ.data.disponibles.map((m) => (
              <label key={m.name} className={`case ${m.pret ? "" : "indispo"}`} title={m.manque ?? ""}>
                <input
                  type="checkbox"
                  checked={moteurs.includes(m.name)}
                  disabled={!m.pret}
                  onChange={() => setMoteurs((l) => basculer(l, m.name))}
                />
                <span className="mono">{m.name}</span>
                <span className="case-sous">{m.pret ? m.runtime : "à installer"}</span>
              </label>
            ))}
          </div>
        ) : (
          <p className="info">Chargement…</p>
        )}
      </div>

      <div className="section">
        <h2>Protections</h2>
        {protectionsQ.data ? (
          <div className="liste-cases">
            {protectionsQ.data.protections.map((p) => (
              <label key={p.code} className="case">
                <input
                  type="checkbox"
                  checked={protections.includes(p.code)}
                  onChange={() => setProtections((l) => basculer(l, p.code))}
                />
                <span>
                  <span className="niveau">{p.code}</span> {p.nom}
                </span>
              </label>
            ))}
          </div>
        ) : (
          <p className="info">Chargement…</p>
        )}
        {arenaRequise && (
          <p className="message avert">
            Les niveaux 02–06 exigent l'Arena démarrée : <code>uv run shadowlab arena demarrer</code>.
          </p>
        )}
      </div>

      <div className="section">
        <div className="section-titre">
          <h2>Scénarios</h2>
          {scenariosQ.data && (
            <button
              type="button"
              className="lien"
              onClick={() =>
                setScenarios(scenarios.length === scenariosQ.data!.length ? [] : scenariosQ.data!.map((s) => s.name))
              }
            >
              {scenariosQ.data.length === scenarios.length ? "Tout décocher" : "Tout cocher"}
            </button>
          )}
        </div>
        {scenariosQ.data ? (
          <div className="liste-cases">
            {scenariosQ.data.map((s) => (
              <label key={s.name} className="case" title={s.description}>
                <input
                  type="checkbox"
                  checked={scenarios.includes(s.name)}
                  onChange={() => setScenarios((l) => basculer(l, s.name))}
                />
                <span className="mono">{s.name}</span>
                {s.javascript && <span className="case-sous">JS</span>}
              </label>
            ))}
          </div>
        ) : (
          <p className="info">Chargement…</p>
        )}
      </div>

      <div className="section">
        <h2>Paramètres</h2>
        <div className="params">
          <label>
            Nom
            <input value={nom} onChange={(e) => setNom(e.target.value)} />
            {!nomValide && <span className="champ-erreur">minuscules, chiffres, - et _ uniquement</span>}
          </label>
          <label>
            Répétitions
            <input
              type="number"
              min={1}
              max={10000}
              value={repetitions}
              onChange={(e) => setRepetitions(Math.max(1, Number(e.target.value) || 1))}
            />
          </label>
          <label>
            Concurrence (max {concurrenceMax})
            <input
              type="number"
              min={1}
              max={concurrenceMax}
              value={concurrence}
              onChange={(e) => setConcurrence(Math.min(concurrenceMax, Math.max(1, Number(e.target.value) || 1)))}
            />
          </label>
          <label>
            Graine (vide = aléatoire)
            <input value={graine} onChange={(e) => setGraine(e.target.value.replace(/[^0-9]/g, ""))} placeholder="auto" />
          </label>
        </div>
      </div>

      <div className="recap-barre">
        <div className="recap-texte">
          {complet ? (
            <>
              <b>{totalLocal}</b> passages — {moteurs.length} moteur(s) × {protections.length} protection(s) ×{" "}
              {scenarios.length} scénario(s) × {repetitions} répétition(s)
            </>
          ) : (
            <span className="info">Choisissez au moins un moteur, une protection et un scénario.</span>
          )}
          {serveurErreur && <span className="champ-erreur"> · {serveurErreur}</span>}
          {lancer.isError && (
            <span className="champ-erreur">
              {" "}
              · {lancer.error instanceof ErreurApi ? `${lancer.error.statut} — ${lancer.error.message}` : "échec du lancement"}
            </span>
          )}
        </div>
        <button type="button" className="primaire" disabled={!peutLancer} onClick={() => lancer.mutate()}>
          {lancer.isPending ? "Lancement…" : "Lancer la campagne"}
        </button>
      </div>
    </section>
  );
}

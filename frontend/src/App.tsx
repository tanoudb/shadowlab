import { useQuery } from "@tanstack/react-query";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { obtenir } from "./api";
import Configurer from "./screens/Configurer";
import Experiences from "./screens/Experiences";
import Moteurs from "./screens/Moteurs";
import Protections from "./screens/Protections";
import Suivi from "./screens/Suivi";

function Sante() {
  const q = useQuery({
    queryKey: ["sante"],
    queryFn: () => obtenir<{ statut: string }>("/sante"),
    refetchInterval: 10000,
  });
  const etat = q.isError ? "ko" : q.data ? "ok" : "";
  return (
    <span className={`sante ${etat}`}>
      <i className="point" /> {q.isError ? "API injoignable" : q.data ? "API connectée" : "…"}
    </span>
  );
}

// Navigation par parcours, pas par type de donnée : Configurer → Lancer → Observer → Comprendre → Comparer.
const LIENS = [
  { to: "/configurer", texte: "Configurer" },
  { to: "/experiences", texte: "Expériences" },
  { to: "/comparer", texte: "Comparer" },
];
const LIENS_REF = [
  { to: "/moteurs", texte: "Moteurs" },
  { to: "/protections", texte: "Protections" },
];

function AVenir({ titre }: { titre: string }) {
  return (
    <section>
      <h1>{titre}</h1>
      <p className="info">Écran en cours de construction.</p>
    </section>
  );
}

export default function App() {
  return (
    <div className="cadre">
      <aside className="lateral">
        <div className="marque">
          <span className="logo" aria-hidden="true" />
          <div>
            <b>ShadowLab</b>
            <small>NOEZIA · laboratoire local</small>
          </div>
        </div>
        <nav aria-label="Parcours">
          {LIENS.map((l) => (
            <NavLink key={l.to} to={l.to}>
              {l.texte}
            </NavLink>
          ))}
          <div className="separateur">Référence</div>
          {LIENS_REF.map((l) => (
            <NavLink key={l.to} to={l.to}>
              {l.texte}
            </NavLink>
          ))}
        </nav>
        <div className="pied-lateral">
          <Sante />
          <a href="/api/docs" target="_blank" rel="noopener">
            API ↗
          </a>
        </div>
      </aside>
      <main className="principal" tabIndex={-1}>
        <Routes>
          <Route path="/" element={<Navigate to="/configurer" replace />} />
          <Route path="/configurer" element={<Configurer />} />
          <Route path="/experiences" element={<Experiences />} />
          <Route path="/experiences/:id" element={<Suivi />} />
          <Route path="/passages/:id" element={<AVenir titre="Passage" />} />
          <Route path="/comparer" element={<AVenir titre="Comparer" />} />
          <Route path="/moteurs" element={<Moteurs />} />
          <Route path="/protections" element={<Protections />} />
          <Route path="*" element={<AVenir titre="Page introuvable" />} />
        </Routes>
      </main>
    </div>
  );
}

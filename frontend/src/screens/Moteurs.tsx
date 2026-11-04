import { useQuery } from "@tanstack/react-query";
import { obtenir } from "../api";
import type { MoteursReponse } from "../types";
import { Etat, Puce } from "../ui";

export default function Moteurs() {
  const q = useQuery({ queryKey: ["moteurs"], queryFn: () => obtenir<MoteursReponse>("/moteurs") });
  return (
    <section>
      <h1>Moteurs</h1>
      <p className="chapeau">Les moteurs d'automatisation que ce laboratoire sait piloter.</p>
      <Etat q={q}>
        {(d) => (
          <div className="grille">
            {d.disponibles.map((m) => (
              <article className="carte" key={m.name}>
                <h2 className="mono">{m.name}</h2>
                <p className="etiquettes">
                  <span className="etiquette">{m.runtime}</span>
                  <Puce actif={m.javascript}>{m.javascript ? "exécute JS" : "sans JS"}</Puce>
                </p>
                <p className="sous">{m.description || "—"}</p>
              </article>
            ))}
          </div>
        )}
      </Etat>
    </section>
  );
}

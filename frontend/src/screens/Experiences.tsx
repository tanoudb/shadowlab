import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { obtenir } from "../api";
import type { ExperienceListe } from "../types";
import { Etat } from "../ui";

const date = (s: string) => (s ? s.slice(0, 19).replace("T", " ") : "—");

export default function Experiences() {
  const q = useQuery({
    queryKey: ["experiences"],
    queryFn: () => obtenir<ExperienceListe[]>("/experiences"),
    refetchInterval: 5000,
  });
  return (
    <section>
      <h1>Expériences</h1>
      <p className="chapeau">Historique des campagnes. Cliquez pour suivre le déroulé ou examiner les résultats.</p>
      <Etat q={q}>
        {(d) =>
          d.length === 0 ? (
            <p className="info">Aucune expérience pour l'instant. Lancez-en une depuis « Configurer ».</p>
          ) : (
            <table className="tableau">
              <thead>
                <tr>
                  <th className="num">#</th>
                  <th>Nom</th>
                  <th>État</th>
                  <th className="num">Passages</th>
                  <th className="num">Réussis</th>
                  <th className="num">Erreurs</th>
                  <th>Créée</th>
                </tr>
              </thead>
              <tbody>
                {d.map((e) => (
                  <tr key={e.id}>
                    <td className="num">{e.id}</td>
                    <td>
                      <Link to={`/experiences/${e.id}`}>{e.name}</Link>
                    </td>
                    <td>
                      <span className={`pastille ${e.status}`}>{e.status}</span>
                    </td>
                    <td className="num">{e.passages}</td>
                    <td className="num">{e.reussis ?? 0}</td>
                    <td className="num">{e.erreurs ?? 0}</td>
                    <td className="sous">{date(e.created_at)}</td>
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

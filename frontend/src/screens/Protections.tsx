import { useQuery } from "@tanstack/react-query";
import { obtenir } from "../api";
import type { Protection, ProtectionsReponse } from "../types";
import { Etat } from "../ui";

function mecanismes(p: Protection): string[] {
  const m: string[] = [];
  if (p.baseline) return ["Aucune protection — site nu"];
  m.push(`Débit ${p.limitation.debit} req/s (rafale ${p.limitation.rafale})`);
  m.push(`WAF ${p.waf.mode === "blocage" ? "en blocage" : "en détection"} · paranoïa ${p.waf.paranoia}`);
  if (p.defi_js.actif) m.push(`Défi JS (difficulté ${p.defi_js.difficulte}${p.defi_js.lier_tls ? ", lié TLS" : ""})`);
  if (p.captcha) m.push("CAPTCHA démo");
  if (p.fingerprinting.actif) m.push(`Fingerprinting${p.fingerprinting.bloquer !== "non" ? ` (bloque ${p.fingerprinting.bloquer})` : ""}`);
  if (p.honeypots) m.push("Honeypots");
  if (p.turnstile) m.push("Turnstile (clés de test)");
  if (p.recaptcha) m.push("reCAPTCHA v2 (clés de test)");
  return m;
}

export default function Protections() {
  const q = useQuery({ queryKey: ["protections"], queryFn: () => obtenir<ProtectionsReponse>("/protections") });
  return (
    <section>
      <h1>Protections de l'Arena</h1>
      <p className="chapeau">Six niveaux progressifs. Chaque niveau empile les mécanismes du précédent.</p>
      <Etat q={q}>
        {(d) => (
          <div className="grille">
            {d.protections.map((p) => (
              <article className="carte" key={p.code}>
                <h2>
                  <span className="niveau">{p.code}</span> {p.nom}
                </h2>
                {p.description && <p className="sous">{p.description}</p>}
                <ul className="mecanismes">
                  {mecanismes(p).map((m) => (
                    <li key={m}>{m}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        )}
      </Etat>
    </section>
  );
}

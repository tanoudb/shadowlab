import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { ErreurApi } from "./api";

// Enveloppe d'affichage uniforme : chargement, erreur explicite, données. Jamais d'écran vide silencieux.
export function Etat<T>({ q, children }: { q: UseQueryResult<T>; children: (d: T) => ReactNode }) {
  if (q.isLoading) return <p className="info">Chargement…</p>;
  if (q.isError) {
    const e = q.error;
    const msg = e instanceof ErreurApi ? `${e.statut} — ${e.message}` : String(e);
    return <p className="message erreur">Erreur : {msg}</p>;
  }
  if (q.data === undefined) return <p className="info">Aucune donnée.</p>;
  return <>{children(q.data)}</>;
}

export function Puce({ actif, children }: { actif: boolean; children: ReactNode }) {
  return <span className={`puce ${actif ? "on" : "off"}`}>{children}</span>;
}

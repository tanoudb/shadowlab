import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import type { Progression } from "./types";

export const terminal = (etat: string | undefined): boolean =>
  etat !== undefined && !["creee", "en_cours"].includes(etat);

// Pousse la progression en temps réel (SSE) dans le cache react-query. Si le flux échoue,
// le polling de la requête ["progression", id] prend le relais : une seule source de vérité pour l'UI.
export function usePousseeProgression(id: number) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!Number.isFinite(id)) return;
    const src = new EventSource(`/api/experiences/${id}/flux`);
    src.onmessage = (e) => {
      try {
        const p = JSON.parse(e.data) as Progression;
        qc.setQueryData(["progression", id], p);
        if (terminal(p.etat)) src.close();
      } catch {
        /* message malformé : ignoré, le polling reste la source fiable */
      }
    };
    src.onerror = () => src.close();
    return () => src.close();
  }, [id, qc]);
}

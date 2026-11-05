import type { Cellule } from "./types";

// Intervalle de Wilson à 95 % : honnête sur les petits effectifs, contrairement à l'intervalle normal.
export function wilson(reussis: number, n: number): [number, number] | null {
  if (n === 0) return null;
  const z = 1.96;
  const p = reussis / n;
  const d = 1 + (z * z) / n;
  const centre = (p + (z * z) / (2 * n)) / d;
  const demi = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d;
  return [Math.max(0, centre - demi), Math.min(1, centre + demi)];
}

// Taux de réussite sur les tentatives valides (réussis + échecs). Les erreurs techniques sont exclues.
export function taux(c: Cellule): { valide: number; taux: number | null; ci: [number, number] | null } {
  const valide = c.reussis + c.echecs;
  const t = valide > 0 ? c.reussis / valide : null;
  return { valide, taux: t, ci: wilson(c.reussis, valide) };
}

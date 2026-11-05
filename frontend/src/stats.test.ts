import { describe, expect, it } from "vitest";
import type { Cellule } from "./types";
import { taux, wilson } from "./stats";

const cellule = (p: Partial<Cellule>): Cellule => ({
  total: 0,
  reussis: 0,
  echecs: 0,
  erreurs: 0,
  duree_moy: null,
  ...p,
});

describe("wilson", () => {
  it("renvoie null quand il n'y a aucune observation", () => {
    expect(wilson(0, 0)).toBeNull();
  });

  it("encadre la proportion et reste borné à [0, 1]", () => {
    const [lo, hi] = wilson(10, 10)!;
    expect(lo).toBeGreaterThan(0.6);
    expect(hi).toBeLessThanOrEqual(1);
    expect(lo).toBeLessThan(hi);
  });

  it("donne un intervalle plus large sur un petit effectif", () => {
    const [, hiPetit] = wilson(1, 2)!;
    const [, hiGrand] = wilson(50, 100)!;
    const [loPetit] = wilson(1, 2)!;
    const [loGrand] = wilson(50, 100)!;
    expect(hiPetit - loPetit).toBeGreaterThan(hiGrand - loGrand);
  });
});

describe("taux", () => {
  it("exclut les erreurs techniques du dénominateur", () => {
    const r = taux(cellule({ reussis: 3, echecs: 1, erreurs: 10 }));
    expect(r.valide).toBe(4); // 10 erreurs ignorées
    expect(r.taux).toBeCloseTo(0.75);
  });

  it("renvoie un taux nul quand il n'y a que des erreurs", () => {
    const r = taux(cellule({ erreurs: 5 }));
    expect(r.valide).toBe(0);
    expect(r.taux).toBeNull();
    expect(r.ci).toBeNull();
  });
});

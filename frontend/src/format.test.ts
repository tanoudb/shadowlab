import { describe, expect, it } from "vitest";
import { mo } from "./format";

describe("mo", () => {
  it("affiche tel quel un pic de mémoire déjà en Mo", () => {
    expect(mo(1111.6)).toBe("1111.6 Mo");
  });

  it("n'applique aucune conversion d'octets", () => {
    expect(mo(0.5)).toBe("0.5 Mo");
  });

  it("affiche un tiret quand la mesure manque", () => {
    expect(mo(null)).toBe("—");
    expect(mo(undefined)).toBe("—");
  });
});

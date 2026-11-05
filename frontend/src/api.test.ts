import { afterEach, describe, expect, it, vi } from "vitest";
import { ErreurApi, obtenir, poster } from "./api";

function reponse(corps: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    statusText: "x",
    text: async () => (typeof corps === "string" ? corps : JSON.stringify(corps)),
  } as Response;
}

afterEach(() => vi.restoreAllMocks());

describe("obtenir", () => {
  it("renvoie le corps JSON parsé", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reponse({ statut: "ok" })));
    expect(await obtenir("/sante")).toEqual({ statut: "ok" });
  });

  it("lève ErreurApi avec le statut et le detail sur une réponse en erreur", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reponse({ detail: "introuvable" }, false, 404)));
    await expect(obtenir("/x")).rejects.toMatchObject({ statut: 404, message: "introuvable" });
    await expect(obtenir("/x")).rejects.toBeInstanceOf(ErreurApi);
  });
});

describe("poster", () => {
  it("ajoute l'en-tête d'écriture X-ShadowLab", async () => {
    const faux = vi.fn(async (_url: string, _init?: RequestInit) => reponse({ id: 1 }));
    vi.stubGlobal("fetch", faux);
    await poster("/experiences", { experiment: {} });
    const init = faux.mock.calls[0][1]!;
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["X-ShadowLab"]).toBe("1");
  });
});

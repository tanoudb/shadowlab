// Client HTTP minimal vers l'API locale ShadowLab. Toutes les écritures portent l'en-tête X-ShadowLab
// (qu'une page tierce ne peut pas ajouter sans autorisation CORS). Aucune donnée simulée : tout vient de /api.

export class ErreurApi extends Error {
  constructor(
    public readonly statut: number,
    message: string,
  ) {
    super(message);
    this.name = "ErreurApi";
  }
}

async function corps(r: Response): Promise<unknown> {
  const texte = await r.text();
  if (!texte) return null;
  try {
    return JSON.parse(texte);
  } catch {
    return texte;
  }
}

function detail(data: unknown, repli: string): string {
  if (data && typeof data === "object" && "detail" in data) {
    const d = (data as { detail: unknown }).detail;
    if (typeof d === "string") return d;
  }
  return repli;
}

export async function obtenir<T = unknown>(chemin: string): Promise<T> {
  const r = await fetch(`/api${chemin}`, { headers: { Accept: "application/json" } });
  const data = await corps(r);
  if (!r.ok) throw new ErreurApi(r.status, detail(data, r.statusText));
  return data as T;
}

export async function poster<T = unknown>(chemin: string, charge?: unknown): Promise<T> {
  const r = await fetch(`/api${chemin}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json", "X-ShadowLab": "1" },
    body: charge === undefined ? undefined : JSON.stringify(charge),
  });
  const data = await corps(r);
  if (!r.ok) throw new ErreurApi(r.status, detail(data, r.statusText));
  return data as T;
}

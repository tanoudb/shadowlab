// Mémoire d'un passage : la valeur arrive déjà en Mo (écrite ainsi par mesures.py), on ne la convertit pas.
export const mo = (v: number | null | undefined): string => (v == null ? "—" : `${v.toFixed(1)} Mo`);

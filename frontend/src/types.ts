// Formes de données renvoyées par l'API /api. Elles reflètent les endpoints réels (voir src/shadowlab/api.py).

export interface MoteurDisponible {
  name: string;
  runtime: string;
  categorie: string;
  javascript: boolean;
  description: string;
  pret: boolean;
  manque: string | null;
}

export interface MoteursReponse {
  disponibles: MoteurDisponible[];
  enregistres: unknown[];
}

export interface Scenario {
  name: string;
  description: string;
  javascript: boolean;
}

export interface Protection {
  code: string;
  nom: string;
  description: string;
  baseline: boolean;
  limitation: { debit: number; rafale: number };
  waf: { mode: string; paranoia: number; seuil: number };
  defi_js: { actif: boolean; difficulte: number; lier_tls: boolean };
  captcha: boolean;
  fingerprinting: { actif: boolean; bloquer: string };
  honeypots: boolean;
  turnstile: boolean;
  recaptcha: boolean;
}

export interface ProtectionsReponse {
  protections: Protection[];
}

export interface Reglages {
  hote: string;
  port: number;
  hotes_autorises: string[];
  memoire_max_mo: number;
  concurrence_max: number;
  base_donnees: string;
  jeton_configure: boolean;
  campagne_en_cours: boolean;
}

export interface Validation {
  valide: boolean;
  erreur?: string;
  nom?: string;
  seed?: number | null;
  total?: number;
  moteurs?: string[];
  protections?: string[];
  scenarios?: string[];
}

export interface ExperienceListe {
  id: number;
  name: string;
  description: string;
  created_at: string;
  status: string;
  seed: number | null;
  passages: number;
  reussis: number | null;
  erreurs: number | null;
}

export interface Progression {
  experience: number;
  etat: string;
  total: number;
  faits: number;
  restant: number;
  pourcentage: number;
  en_cours: number;
  par_statut: Record<string, number>;
  par_issue: Record<string, number>;
  duree_moyenne_ms: number | null;
  eta_secondes: number | null;
}

export interface PassageLigne {
  id: number;
  moteur: string;
  engine: string;
  scenario: string;
  repetition: number;
  status: string;
  duration_ms: number | null;
  error: string | null;
  cpu_usage: number | null;
  cpu_time_ms: number | null;
  memory_usage: number | null;
  request_count: number | null;
  detections: number;
}

"""Moteurs dont les dépendances entrent en conflit avec le laboratoire. Chacun tourne dans son environnement
(`moteurs_isoles/<projet>`), derrière le pont de `engines/pont.py`. Ces modules n'importent leur bibliothèque
qu'à l'exécution : le processus principal peut donc lire leurs caractéristiques sans l'avoir installée."""

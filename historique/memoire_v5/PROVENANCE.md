# Provenance — mémoire de la lignée V5

Reconstitution documentaire au 3 novembre 2026, pas archive certifiée d'une
release historique précise. Les trois modules sont copiés depuis les fichiers
homonymes de `src/alice/memory/` dans l'installation originale. Aucun changement
de contenu ; seules les fins de ligne sont normalisées en LF.

| Fichier public dans `extraits/` | SHA-256 |
| --- | --- |
| `store.py` | `70b71845f3483aa87f5a04fcd24ddc5d616a4e9c2d4870f6bc48a012300319a1` |
| `extractor.py` | `d88c3d813ffc3ee427d8a2d8cc265696ac4269a8ac5f85b89286f29ef9061ff2` |
| `query.py` | `f4a1972b6ebd18a0f7455e0591927028e1ca0c670ddd8131816836b24a6e59c7` |

Sources locales de l'explication, consultées dans le projet de travail :

- `PROJET.md` : distinction entre installation originale et laboratoire ; modèle
  Alice-v5-reliable conservé pour retour arrière, autre modèle désormais installé.
- `docs/reference_v5_conversations_roles.md` : référence V5 testée avec
  `BrainEngine` et des mémoires fictives ; ne certifie pas cette copie de code.
- `docs/memory_checkup_20260910.md`, section architecture : description antérieure
  du stockage, de l'extraction et du rappel, recoupée avec le code retrouvé.
- `src/alice/brain/engine.py` : méthodes `respond`, `_model_extraction`,
  `_recall_memories`, `close` et parcours `respond_ephemeral`.
- `src/alice/brain/context.py` : sélection des souvenirs sous budget.
- `config/alice.toml`, section `memory` : limites consultées de 24 événements
  et 12 souvenirs. La configuration privée n'est pas redistribuée.

Contrôles de publication : relecture des modules, égalité avec les sources après
normalisation des fins de ligne, analyse syntaxique Python, liens locaux et
recherche de formats de secrets. Aucun modèle exécuté, aucune base réelle
ouverte et aucun test conversationnel rejoué pour cette documentation.
La lecture du code ne constitue pas une preuve de fiabilité générale du modèle.

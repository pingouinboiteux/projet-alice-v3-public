# Alice actuelle — 5 novembre 2026

L'installation originale et le laboratoire sont distincts. Le travail fonctionnel
sur l'originale est en pause ; les essais actuels concernent le laboratoire.
Ce dépôt expose son code, sans ses données privées ni ses ressources de modèles.

| Partie | État actuel | Limites |
| --- | --- | --- |
| Dialogue | Gemma 4 26B-A4B Q4_0, moteur llama.cpp b12020 | Compréhension et cohérence non garanties |
| Voix | Sopro, référence originale, français, FP32, 2 étapes ; choix conservé | Sibilance encore perceptible ; référence audio exclue |
| Mémoire | Backend `v5_context`, stockage épisodique et sources | Stocker, retrouver et comprendre sont trois propriétés distinctes ; aucune fiabilité générale revendiquée |
| Personnalité | Consignes expressives et franches conservées | Un prompt ne garantit pas un avis cohérent |
| Actions | Outils locaux limités, confirmations et atelier encadré | Pas de contrôle général autonome du PC |
| Twitch / Discord | Lecture Twitch et raccord vocal Discord ; contexte public séparé | Les entrées externes n'obtiennent pas de droits locaux ni de souvenirs privés |
| Vision / initiative | Vision et parole spontanée non activées | Objectifs futurs, pas fonctions terminées |

## Chantier suivant : memoire entre sessions

Le proprietaire demande de passer a la suite en conservant le modele actuel.
Le jugement conversationnel reste imparfait : il est reporte, pas declare resolu.
La voix et la personnalite actives sont conservees.

Derniere campagne : 75 reponses synthetiques adaptatives examinees ; trois
variantes non qualifiees et non activees. Un defaut technique du rappel long
a ete corrige : lots de sources entieres, budget mesure avec schema et rejet
conservateur des associations invalides. 448 tests logiciels locaux passent.
Le rappel du scenario fictif auparavant bloquant a reussi avec le vrai modele.
[Mesures et limites](../technique/dialogue-et-rappel.md).

Prochaine etape : verifier stockage, recherche et lecture apres redemarrage,
avec des profils fictifs. Criteres proposes : 36 rappels exacts sur 40 cas
reserves, aucun fait personnel invente, aucune fuite prive/public, corrections
et oublis respectes. Aucun changement de backend ni de modele prevu.
Ces mesures restent a effectuer ; elles ne sont pas acquises par la publication.

Cette copie est documentaire : les rapports bruts et les ressources privees
sont exclus. [Code et provenance](../../laboratoire/README.md).

## Migration technique locale du 5 novembre

Journaux, caches, sorties et rapports regroupes sous data dans l installation
privee ; anciens chemins conserves par jonctions Windows, sans double copie.
Controle commun des chemins audio adapte : 349 tests logiciels laboratoire
et 18 tests originaux passent apres migration. Profil Sopro original a 2 etapes
conserve. Aucun essai micro ou son en direct pendant cette migration.
Ces controles ne changent pas le bilan de jugement conversationnel ci-dessus.

Apres migration, le proprietaire a effectue un essai et confirme le fonctionnement.
Ce retour utilisateur complete les tests logiciels, sans garantir tous les usages.

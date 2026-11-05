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

## Memoire retenue ; suite : initiative de parole bornee

Le proprietaire accepte la memoire actuelle comme base viable, avec ses limites,
et demande de poursuivre. Le modele, la voix et le backend sont conserves.
Le jugement conversationnel reste reporte. Les retours d'usage permettront
d'ameliorer la memoire ; elle n'est pas declaree parfaite ni qualifiee globalement.

Corrections actives : budget final avec schema reel, sources entieres,
priorite au meilleur temoin de recherche puis au reclassement, identite et
tutoiement du lecteur factuel sans ajout d'intentions absentes des sources.
20 rappels acceptables, dont 17 sans reserve. Lot fictif reserve de 16 cas :
14 corrects, 2 partiels, 0 incorrect ; ton conforme 16/16 contre 3/16 avant.
485 tests logiciels locaux reussis. Le critere propose de 36/40 n'a pas ete
mesure. [Resultats, conditions et limites](../technique/rappel-memoire.md).

Suite retenue : initiative de parole bornee, a concevoir puis verifier avec
silence, interruption et arret humain respectes. Aucune parole spontanee
n'est activee par cette publication ; la vision reste un objectif futur.

Cette copie est documentaire : rapports bruts, conversations et ressources
privees exclus. Les 485 tests locaux ne sont pas integralement reproductibles
depuis cette selection. [Code et provenance](../../laboratoire/README.md).

## Migration technique locale du 5 novembre

Journaux, caches, sorties et rapports regroupes sous data dans l installation
privee ; anciens chemins conserves par jonctions Windows, sans double copie.
Controle commun des chemins audio adapte : 349 tests logiciels laboratoire
et 18 tests originaux passent apres migration. Profil Sopro original a 2 etapes
conserve. Aucun essai micro ou son en direct pendant cette migration.
Ces controles ne changent pas le bilan de jugement conversationnel ci-dessus.

Apres migration, le proprietaire a effectue un essai et confirme le fonctionnement.
Ce retour utilisateur complete les tests logiciels, sans garantir tous les usages.

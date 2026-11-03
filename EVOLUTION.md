# De la V3 à la direction actuelle

État présenté le 3 novembre 2026. Alice est un projet de compagnon vocal local
sur Windows, en français, avec une personnalité affirmée. L'objectif reste une
conversation vivante, avec des souvenirs utiles et des actions encadrées.

## Ce qui a évolué

La sélection V3 montre surtout les fondations techniques : voix, lecture audio,
gestion des processus, GPU et fenêtres. Elle n'est pas assez complète pour
affirmer qu'une fonction absente de ces extraits n'existait pas dans la V3.
Le tableau compare donc ce qui est présenté ici, sans inventer un bilan exhaustif.

| Sujet | Extraits V3 publiés | Direction du laboratoire actuel |
| --- | --- | --- |
| Voix et écoute | Service vocal et lecture progressive Windows | Copies indépendantes de la voix et de l'écoute raccordées au dialogue |
| Conversation | Fondations techniques et tests d'interface | Dialogue local, personnalité, bibliothèque locale et pensées silencieuses bornées |
| Souvenirs | Stockage privé exclu de la publication | Mémoire épisodique, sources conservées, corrections et oubli confirmé ; compréhension encore imparfaite |
| Twitch / Discord | Pas de démonstration complète dans cette sélection | Dialogue externe séparé du local, sans accès aux outils ni aux souvenirs privés |
| OBS | Pas d'intégration démontrée par ces extraits | Sous-titres raccordés ; rendu réel et essai en stream encore à vérifier |
| Priorité de recherche | Difficultés techniques décrites dans PIEGES.md | Lire fidèlement les échanges avant d'en tirer des souvenirs ou des conclusions |

## Trois états à distinguer

1. **V3 historique** : les dix fichiers déjà publiés restent à leur emplacement.
2. **Laboratoire utilisable pour essais** : une installation indépendante fondée
   sur GPT-oss, avec voix, écoute, mémoire et raccordements conversationnels.
   Elle ne remplace pas complètement l'installation originale et n'est pas
   déclarée stable dans son ensemble.
3. **Recherche mémoire en cours** : des lecteurs expérimentaux mesurent la
   compréhension des faits, corrections, dates, incertitudes et interactions.
   Les nouveaux candidats ne sont pas installés dans Alice active.

## La nouvelle priorité, simplement

Si une personne dit « je me suis trompé, c'était 40 et non 60 », Alice doit
comprendre une correction, sans inventer un changement réel de 60 vers 40.
Une ancienne permission rapportée dans un souvenir ne doit pas devenir une
autorisation actuelle d'agir. Ces exemples sont fictifs et illustrent le but ;
ils ne sont pas présentés comme de nouveaux tests réussis.

Le travail actuel cherche à conserver les sources entières, puis à distinguer
les faits, les incertitudes et les intentions dans leur contexte. Un JSON valide
ne prouve pas que le modèle a compris. La priorité est cette fidélité de lecture,
avant une nouvelle qualification du dialogue. Personnalité, répétitions et
nouveaux ajouts publics ne sont pas le chantier de cette étape.

La vision, l'avatar et une conversation collective Discord ne sont pas raccordés
dans ce laboratoire. Les essais complets micro/voix/stream restent nécessaires.

Voir [l'état actuel et les limites mesurées](version_actuelle/README.md).

## Retrouver le fonctionnement de la mémoire V5

La [documentation dédiée à la mémoire V5](memoire_v5/README.md) décrit le
stockage SQLite de l’installation originale, les citations sources, l’extraction
et le rappel lexical, avec trois modules de code. Elle précise les limites de
la reconstitution historique et la différence avec le laboratoire actuel.

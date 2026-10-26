# Investigation du démarrage de DAS 1.0.0 sur Steam Deck

26 octobre 2026 — PR #1, branche `fix/steam-deck-cold-start-rpc-race`.

La course au démarrage est reproduite dans les octets du ZIP 1.0.0 publié : les quatre appels `state`, `jsaux_refresh`, `jsaux_recover` et `update_status` peuvent lever `AttributeError: 'Plugin' object has no attribute 'updater'`. Le déplacement de l’initialisation proposé par la PR corrige cette course. Deux défauts frontend associés sont également corrigés : une erreur transitoire persistait après une réponse réussie, et une ancienne réponse en erreur pouvait contaminer un état plus récent.

Cela démontre des défauts logiciels et leurs corrections. Sans le traceback de l’utilisateur, cela ne prouve pas que son signalement particulier a exactement cette cause. Aucun Steam Deck LCD ou OLED physique n’était disponible. La validation native reste à effectuer avant fusion et publication.

## Sources et périmètre

- Dépôt public : https://github.com/Alyenax/Decky-Animated-Screensaver
- Version publiée : https://github.com/Alyenax/Decky-Animated-Screensaver/releases/tag/v1.0.0
- PR examinée : https://github.com/Alyenax/Decky-Animated-Screensaver/pull/1
- Base publique : `7bc67d7947e31d2b931cf346d48ed21480290b5f`.
- Tête initiale de la PR : `ba866e12c528830ecfaac91c5ef8505890d02684`.
- Dépôt privé : inventaire de ses branches et comparaison du point de publication Lab69 `f709045677fccb196333efe7d0f85bbb131e117a` avec l’entrée publique. Le `main` privé est plus ancien et ne représente pas la version publique actuelle. Ce contrôle ne constitue pas un nouvel audit intégral de toutes les branches privées.
- Decky Loader stable consulté : v3.3.0, publié le 18 octobre 2026, commit `3e81176da2c8b5f267a157b32e5e4b9fe3ab0b2d` ; source `main` également examinée au commit `00cd202872b85868071b041c8f1b34e734147195`.
- Exécution locale sous Linux x86_64, UID 0 ; Python 3.10.22, 3.12.14 et 3.14.8 ; Node 24.22.1. Aucun workflow GitHub Actions lancé pour les validations. Aucun changement des workflows.

## Archive effectivement publiée

L’asset téléchargé est `Decky-Animated-Screensaver-v1.0.0.zip`, et non l’archive GitHub générée automatiquement pour les sources.

| Contrôle | Résultat |
|---|---|
| Taille | 424 264 octets |
| SHA-256 | `e25096b1079966da7be67421a729646cea65742e8a7f23d8625614fbfc63cb73` |
| Empreinte déclarée par GitHub | Identique |
| Intégrité ZIP | Correcte |
| Entrées | 132, dont 131 fichiers couverts par le manifeste |
| Vérification du manifeste | Chaque empreinte correspond aux octets archivés ; aucun fichier supplémentaire hors manifeste, à part le manifeste lui-même |
| Structure | Un dossier `Decky-Animated-Screensaver/`, sans doublon ni traversée de chemin |
| Fichiers essentiels | `plugin.json`, `package.json`, `main.py`, `dist/index.js`, `py_modules/das`, player et licences présents |
| Identité | Nom affiché `Animated Screensaver`, API 1, flag `root`, version 1.0.0 |
| Modules Python | 46 fichiers sous `py_modules`, plus entrée et script de packaging ; aucune dépendance tierce Python obligatoire trouvée |
| Imports réels | `main.py` et 45 sous-modules DAS importés avec le module `decky` officiel sous les trois versions de Python |
| Source de l’entrée | `main.py` de l’asset identique à celui du tag v1.0.0 |

Les fichiers sont archivés en 0644, sauf le manifeste en 0600. Le backend root peut les lire ; les fichiers Python et JavaScript n’ont pas besoin d’un bit exécutable. L’extraction locale n’est pas une preuve d’installation réussie par le vrai Decky sur le matériel.

## Distinguer les étapes du problème

| Étape | Observation et conclusion |
|---|---|
| Installation du plugin par Decky | La structure et les métadonnées correspondent au parcours d’installation ZIP du Loader consulté. Aucun fichier essentiel manquant trouvé. Les opérations réelles de Decky, la place disponible et les permissions de la machine de l’utilisateur restent à vérifier. |
| Import Python | Les imports du package publié réussissent avec `decky` officiel sous Python 3.10, 3.12 et 3.14. Aucun import de `signalbar`, aucun pilote série, aucun module GCA requis pour charger DAS. |
| Exécution de `_main()` | La création du stockage peut échouer, par exemple si les réglages sont inaccessibles. Ce cas est distinct de la course RPC. Une erreur fatale garde désormais son traceback et fournit un code d’état explicite au frontend déjà connecté. |
| Premier RPC | Défaut reproduit : le serveur de requêtes peut exécuter un appel pendant la première attente de découverte, avant la création de `updater`. |
| Ouverture de l’interface | Le QAM utilise `jsaux_refresh`, tandis que l’amorçage appelle aussi `state`, `jsaux_recover` et `update_status`. Une requête en erreur pouvait laisser le texte d’erreur après récupération. |
| Préparation et lecture | Aucun besoin de GCA pour l’export TV/écran. Les tests logiciels couvrent l’export et la conservation des réglages. Le téléchargement des outils, la conversion réelle et la lecture dans Steam doivent encore être acceptés sur Deck. |

## Problèmes et corrections

Les lignes « publié » désignent le ZIP original ; les lignes « corrigé » désignent la branche de la PR.

| Problème | Fichier et ligne | Cause et reproduction | Correction | Résultat |
|---|---|---|---|---|
| Course sur `updater` | Publié : `main.py:51`, `main.py:59`, `main.py:119` ; corrigé : `main.py:64` | Suspendre `_main()` sur `installer.status(True)`, puis appeler séparément les quatre RPC. `service` existe déjà, donc l’ancien garde admet les appels ; `updater` n’existe pas encore. | Construire `Updater`, ou le fallback `UnavailableUpdater`, avant la première suspension. Son ordonnanceur ne démarre toujours qu’après la découverte. | Même test : quatre erreurs dans le ZIP publié ; aucune sur la PR et dans le ZIP candidat. |
| Test initial de la PR défectueux en exécution isolée | `tests/backend/test_plugin.py:18`, test à `:54` | Le patch temporaire de `sys.modules` peut retirer les modules chargés dans le setup. L’import tardif de `BrokerError` crée alors une autre classe ; le manager ne capture pas l’exception injectée. | Charger `BrokerError` avant le patch de modules ; ajouter `jsaux_recover`. Ajouter un test indépendant avec un endpoint réellement absent. | Test initial en erreur `BROKER_UNAVAILABLE` avant correction du test ; test corrigé réussi. Ce résultat ne signale pas une dépendance réelle à GCA. |
| Erreur transitoire conservée | Publié : `src/StudioRuntime.tsx:15` ; corrigé : `:13`, `:17` | Le hook reçoit une erreur « Python Exception », puis une réponse correcte. Le succès remplaçait l’état sans effacer l’erreur. | Identifier les erreurs provenant des lectures et les effacer au succès suivant. Conserver les erreurs d’actions qui nécessitent une intervention. | Test comportemental du hook React : échec sur le code du ZIP, réussite après correction. |
| Ancien échec de lecture écrasant un état récent | Publié : `src/StudioRuntime.tsx:16` ; corrigé : `:18` | Lancer une lecture lente, réussir une lecture plus récente, puis rejeter l’ancienne. Le `catch` ne vérifiait pas son numéro de séquence. | Appliquer le garde de séquence également aux rejets. | Le test vérifie que l’état récent reste sain et sans erreur. |
| RPC avant démarrage ou sur initialisation partielle | Publié : `main.py:126` ; corrigé : `main.py:138` | Avant `_main()`, l’ancien garde lève une exception. Si `service` est créé mais l’initialisation échoue ensuite, ce garde est insuffisant. | Réponse existante `das-action-error-v1` avec `backend_starting` ou `backend_stopping` ; ne pas exposer des dépendances partielles. Aucune relance automatique des mutations. | Tests avant `_main()` et avec un objet partiellement initialisé réussis. |
| Échec fatal des réglages insuffisamment distingué | Corrigé : `main.py:32`, `src/i18n.ts:17` | Injecter `PermissionError` dans la récupération des réglages. Une telle erreur ne doit pas devenir un état « démarrage » sans fin. | Conserver l’exception originale dans le journal ; exposer `backend_storage` ou `backend_start_failed`. Ajouter les messages FR/EN. | Test : traceback préservé, réponse classée, aucun chemin privé exposé. Le stockage inaccessible nécessite toujours une intervention réelle. |

Le premier correctif de la PR était pertinent, mais sa vérification annoncée n’avait pas été exécutée. Il ne traitait pas les erreurs persistantes du frontend et son test ne couvrait pas `jsaux_recover`.

## Decky Loader, chemins et permissions

Dans `backend/decky_loader/plugin/sandboxed_plugin.py:72`, Decky sélectionne l’identité root pour ce flag, exporte `HOME` séparément de `DECKY_USER_HOME`, puis ajoute le `py_modules` du plugin à `sys.path` à la ligne 91. Le serveur RPC et `_main()` sont planifiés séparément aux lignes 130 et 133 : le serveur n’attend pas la fin de `_main()`.

Le parcours d’installation consulte un `plugin.json` au premier niveau de l’archive (`browser.py:233`). Le nom affiché et le nom du dossier sont traités séparément. Le fait que le dossier soit `Decky-Animated-Screensaver` et l’étiquette `Animated Screensaver` ne démontre donc pas une erreur de packaging. Le module `src/runtime_identity.ts` existant et ses tests sont conservés.

DAS utilise `DECKY_PLUGIN_SETTINGS_DIR/library` pour son catalogue, et `_steam_home()` (`py_modules/das/library.py:16`) cherche notamment `.steam/steam`, `.steam/root` et `.local/share/Steam` dans le home de l’utilisateur Steam. Le test utilise `HOME` pointant vers un faux home root et `DECKY_USER_HOME` pointant vers le home utilisateur, avec le lien Steam habituel. Le chemin obtenu est celui de cet utilisateur, pas `/root/.local/share/Steam`.

Les réglages restent sous le dossier d’installation historique de Decky ; le changement de nom affiché ne les déplace pas. Les exports écrivent dans `Steam/config/uioverrides/screensavers/decky-animated-screensaver`, avec dossiers 0755 et fichiers lisibles 0644 (`py_modules/das/studio/installer.py:239`). La version root reste nécessaire à l’identité du client JSAUX optionnel ; la retirer sans revoir l’authentification du broker constituerait une régression.

Les outils vidéo ne sont pas embarqués dans le petit ZIP : `Resources` gère leur téléchargement explicite, leur empreinte et leur exécution séparée. Leur absence n’empêche pas l’import ni l’affichage de l’état initial. Le système Python externe utilisé par le superviseur de conversions est distinct du Python embarqué dans Decky. Aucun `pip install` de GCA, de pilote USB ou de bibliothèque Python n’est nécessaire au démarrage.

## Scénarios sans GCA et sans Faceplate

| Scénario | Couverture et résultat |
|---|---|
| Installation vierge, GCA absent | Endpoint broker réellement absent ; quatre RPC testés pendant le premier await, puis après initialisation : réussite. |
| Service JSAUX indisponible ou refusé | `BROKER_UNAVAILABLE`, `AUTH_DENIED`, `VERSION_UNSUPPORTED` simulés dans le client réel : état JSAUX indisponible, état TV utilisable. |
| Ancien réglage JSAUX activé, GCA retiré | Redémarrage, réglages conservés octet pour octet, durée de scène conservée, export TV possible sans désactiver la préférence enregistrée. |
| Ancien export publié via GCA | Ancienne publication broker simulée, mais fichiers Steam et marqueur installés réellement par DAS. Après retrait de GCA : quatre RPC réussis, fichiers et catalogue inchangés ; reconstruction explicite TV seule réussie. |
| Stockage de l’updater inaccessible | Fallback existant testé ; écran seul utilisable, erreur limitée à l’updater. |
| Réglages inaccessibles | Erreur fatale classée, traceback préservé ; aucune fausse annonce de fonctionnement normal. |
| Arrêt et rechargement | Les tests ciblés ferment les workers et recréent le plugin avec les mêmes réglages. |

Aucune modification de `py_modules/das/jsaux`, des assets du player, du manifeste ou des règles d’usure flash. Les budgets, déduplications, contrôles d’accès, conditions de transfert, limites de puissance, verrouillages et temporisations existants sont conservés. Aucun envoi matériel supplémentaire ajouté.

## Résultats des validations locales

| Validation | Résultat |
|---|---|
| Reproduction sur le ZIP publié | 1 test, 4 sous-cas en erreur `AttributeError` |
| Test initial de la PR corrigé | Réussi, y compris `jsaux_recover` |
| Ensemble ciblé plugin et démarrage | 42 tests réussis sous Python 3.12 |
| Nouveaux scénarios de démarrage | 8/8 sous Python 3.10, 3.12 et 3.14 |
| Tests du plugin sous Python 3.10 et 3.14 | 41 tests réussis dans chaque exécution, avant le dernier scénario ancien export ; ce dernier est ensuite inclus dans les 8/8 multi-version |
| Tests frontend existants et nouveaux | 93 réussis |
| Hook React de production | 3 assertions comportementales réussies : récupération, rejet tardif ignoré, erreur d’action conservée |
| Player, debug, calendrier, calibration, continuité | 46 tests, 42 réussis, 4 ignorés faute de prérequis externes |
| Suites E2E optionnelles | 17 ignorés : environnement GCA/FFmpeg de test explicitement requis |
| Suite backend exhaustive | 512 exécutés lors de l’essai complet : 473 réussis, 18 ignorés, 17 erreurs et 4 échecs liés aux capacités de cet hôte ; dernier scénario ajouté ensuite et réussi |
| Sous-ensemble compatible avec cet hôte | 492 tests : 474 réussis, 18 ignorés ; exclusion explicite des 21 tests bloqués ci-dessus, sans modification de leur code |
| TypeScript | `tsc --noEmit` réussi |
| Frontend de production | Compilation Rollup réussie ; `node --check dist/index.js` réussi |
| Python | Compilation syntaxique et imports réels réussis |
| Package candidat | 131 empreintes internes vérifiées, ZIP intègre, SHA-256 vérifié |
| Diff et périmètre | `git diff --check` réussi ; aucun diff des modules JSAUX, assets ou `plugin.json` |

La suite exhaustive n’est donc pas entièrement verte dans cet environnement. Seize tests nécessitant la création d’un socket Unix rencontrent `PermissionError: [Errno 1] Operation not permitted`. Cinq autres tests dépendent de la surveillance du processus propriétaire : le superviseur observe le PID propriétaire original comme absent et déclenche sa protection `cinema_parent_lost`. Une reproduction instrumentée temporaire, hors production, confirme cette observation. Ces protections n’ont pas été retirées pour faire passer les tests. La liste exacte figure dans `host-blocked-tests.json` dans les pièces jointes.

Les tests navigateur supplémentaires ont également été tentés : cinq échecs faute des prérequis navigateur/outils configurés. Chromium est absent et son téléchargement a retourné une archive invalide. Ils ne constituent pas une validation graphique. Le test de récupération du frontend exécute le vrai hook React avec `react-test-renderer`, des adaptateurs explicites et sans session SteamOS. Les suites E2E ignorées ne sont pas comptabilisées comme réussies.

Le premier essai de la suite backend rencontrait aussi l’absence de `/private/tmp`, chemin attendu par des fixtures héritées de macOS. Le dossier a été créé localement ; aucun changement produit n’a été nécessaire. Le lanceur `tsx` essayait de créer un socket IPC interdit ; la même suite frontend a donc été exécutée par `node --import tsx --test`, sans ce lanceur. Ces adaptations sont propres à l’hôte de test.

## Reproduction des validations essentielles

Depuis la racine du dépôt, avec les dépendances du lockfile installées :

```bash
PYTHONPATH=py_modules:tests/backend python3 -m unittest test_cold_start test_plugin -v
PYTHONPATH=py_modules python3 -m unittest discover -s tests/backend -v
node --import tsx --test tests/frontend/*.test.ts
npm run typecheck
npm run build
npm run package
(cd out && sha256sum -c SHA256SUMS)
```

Pour démontrer l’échec avant correction avec les octets de l’asset publié :

```bash
DAS_AUDIT_PLUGIN_ROOT=/chemin/zip-extrait/Decky-Animated-Screensaver \
PYTHONPATH=/chemin/zip-extrait/Decky-Animated-Screensaver/py_modules:tests/backend \
python3 -m unittest test_cold_start.ColdStartTests.test_all_four_early_rpcs_without_gca -v
```

Le test doit produire quatre erreurs d’attribut sur `updater`. Avec le package candidat extrait au même endroit, le même test réussit. Aucune source du ZIP publié n’est retouchée.

Pour le test comportemental frontend, installer temporairement React et son renderer de même version, puis définir `DAS_UI_DEPS` sur leur dossier `node_modules` :

```bash
npm install --prefix /tmp/das-hook-deps react@19.1.1 react-test-renderer@19.1.1
DAS_UI_DEPS=/tmp/das-hook-deps/node_modules node scripts/test_startup_recovery.mjs
```

Ajouter `DAS_AUDIT_SOURCE_ROOT=/chemin/zip-extrait/Decky-Animated-Screensaver` à la dernière commande pour tester les sources frontend publiées : l’assertion exigeant l’effacement de l’erreur doit échouer. Les dépendances du renderer sont des outils de test externes et ne sont pas ajoutées au package distribué.

## Package candidat et validation physique restante

Le candidat est compilé localement, sans release. Il conserve provisoirement la version interne 1.0.0 ; son empreinte le distingue du ZIP public :

`f17c43ce014888186952ddbe2165f4eca111a0303e3caafed471046efc42b656`

Taille : 425 315 octets. Il ne faut pas le confondre avec l’asset public existant. Le bundle de preuves contient une copie explicitement nommée comme candidat PR1 non publié.

Sur chacun des deux modèles LCD et OLED, avec GCA absent et aucune Faceplate :

1. Relever la version exacte de SteamOS, de Decky et le canal du client Steam ; conserver les réglages avant l’essai.
2. Installer le candidat depuis ZIP avec le vrai Decky ; ouvrir immédiatement le QAM, fermer et rouvrir, puis recharger le backend.
3. Vérifier que le chargement ne laisse pas une « Python Exception » persistante, que les réglages restent accessibles et que le journal ne comporte pas d’erreur d’import ni d’attribut `updater` manquant.
4. Configurer SteamGridDB, télécharger les outils vidéo, ajouter des jeux, vérifier les aperçus, préparer et installer la collection en cadrage 16:10.
5. Sélectionner l’écran de veille dans Steam ; vérifier animation, entrée, sortie, reprise après veille et redémarrage de la console.
6. Rejouer avec des réglages et un export issus d’une ancienne installation où GCA était présent, puis avec son service arrêté ; vérifier l’intégrité des choix utilisateur.
7. Comparer le vrai traceback du signalement initial avec les signatures reproduites. Un `ModuleNotFoundError`, un refus d’accès ou un échec d’installation doit être traité séparément si rencontré.

Les défauts logiciels démontrés sont corrigés sur la branche de la PR. La compatibilité complète LCD/OLED, le focus manette, le téléchargement réseau natif, la conversion et la lecture Steam ne peuvent pas être certifiés par ces seuls tests locaux. Aucune fusion et aucune release ne sont autorisées par ce rapport.

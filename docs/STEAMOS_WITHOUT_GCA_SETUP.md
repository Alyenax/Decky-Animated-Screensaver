# Corrections complémentaires pour SteamOS sans GCA ni Faceplate

26 octobre 2026 — complément à l’investigation initiale de la PR #1. Base avant ces corrections : `afbef64b97347c22c256b6283260a99011387877`.

Des défauts supplémentaires sont démontrés, indépendamment de la course au démarrage déjà corrigée. Ils concernent les erreurs de setup et une ancienne installation où la sortie JSAUX avait été préparée. Aucun traceback de l’utilisateur Reddit n’est encore disponible : ces reproductions ne prouvent pas la cause de son cas particulier.

## Défauts certains et corrections

| Défaut | Localisation après correction | Reproduction | Comportement corrigé |
|---|---|---|---|
| Clé manquante ou rejetée transformée en exception générique | `main.py:31`, `main.py:153`, `main.py:438` | Sans clé, appeler `validate_key`, `search`, `add` ou `candidates`. Avec une clé enregistrée, simuler le refus API `unauthorized`. Avant : `ValueError` traversant Decky. | Les erreurs de setup passent dans l’enveloppe existante `das-action-error-v1`. Le frontend affiche le code traduit et une action vers les réglages. Cela couvre aussi les contrôles hors du verrou principal comme `resume`. |
| Saisie de clé invalide renvoyée comme exception Python | `main.py:364`, `src/i18n.ts:68` | Enregistrer une chaîne contenant des espaces, trop courte, ou une valeur non textuelle. | Réponse `steamgriddb_invalid_key`, traduite FR/EN ; ancienne clé et collection conservées, aucune valeur sensible renvoyée. La suppression volontaire par chaîne vide reste possible. |
| FFprobe manquant détecté après une tentative de lancer les décodeurs | `py_modules/das/studio/service.py:402` | Déclarer FFmpeg disponible mais FFprobe absent ; le test refuse tout appel au décodeur. | `ffprobe_missing` avant lancement de décodeur ou worker. Sans FFmpeg : `ffmpeg_missing`. Le parcours collection conserve une erreur récupérable dans son état et n’installe rien. |
| Ancien GIF prêt pouvant réintroduire une sortie JSAUX absente | `py_modules/das/studio/installer.py:177`, `:214` | Préparer et installer une vraie miniature de collection JSAUX dans la fixture ; retirer ensuite GCA ou la Faceplate, en gardant volontairement l’ancienne détection positive. L’ancienne installation tente encore une publication JSAUX. | L’installation explicite rafraîchit la présence avant ses contrôles. Si la sortie est absente ou incompatible, le nouvel export contient uniquement l’écran principal : aucune publication ni démarrage du relais JSAUX. Le GIF préparé, les options, le mode et les préférences restent sauvegardés. |

Le contrôle d’absence est limité à l’installation d’un nouvel export. Les descripteurs JSAUX existants restent lisibles et la lecture d’un ancien export peut toujours reprendre après redémarrage lorsque GCA est disponible. Les tests de lots, de synchronisation et de restauration ont été exécutés pour vérifier ces comportements.

Il reste possible d’ajouter des jeux avant le setup complet. Le bouton normal de préparation conserve sa redirection vers le setup si la clé ou les outils manquent. Installer une collection déjà préparée reste possible sans clé et sans outils vidéo : aucun prérequis artificiel n’a été ajouté à cette installation.

Les protections flash, les budgets, la déduplication, les limites de puissance, les règles d’authentification et les assets du player n’ont pas été modifiés. Le rafraîchissement ajouté est une lecture de présence lors d’une installation explicitement demandée, pas une nouvelle boucle périodique ni un transfert matériel.

## Tests et preuve avant après

Les huit nouveaux tests de `tests/backend/test_setup_without_gca.py` exécutent les chemins réels de DAS avec un stockage temporaire, un broker de fixture et des réponses API simulées. Ils ne supposent aucune installation de GCA et n’ouvrent aucun périphérique USB.

Sur la base précédente `afbef64`, les mêmes tests produisent trois échecs et onze erreurs répartis sur leurs sous-cas. Avec les corrections, les huit tests réussissent. Un test vérifie expressément que le retrait du matériel est découvert par `install()` lui-même, même si la dernière détection mémorisée était positive.

Validations effectuées localement, sans GitHub Actions :

- 50 tests ciblés plugin, démarrage et setup réussis sous Python 3.12.
- Passage backend compatible avec cet hôte : 500 tests, dont 482 réussis et 18 ignorés ; aucun échec.
- 91 tests d’intégration sélectionnés autour du plugin, des lots et de la lecture JSAUX : 90 réussis, un ignoré faute de prérequis explicite.
- 16 scénarios setup et démarrage réussis sous Python 3.10.22 et sous Python 3.14.8.
- 94 tests frontend réussis, dont vérification des messages et des actions de récupération sans conseil inutile concernant GCA/JSAUX.
- Trois vérifications du hook React de récupération réussies.
- TypeScript, compilation Rollup, syntaxe JavaScript et contrôles du package réussis.
- Package extrait : 16 tests setup/démarrage réussis avec ses modules Python réels.

La liste de 21 tests dépendant de sockets Unix ou de l’observation du PID propriétaire, bloqués par l’hôte et détaillés dans le rapport initial, reste exclue du passage compatible. Les tests ignorés ne constituent pas des validations réussies. L’acceptation physique Steam Deck LCD/OLED et la vérification du traceback utilisateur restent nécessaires.

Pour rejouer les tests ciblés :

```bash
PYTHONPATH=py_modules:tests/backend python3 -m unittest test_setup_without_gca test_plugin test_cold_start -v
node --import tsx --test tests/frontend/*.test.ts
npm run typecheck
npm run build
npm run package
(cd out && sha256sum -c SHA256SUMS)
```

Pour la preuve avant correction, extraire `git archive afbef64` dans un dossier temporaire puis placer son `py_modules` avant `tests/backend` dans `PYTHONPATH`, et définir `DAS_AUDIT_PLUGIN_ROOT` sur ce dossier. Exécuter le nouveau module `test_setup_without_gca` depuis le dépôt courant : aucun fichier de la base n’est retouché.

Le nouveau ZIP local conserve provisoirement la version interne 1.0.0 ; il n’est pas publié : 425 896 octets, SHA-256 `77655e668a0c032838e197efefc5f094017cca131f630420cf7aaa1985aa80e5`. Il remplace le candidat précédent pour la validation logicielle de cette branche, sans remplacer l’asset public.

Aucune fusion ni release. Toutes les corrections restent sur la branche de la PR #1.

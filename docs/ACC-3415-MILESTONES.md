# ACC-3415 — R6 : marqueurs de progression

## Placement et chemin réellement ciblé

Vérification **statique**, pas exécution Android : le manifeste du shell désigne
`org.yuzu.yuzu_emu.ui.main.MainActivity` comme entrée MAIN. Son `onCreate`, après
`super.onCreate`, émet `APP_OPEN` avec le tag `lasrecomp`. Le launcher autonome
`SharedLauncherActivity` reçoit le même marqueur, sans marqueur de frame.
Une recréation d'activité peut donc répéter APP_OPEN ; ce n'est pas une preuve de
chargement du runtime ni de démarrage d'un jeu.

`engine/tools/build_shared_android.py` archive la source LAS épinglée puis copie
les overlays `engine/ports/shared-android/runtime` dans le runtime préparé.
`engine/ports/shared-android/CMakeLists.txt` construit `libmain.so` avec ces sources
et la plateforme Android héritée. On instrumente les overlays effectifs, pas une
copie de travail générée ni les probes natifs synthétiques. Le shell possède aussi
`RaitchiLaunchActivity`, qui appelle `RaitchiShellBridge` pour préparer la session.
Aucune construction ni préparation de workspace de build n'a été lancée ici.

- `runtime/gamelib.c`, `reserve_window` : `MEM_RESERVE_FAIL(%llu)` si
  `plat_reserve_guest` retourne faux ; `MEM_RESERVE_OK(%llu)` après retour vrai.
  La taille est `window.hi - window.lo`, en octets, non la mémoire physique engagée.
  Ce point commun couvre les préparations AOT et native. La plateforme Android est
  héritée et n'existe pas comme overlay local : les deux échecs internes de mmap
  sont observés par le retour faux, sans copier ni modifier la source héritée.
- `runtime/nvn/vulkan/device.c` : les **deux** appels à `vkCreateDevice` émettent
  `VK_DEVICE_FAIL(%s)` avant le `VK_CHECK` existant ou `VK_DEVICE_OK(%s)` après.
  Le résultat d'échec est conservé dans le log et la politique d'erreur reste
  inchangée. Comme dans le sibling letsgo, `%s` est `g_vk.props.deviceName` :
  identité du périphérique du pilote sélectionné, **pas** chemin de bibliothèque,
  version complète de pilote ni preuve d'un pilote personnalisé.
- Même fichier, `present_hooks` : `GAME_FIRST_FRAME` lorsque `total_frames == 1`,
  après remise du premier present invité au renderer direct ou à `rq_present`.
  Ce hook n'est pas le rafraîchissement du launcher ni celui du menu seul.

## Limites de preuve

GAME_FIRST_FRAME signifie **premier present invité remis au renderer**, comme le
compteur de presents du runtime ; ce n'est pas un accusé de réception de l'écran.
En mode asynchrone, le rendu peut encore être en file. En mode direct, une surface
indisponible ou une texture non exploitable peut empêcher l'affichage. Le marqueur
ne prouve ni pixels visibles, ni gameplay, ni progression, ni vitesse correcte.
Une image du launcher ne permet jamais de déclarer « jeu démarré ».
Le compteur est celui du processus existant, sans ajout de réinitialisation.
Les erreurs avant `vkCreateDevice` (instance, sélection GPU, fonctionnalités
manquantes), les crashs et les arrêts avant retour de réservation ne sont pas
transformés en VK_DEVICE_FAIL ou MEM_RESERVE_FAIL par cette instrumentation minimale.

## Cohérence avec letsgo et validation

Lecture de `../acc3415-letsgo/tests/test_milestone_markers.py` et du diff des trois
sites d'instrumentation : mêmes noms, parenthèses, octets et deviceName. Adaptations
NativeNX : réservation dans le wrapper commun réellement présent, deux chemins de
création Vulkan, present_hooks partagé entre rendu direct et file asynchrone.

Commande depuis la racine NativeNX :

```sh
python3 -m unittest discover -s tests -p test_milestone_markers.py -v
```

Avant instrumentation : `Ran 5 tests`, `FAILED (failures=5)` (le sous-test APP_OPEN
vérifie deux activités). Après instrumentation : `Ran 5 tests`, `OK`, sortie 0.
Tests statiques synthétiques seulement : placement, taille, deux créations Vulkan,
unicité du marqueur invité et copie des overlays. `git diff --check` : sortie 0.
Aucun appareil, jeu, clé, réseau, build Android ou test de pixels utilisé.
Les manifests de sources et la CI ne sont pas modifiés par R6 ; leur actualisation
reste à la charge du responsable, conformément à la consigne.

# Jev joue à Zork

Jev, le modèle System One de [TypeSafe](https://typesafe.ai), joue à Zork I. À
chaque tour, [Jericho](https://github.com/microsoft/jericho) fournit les actions
valides et Jev répond à un seul Choice : quelle commande taper. On voit sa
confiance, et le moment où il hésite entre « open mailbox » et « north ».

Trois pièces :

- **`jev-zork`**, le harnais : il fait jouer Jev et affiche ses barres de
  confiance dans le terminal. Chaque tour est noté dans un journal JSONL.
- **`replay/index.html`**, le lecteur : il rejoue un journal avec la carte des
  lieux découverts, la courbe de confiance et les intentions, tour par tour.
- **`video/render_video.py`**, la vidéo : il filme le lecteur image par image
  et produit un MP4 (et un GIF) prêt pour LinkedIn.

## Comment ça marche

```
Jericho ──► actions valides ──┐
                              ├─► state + 3 questions ──► Jev ──► probabilités, confiance
mémoire (8 derniers tours) ───┘                                          │
                                                                         ▼
Zork ◄── commande jouée ◄── anti-boucle (le code garde la main) ◄── distribution
```

- **Jev ne fait que juger.** Chaque tour pose trois questions dans une seule
  requête :
  - un **Choice** sur les actions valides : les options sont les clés de
    `criteria`, au plus 255 ;
  - un **Noul** « danger » ;
  - un **Choice** « intention » (explorer, ramasser, fouiller, résoudre,
    combattre, fuir).

  Les deux derniers ne servent qu'à la visualisation.
- **La mémoire et l'anti-boucle sont dans le code.** Les 8 derniers tours
  partent dans le state. Une action déjà tentée dans le même état du monde voit
  sa probabilité divisée par deux à chaque essai : sans cela, n'importe quel
  agent tourne en rond dans la forêt. Quand le code s'écarte de l'avis de Jev,
  le terminal, le journal et le replay le disent.
- **Les options parlent d'elles-mêmes.** Une sortie déjà empruntée porte sa
  destination (« leads to North of House (visited 2 times) »). La doc de Jev
  déconseille de le faire chercher ailleurs dans le state.
- **Le state est en anglais, l'affichage en français.** Jev lit mieux l'anglais.
  Dans le noir, il ne sait pas où il est, parce que le jeu ne le dit pas.

## Installation (Windows + WSL)

Jericho ne tourne que sous Linux ou macOS. Sous Windows, tout passe par WSL
(Ubuntu), sans `sudo` : `uv` s'installe dans `~/.local/bin` et apporte son
propre Python 3.12.

```bat
jouer installer
```

Le script `scripts/setup_wsl.sh` fait tout :

- il installe `uv` si besoin ;
- il crée l'environnement Python dans `~/.venvs/jev-zork` (Jericho, SDK
  TypeSafe, spaCy et son modèle) ;
- il télécharge `roms/zork1.z5` depuis la suite de jeux de Jericho, en
  vérifiant son empreinte MD5 ;
- il lance les tests.

Sous Linux ou macOS : `scripts/setup_wsl.sh`, puis `scripts/play.sh` à la place
de `jouer`.

La ROM n'est pas versionnée. Il faut `gcc` et `make`, car Jericho se compile.
Sous Ubuntu : `sudo apt install build-essential`.

## La clé TypeSafe

Copiez `.env.example` en `.env` et collez-y votre clé
(<https://console.typesafe.ai/keys>) :

```
TYPESAFE_API_KEY=…
```

`.env` n'est jamais versionné, pas plus que ses variantes (`.env.*`, hors
`.env.example`). Sans clé, `jev-zork` s'arrête et le dit.

Sous Windows, le Bloc-notes ajoute volontiers `.txt` à un nom sans extension :
le fichier devient `.env.txt` et n'est pas lu. `jev-zork` le détecte et dit de
le renommer.

`jev-zork` ne lit dans `.env` que `TYPESAFE_API_KEY`, et la variable
d'environnement du shell, si elle existe, l'emporte. Un `.env` glissé dans un
dossier cloné ne peut donc pas rediriger l'API (`TYPESAFE_BASE_URL`) pour
détourner votre vraie clé.

## Jouer

```bat
jouer --mock --steps 20          :: sans clé : tirage au hasard, ce n'est PAS Jev
jouer --delay 0.6 --steps 150    :: Jev, avec une pause pour pouvoir lire
```

| Option | Rôle | Défaut |
|---|---|---|
| `--steps` | coups au plus | 150 |
| `--delay` | pause entre deux coups, en secondes | 0 |
| `--mock` | tirage au hasard au lieu de Jev, pour tester sans clé | non |
| `--model` | modèle TypeSafe | `jev-latest` |
| `--seed` | graine de Jericho (et du tirage `--mock`) | 12, celle du walkthrough |
| `--history` | tours envoyés à Jev dans le state | 8 |
| `--penalty` | facteur appliqué par essai déjà fait (anti-boucle) | 0.5 |
| `--floor` | probabilité plancher avant l'anti-boucle | 0.01 |
| `--budget-usd` | arrête la partie au-delà de ce coût | 0.25 |
| `--top` | options affichées par coup | 6 |
| `--quiet` | n'affiche que le début et la fin | non |

Le mode `--mock` est annoncé partout : dans le terminal, dans le journal et
dans la vidéo. Il ne remplace jamais une partie de Jev.

**N'attendez pas un gros score.** Zork I se joue sur 350 points, et Jev ne
planifie rien : il juge chaque coup sur ce qu'il voit. Sur la partie de
référence (voir « Mesures réelles »), il a marqué 44 points en 150 coups, sans
mourir, mais il a mis 116 coups à entrer dans la maison. C'est justement ce
qu'il y a de bon à regarder avec les barres de confiance.

## Le journal

Chaque partie écrit `runs/AAAAMMJJ-HHMMSS-<jev|mock>.jsonl` :

- une ligne d'en-tête (`run`) : modèle, graine, réglages, prix ;
- une ligne par tour (`turn`) : ce que Jev a vu (`observation`, `state`), les
  options et leurs notes, ses `probabilities`, sa `confidence`, son `choice`,
  la distribution corrigée par l'anti-boucle (`adjusted`, `tries`), l'`action`
  jouée, `danger`, `intent`, la réponse du jeu, la latence, les tokens, le coût
  et le `request_id` ;
- une ligne de fin (`end`) : la raison de l'arrêt, le score et le coût total.

Le fichier est écrit ligne à ligne : une partie interrompue garde ses tours.

## Le replay

Ouvrez `replay/index.html` d'un double-clic et déposez-y un journal. Il ne faut
pas de serveur.

- Espace : lecture ou pause. Flèches : tour précédent ou suivant.
- Survolez les courbes pour lire les valeurs, cliquez pour sauter à un tour.
- « Tableau » : toute la partie en tableau, tour par tour.

Avec un serveur local, un journal s'ouvre aussi par l'adresse :
`python -m http.server 8841`, puis
<http://127.0.0.1:8841/replay/index.html?log=../runs/….jsonl>.

## La vidéo

Sous Windows, avec `uv`, Chrome (ou Edge) et `ffmpeg`. La vidéo de la partie de
référence (voir « Mesures réelles ») :

```bat
uv run video/render_video.py runs\20260921-101451-jev.jsonl --from 110 --to 138 --speed 1.2 --format carre
```

Le script ouvre le lecteur dans un Chrome sans interface. Il le pose à chaque
instant et passe chaque image à ffmpeg : aucune image n'est sautée, quelle que
soit la vitesse du poste. Un coup sûr passe vite, une hésitation s'attarde.

| Option | Rôle |
|---|---|
| `--from`, `--to` | l'extrait montré, en numéros de tour du journal. Pour LinkedIn, 25 à 30 coups font environ 1 min 30 |
| `--format` | `paysage` (1920×1080), `carre` (1080×1080) ou `vertical` (1080×1350) |
| `--speed` | rythme du replay : 1.5 va une fois et demie plus vite |
| `--gif` | ajoute un GIF allégé (720 px, 12 images/s) |
| `--bare` | sans carton d'ouverture ni de fin : pour un GIF court qui boucle |
| `--snapshot T` | n'enregistre qu'une image PNG à l'instant T, pour vérifier le rendu |
| `--snapshot-turn N` | comme `--snapshot`, sur le tour N du journal une fois la décision posée : une image de couverture |

Les fichiers arrivent dans `video/out/`, qui n'est pas versionné. Durées
mesurées : les 29 coups de 110 à 138, à la vitesse 1,2, font 88 s de vidéo ; le
rendu prend environ 3 min 15 s en carré et 4 min 20 s en paysage. Un teaser de 15 s
(`--from 133 --to 138 --bare --gif`) prend 28 s.

Choisissez l'extrait dans le journal : les coups où Jev hésite (`confidence`
sous 0,5), où l'anti-boucle le corrige (`overridden`) ou où le score bouge
(`reward`) font les meilleures images. La vidéo dit toujours d'où vient
l'extrait (« coups 110 à 138 sur 150 »).

Autre voie, plus brute : enregistrer le terminal avec `asciinema` et le
convertir en GIF avec `agg`.

## Coût

Jev 1.13 coûte 0,042 $ par million de tokens d'entrée, et la sortie est
gratuite (<https://docs.typesafe.ai/models>). Mesuré sur la vraie API : 1 186
tokens d'entrée par coup en moyenne (753 au premier coup, 1 607 au plus), donc
**0,0075 $ pour une partie de 150 coups**. Le journal note les tokens réels de
chaque tour. `--budget-usd` arrête la partie si le coût dépasse le budget.

## Mesures réelles

Une partie de référence, le 2026-09-21, contre `jev-1.13.0` (`jev-latest`),
graine 12 (celle de Jericho), 150 coups :

| Mesure | Valeur |
|---|---|
| Durée de la partie, démarrage de WSL et de Jericho compris | 61 s, soit environ 0,4 s par coup |
| Latence de Jev par décision | 262 ms en moyenne, 316 ms au 95e centile, 714 ms au plus |
| Coût | 0,0075 $ pour 177 915 tokens d'entrée |
| Score | 44 sur 350, sans mourir ni changer de graine |
| Confiance | moyenne de 0,37 ; sous 0,5 pour 65 coups sur 150 ; à 0,8 ou plus pour 11 seulement |
| Anti-boucle | 12 corrections du choix de Jev |
| Anomalies | aucune réponse refusée, aucun avertissement, aucune action de repli |

Le journal est dans `runs/` (non versionné). Les 44 points se sont joués entre
les coups 116 et 150 : entrée dans la maison par la fenêtre (+10), trappe du
salon vers la cave (+25), tableau de la galerie (+4), sortie est de la salle du
troll (+5). Le mode `--delay` ne sert qu'à regarder la partie en direct : la
vidéo règle son propre rythme à partir du journal, il ne faut donc pas l'utiliser
pour la préparer.

## Tests

```bat
wsl -d Ubuntu --cd . --exec bash -lc "~/.venvs/jev-zork/bin/python -m pytest --cov"
node --test "replay/tests/*.test.js"
```

- **Python** : les modules purs, le juge Jev à travers le vrai SDK contre un
  faux serveur HTTP, et de vrais coups de Zork sous Jericho.
- **JavaScript** : la logique du replay (journal, rythme, carte, intentions).

## Limites connues

- Jericho propose les actions qui **changent l'état du monde** : il ne propose
  ni `look`, ni `inventory`, ni les mots magiques. S'il ne trouve rien, le
  harnais propose des commandes de base et le note dans le journal
  (`fallback_actions`).
- La carte place un lieu selon la direction prise pour y entrer. La géographie
  de Zork n'est pas euclidienne : la forêt et le labyrinthe donnent des liens
  qui se croisent.
- Le Noul « danger » et le Choice « intention » ne pilotent rien. Ce sont des
  lectures de la situation, pour la visualisation.

## Licence

Le code de ce dépôt est sous licence MIT (voir `LICENSE`).

- **Jericho est sous GPL-2.0 ou ultérieure.** Le projet l'utilise sans le
  contenir : chacun l'installe de son côté avec `scripts/setup_wsl.sh`. Une
  distribution qui embarquerait les deux ensemble (image Docker, exécutable)
  devrait respecter la GPL pour l'ensemble.
- Les autres dépendances sont sous MIT ou BSD : SDK TypeSafe, rich,
  python-dotenv, spaCy et son modèle.
- **Zork I** est une œuvre d'Infocom, aujourd'hui propriété d'Activision. Son
  code source est publié sous licence MIT dans le dépôt `historicalsource/zork1`.
  Ce dépôt-ci ne contient pas la ROM : `scripts/setup_wsl.sh` la télécharge
  depuis la suite de jeux de Jericho, en vérifiant son empreinte MD5.
- Le lecteur de replay charge les polices IBM Plex (licence SIL OFL) depuis
  Google Fonts : ouvrir `replay/index.html` envoie donc une requête à Google.
- Projet indépendant, non affilié à TypeSafe ni à Activision. « Jev » est le
  nom du modèle de TypeSafe.

## Sécurité

La clé TypeSafe ne vit que dans `.env`, qui n'est jamais versionné (ses
variantes `.env.*` non plus). Les journaux de parties, la ROM et les vidéos ne
le sont pas davantage. Pour signaler une vulnérabilité, voir `SECURITY.md`.

## Organisation

```
src/jev_zork/      le harnais : game (Jericho), questions (state et questions),
                   judges (Jev et mock), policy (anti-boucle), memory, journal,
                   display (terminal), runner (boucle de jeu), cli
tests/             tests Python (pytest)
replay/            lecteur de replay : index.html, replay.css, replay-core.js
                   (logique pure, testée), replay-ui.js (affichage)
video/             render_video.py (Playwright + ffmpeg)
scripts/           setup_wsl.sh, play.sh
jouer.cmd          lanceur Windows vers WSL
LICENSE            licence MIT
SECURITY.md        politique de sécurité
```

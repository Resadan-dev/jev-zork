# Politique de sécurité

## Signaler une vulnérabilité

Merci de ne pas ouvrir de ticket public. Utilisez le bouton « Report a
vulnerability » de l'onglet **Security** du dépôt : le signalement reste privé
entre vous et le mainteneur. Décrivez ce que vous avez observé, comment le
reproduire et l'impact que vous imaginez.

*English: please report vulnerabilities privately with the "Report a
vulnerability" button in the Security tab, not through a public issue.*

Le projet est maintenu par une seule personne : la réponse peut prendre
quelques jours.

## Ce qui est concerné

- le harnais `jev-zork` (`src/jev_zork/`), le lecteur de replay (`replay/`) et
  le script de rendu vidéo (`video/render_video.py`) ;
- les scripts d'installation (`scripts/`, `jouer.cmd`).

## Secrets

- La clé TypeSafe se met dans `.env`, jamais dans le code, un ticket ou une
  capture d'écran. `.env` et ses variantes (`.env.*`, hors `.env.example`) sont
  ignorés par git.
- `jev-zork` ne lit que `TYPESAFE_API_KEY` dans `.env`, et la variable
  d'environnement du shell, si elle existe, l'emporte. Un `.env` piégé ne peut
  donc pas rediriger l'API vers un autre serveur.
- Les journaux (`runs/*.jsonl`) contiennent le texte de la partie, les
  identifiants de requête et les tokens, jamais la clé. Ils ne sont pas
  versionnés.
- Si vous trouvez une clé dans l'historique du dépôt, dans un ticket ou dans un
  journal, signalez-le en privé comme ci-dessus, et régénérez-la sur
  console.typesafe.ai/keys.

## Versions prises en charge

Seule la dernière version de la branche `main` reçoit des correctifs.

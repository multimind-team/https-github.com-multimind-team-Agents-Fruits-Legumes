# Vidéo des échanges entre agents

`scenario-agents.json` contient les dialogues, les explications et les rôles représentés.
`generer-interactions.py` produit le MP4, l'affiche, les sous-titres et les repères de chapitres
dans `../assets/video-agents/`. Il utilise Python avec Pillow, FFmpeg et `edge-tts` (7.2.8 lors
de la vérification). La narration utilise `fr-FR-VivienneMultilingualNeural`, à vitesse normale.
Le service vocal Microsoft reçoit uniquement le texte de narration ; aucun courriel, fichier
métier ou secret du projet n'est transmis. Une connexion Internet est nécessaire pour produire
une nouvelle narration ; lire la vidéo produite fonctionne ensuite hors ligne.
Les fichiers temporaires restent dans `scratch/video-agents/`.

La vidéo explique le fonctionnement prévu ; elle ne montre pas des échanges enregistrés
pendant une opération réelle. Les sous-titres sont intégrés à l'image. Le fichier VTT séparé
reprend les repères de phrases fournis par le moteur vocal. Le cache distingue voix, vitesse
et texte : une narration modifiée ne reprend pas une ancienne bande-son.

Après modification du scénario, régénérer la vidéo. Le script actualise aussi les chapitres
et la transcription de `../video-interactions-agents.html`. L'option `--scene 11` permet de
refaire cette seule scène si les autres segments existent et sont inchangés.
Vérifier l'image, le son et la lecture.
Cette génération n'utilise aucun serveur ni aucune donnée métier.

La comparaison des scènes avec les consignes est conservée dans
[correspondance-consignes.md](correspondance-consignes.md), avec les empreintes des sources
relues dans `verification-consignes.json`. Une modification ultérieure de ces sources impose
une nouvelle revue documentaire, même si la vidéo fonctionne toujours.

Références du moteur vocal : [edge-tts](https://github.com/rany2/edge-tts) et
[voix françaises Microsoft](https://learn.microsoft.com/fr-fr/azure/ai-services/speech-service/language-support).

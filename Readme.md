# ⬡ Interface de Contrôle CNC — Projet #3

Interface de contrôle CNC accessible depuis un navigateur, tournant sur un **Raspberry Pi 5** et communiquant avec un **contrôleur de mouvement FPGA** via une interface de commande abstraite.

---

## Stack technique

| Couche | Technologie |
|---|---|
| Plateforme | Raspberry Pi 5 (Wi-Fi, port 8080) |
| Backend | Python 3.11 — FastAPI + Uvicorn |
| Frontend | HTML / CSS / JavaScript vanilla |
| Prévisualisation 3D | Three.js r128 (WebGL) |
| Contrôle mouvement | FPGA (interface SPI/UART abstraite) |

---

## Fonctionnalités

- **Jog manuel** — maintenir un bouton d'axe pour déplacer en continu (X, Y, Z, A)
- **Axes configurables** — basculer entre 2 / 3 / 4 axes en temps réel ; le backend applique la configuration active
- **Chargement G-code & éditeur** — charger un fichier ou saisir du code directement ; les deux affichent un aperçu 3D du parcours outil
- **Lecture animée** — exécuter le G-code avec contrôle de vitesse (0.1× → 10×), mise en pause et arrêt
- **Visualiseur 3D** — déplacements rapides en vert, déplacements en avance en rouge, trace de jog en orange ; orbite / pan / zoom
- **Rotation axe A** — l'indicateur outil tourne visiblement dans la vue 3D lorsque A se déplace
- **Mise à jour firmware FPGA** — charger des fichiers `.bit` / `.mcs` et déclencher le flash depuis l'interface
- **Mise à jour logicielle du Pi** — charger une archive de mise à jour depuis l'interface

---

## Structure du projet

```
cnc-control/
  main.py            ← Serveur FastAPI — API, WebSocket, parseur G-code, interface FPGA
  static/
    index.html       ← Frontend complet (fichier unique)
  uploads/           ← Créé automatiquement au premier lancement
  test_4axis.gcode   ← Programme de test couvrant les 4 axes
```

---

## Démarrage rapide

```bash
# 1. Installer les dépendances
pip install fastapi uvicorn python-multipart

# 2. Lancer le serveur
python main.py

# 3. Ouvrir dans le navigateur
http://<adresse-ip-raspberry>:8080
```

---

## API

| Méthode | Endpoint | Description |
|---|---|---|
| GET | `/api/config/axes` | Récupérer le nombre d'axes actifs et la liste |
| POST | `/api/config/axes` | Définir le nombre d'axes `{"count": 2\|3\|4}` |
| GET | `/api/position` | Position actuelle (axes actifs uniquement) |
| POST | `/api/jog` | Jog pas à pas `{"axis": "X", "distance": 1.0}` |
| POST | `/api/reset` | Remettre à zéro tous les axes actifs |
| POST | `/api/upload/gcode` | Charger un fichier G-code |
| POST | `/api/run` | Exécuter le fichier chargé `{"filename": "piece.gcode"}` |
| POST | `/api/upload/firmware` | Charger un bitfile FPGA (`.bit` / `.mcs`) |
| WS | `/ws` | Synchronisation temps réel position + configuration |

---

## Interface FPGA

Toute communication matérielle est isolée dans `FPGAController` dans `main.py`. L'implémentation actuelle simule le mouvement en logiciel. Pour connecter le vrai matériel, remplacer le corps de `send_command()` par votre appel SPI / UART — le reste du système ne change pas.

```python
def send_command(self, command: dict):
    # command = {"type": "jog", "axis": "X", "distance": 1.0}
    # command = {"type": "linear_move", "target": {...}, "feedrate": 500}
    pass  # ← remplacer par l'appel matériel réel
```

> **Note :** Le Raspberry Pi ne garantit pas le temps réel. Le FPGA doit gérer l'exécution du mouvement en temps réel.

---

## Fichier de test

`test_4axis.gcode` couvre : carré XY, paliers Z, rotation complète de l'axe A (0°→360°), mouvement 4 axes simultané, et un zigzag avec rotation. Le charger via l'onglet Upload pour vérifier tous les axes.

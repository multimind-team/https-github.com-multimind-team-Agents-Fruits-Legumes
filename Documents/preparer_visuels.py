import os
import subprocess

edge = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
doc_dir = r'C:\Users\user\Desktop\projets_IA\projets\preparation-commande\Documents'
img_dir = os.path.join(doc_dir, 'images')
os.makedirs(img_dir, exist_ok=True)

# Detail modal mock in standard mobile phone dimension
detail_html = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<style>
  body {
    background: #15050a;
    color: #fafafa;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    padding: 16px;
    margin: 0;
    box-sizing: border-box;
    width: 412px;
    height: 892px;
  }
  .entete {
    border-bottom: 2px solid #82072a;
    padding-bottom: 12px;
    margin-bottom: 14px;
  }
  .retour {
    font-size: 13px;
    color: #b9a99b;
    margin-bottom: 8px;
    font-weight: 500;
  }
  h2 {
    font-size: 21px;
    margin: 0 0 6px 0;
    color: #ffffff;
    font-family: "Georgia", serif;
  }
  .sous {
    font-size: 12px;
    color: #b9a99b;
  }
  .badge {
    background: #82072a;
    color: #ffffff;
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: bold;
    margin-left: 6px;
  }
  .panneau {
    background: rgba(81, 18, 39, 0.45);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 12px;
    padding: 12px 14px;
    margin-bottom: 12px;
  }
  .titre-panneau {
    font-weight: 700;
    font-size: 13.5px;
    color: #e2d3bf;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .ligne {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 7px 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    font-size: 13px;
  }
  .ligne:last-child {
    border-bottom: none;
  }
  .label {
    color: #d9dfd2;
  }
  .valeur {
    font-weight: 600;
    color: #ffffff;
  }
  .valeur.accent {
    color: #8ec08c;
    font-weight: 700;
    font-size: 15px;
  }
  .resultat-final {
    background: rgba(0, 103, 79, 0.25);
    border: 1px solid #00674f;
    border-radius: 10px;
    padding: 12px 14px;
    margin-top: 10px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .resultat-final .texte {
    font-weight: 700;
    color: #8ec08c;
    font-size: 13.5px;
  }
  .resultat-final .chiffre {
    font-size: 20px;
    font-weight: 800;
    color: #ffffff;
    font-family: "Georgia", serif;
  }
</style>
</head>
<body>
  <div class="entete">
    <div class="retour">← RETOUR À LA LISTE</div>
    <h2>AVOCAT AFFINÉ PIÈCE</h2>
    <div class="sous">Code : 0000087008124 · Fournisseur principal <span class="badge">Colis 18 pièces</span></div>
  </div>

  <div class="panneau">
    <div class="titre-panneau">📦 1. Ce qui est déjà en réserve</div>
    <div class="ligne">
      <span class="label">Comptage physique en chambre froide</span>
      <span class="valeur">6 colis (108 pièces)</span>
    </div>
    <div class="ligne">
      <span class="label">Ventes moyennes observées (saison)</span>
      <span class="valeur">145 pièces / jour</span>
    </div>
    <div class="ligne">
      <span class="label">Taux de perte moyen historique</span>
      <span class="valeur">2,8 %</span>
    </div>
  </div>

  <div class="panneau">
    <div class="titre-panneau">🧮 2. Le calcul de la commande</div>
    <div class="ligne">
      <span class="label">Besoin prévisionnel pour demain</span>
      <span class="valeur">162 pièces</span>
    </div>
    <div class="ligne">
      <span class="label">Marge de sécurité casse (+2,8 %)</span>
      <span class="valeur">+5 pièces</span>
    </div>
    <div class="ligne">
      <span class="label">Déduction du stock déjà au frais</span>
      <span class="valeur">-108 pièces</span>
    </div>
    <div class="resultat-final">
      <span class="texte">Proposition finale :</span>
      <span class="chiffre">9 colis</span>
    </div>
  </div>

  <div class="panneau">
    <div class="titre-panneau">💶 3. Impact financier & marge</div>
    <div class="ligne">
      <span class="label">Prix d'achat unitaire</span>
      <span class="valeur">0,68 € / pièce</span>
    </div>
    <div class="ligne">
      <span class="label">Prix de vente public</span>
      <span class="valeur">1,29 € / pièce</span>
    </div>
    <div class="ligne">
      <span class="label">Taux de marge brute prévu</span>
      <span class="valeur accent">47,9 %</span>
    </div>
  </div>
</body>
</html>
"""

detail_html_path = os.path.join(img_dir, 'detail_temp.html')
with open(detail_html_path, 'w', encoding='utf-8') as f:
    f.write(detail_html)

detail_png_path = os.path.join(img_dir, 'ecran_detail.png')
cmd = [
    edge, '--headless=new', '--disable-gpu',
    '--window-size=412,892',
    f'--screenshot={detail_png_path}',
    f'file:///{detail_html_path.replace(os.sep, "/")}'
]
subprocess.run(cmd, check=True)
print("ecran_detail.png updated successfully.")

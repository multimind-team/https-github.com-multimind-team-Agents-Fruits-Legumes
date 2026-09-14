import os

doc_dir = r'C:\Users\user\Desktop\projets_IA\projets\preparation-commande\Documents'
img_dir = os.path.join(doc_dir, 'images')
os.makedirs(img_dir, exist_ok=True)

# 1. Schéma de la Position (Aéré et équilibré)
svg_position = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 820 330" width="100%" height="100%">
  <defs>
    <linearGradient id="gradPos" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#00674f" />
      <stop offset="100%" stop-color="#004d3b" />
    </linearGradient>
    <linearGradient id="gradNeg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#82072a" />
      <stop offset="100%" stop-color="#511227" />
    </linearGradient>
    <filter id="shadow" x="-3%" y="-3%" width="106%" height="110%">
      <feDropShadow dx="0" dy="3" stdDeviation="4" flood-opacity="0.07" />
    </filter>
  </defs>

  <rect width="820" height="330" rx="14" fill="#fdfbf7" stroke="#e2d3bf" stroke-width="1.5"/>

  <text x="30" y="36" font-family="'Proza Libre', Georgia, serif" font-size="18" font-weight="bold" fill="#511227">Comprendre la « Position » : la vraie mesure du besoin en rayon</text>
  <text x="30" y="56" font-family="'Red Hat Text', Arial, sans-serif" font-size="12" fill="#595959">Ce n'est pas un stock abstrait : on remplit le rayon d'abord, puis on compte ce qui reste au frais ou ce qui manque.</text>

  <!-- Carte 1 : Position Positive -->
  <g transform="translate(30, 75)" filter="url(#shadow)">
    <rect width="365" height="235" rx="10" fill="#ffffff" stroke="#e2d3bf" stroke-width="1"/>
    <rect width="365" height="38" rx="10" fill="#f5f1ec"/>
    <rect y="26" width="365" height="12" fill="#f5f1ec"/>
    <text x="16" y="24" font-family="'Proza Libre', Georgia, serif" font-size="13" font-weight="bold" fill="#00674f">CAS N°1 : RÉSERVE NON VIDE</text>
    
    <rect x="250" y="7" width="102" height="24" rx="12" fill="url(#gradPos)"/>
    <text x="301" y="23" font-family="Arial, sans-serif" font-size="11.5" font-weight="bold" fill="#ffffff" text-anchor="middle">Position = +2</text>

    <g transform="translate(16, 52)">
      <rect x="0" y="0" width="150" height="82" rx="8" fill="#e8f5e9" stroke="#00674f" stroke-width="1.5"/>
      <text x="75" y="26" font-family="Arial, sans-serif" font-size="11" font-weight="bold" fill="#00674f" text-anchor="middle">RAYON DU MAGASIN</text>
      <text x="75" y="48" font-family="Arial, sans-serif" font-size="13" font-weight="bold" fill="#262626" text-anchor="middle">Plein à 100 %</text>
      <text x="75" y="66" font-family="Arial, sans-serif" font-size="10" fill="#595959" text-anchor="middle">(présentation impeccable)</text>

      <text x="166" y="46" font-family="Arial, sans-serif" font-size="18" font-weight="bold" fill="#595959">+</text>

      <rect x="182" y="0" width="150" height="82" rx="8" fill="#fcfbfa" stroke="#c8b39f" stroke-width="1.5"/>
      <text x="257" y="26" font-family="Arial, sans-serif" font-size="11" font-weight="bold" fill="#82072a" text-anchor="middle">CHAMBRE FROIDE</text>
      <text x="257" y="48" font-family="Arial, sans-serif" font-size="13" font-weight="bold" fill="#00674f" text-anchor="middle">2 colis au frais</text>
      <text x="257" y="66" font-family="Arial, sans-serif" font-size="10" fill="#595959" text-anchor="middle">(marchandise d'avance)</text>
    </g>

    <rect x="14" y="148" width="337" height="72" rx="8" fill="#f6f3ef"/>
    <text x="24" y="170" font-family="Arial, sans-serif" font-size="11.5" fill="#262626"><tspan font-weight="bold" fill="#00674f">Exemple :</tspan> Concombres. Rayon garni, 2 colis au frais.</text>
    <text x="24" y="190" font-family="Arial, sans-serif" font-size="11" fill="#404040">→ L'outil déduit ces 2 colis du besoin prévisionnel.</text>
    <text x="24" y="206" font-family="Arial, sans-serif" font-size="11" fill="#595959">On ne commande que le complément pour demain.</text>
  </g>

  <!-- Carte 2 : Position Négative -->
  <g transform="translate(425, 75)" filter="url(#shadow)">
    <rect width="365" height="235" rx="10" fill="#ffffff" stroke="#e2d3bf" stroke-width="1"/>
    <rect width="365" height="38" rx="10" fill="#f5f1ec"/>
    <rect y="26" width="365" height="12" fill="#f5f1ec"/>
    <text x="16" y="24" font-family="'Proza Libre', Georgia, serif" font-size="13" font-weight="bold" fill="#82072a">CAS N°2 : RÉSERVE VIDE</text>
    
    <rect x="250" y="7" width="102" height="24" rx="12" fill="url(#gradNeg)"/>
    <text x="301" y="23" font-family="Arial, sans-serif" font-size="11.5" font-weight="bold" fill="#ffffff" text-anchor="middle">Position = −3</text>

    <g transform="translate(16, 52)">
      <rect x="0" y="0" width="150" height="82" rx="8" fill="#fff5f5" stroke="#82072a" stroke-width="1.5" stroke-dasharray="4 3"/>
      <text x="75" y="26" font-family="Arial, sans-serif" font-size="11" font-weight="bold" fill="#82072a" text-anchor="middle">RAYON DU MAGASIN</text>
      <text x="75" y="48" font-family="Arial, sans-serif" font-size="13" font-weight="bold" fill="#ff2822" text-anchor="middle">Manque 3 colis</text>
      <text x="75" y="66" font-family="Arial, sans-serif" font-size="10" fill="#595959" text-anchor="middle">(pour remplir l'étal)</text>

      <text x="166" y="46" font-family="Arial, sans-serif" font-size="18" font-weight="bold" fill="#595959">+</text>

      <rect x="182" y="0" width="150" height="82" rx="8" fill="#fcfbfa" stroke="#c8b39f" stroke-width="1.5"/>
      <text x="257" y="26" font-family="Arial, sans-serif" font-size="11" font-weight="bold" fill="#595959" text-anchor="middle">CHAMBRE FROIDE</text>
      <text x="257" y="48" font-family="Arial, sans-serif" font-size="13" font-weight="bold" fill="#82072a" text-anchor="middle">Réserve vide (0)</text>
      <text x="257" y="66" font-family="Arial, sans-serif" font-size="10" fill="#595959" text-anchor="middle">(plus aucun carton)</text>
    </g>

    <rect x="14" y="148" width="337" height="72" rx="8" fill="#f6f3ef"/>
    <text x="24" y="170" font-family="Arial, sans-serif" font-size="11.5" fill="#262626"><tspan font-weight="bold" fill="#82072a">Exemple :</tspan> Tomates grappes. Réserve vide, 3 cartons manquants.</text>
    <text x="24" y="190" font-family="Arial, sans-serif" font-size="11" fill="#404040">→ L'outil comprend qu'il faut combler le trou en rayon.</text>
    <text x="24" y="206" font-family="Arial, sans-serif" font-size="11" fill="#595959">La commande est augmentée automatiquement de 3 colis.</text>
  </g>
</svg>"""

with open(os.path.join(img_dir, 'schema_position.svg'), 'w', encoding='utf-8') as f:
    f.write(svg_position)

# 2. Schéma du Calcul (Textes parfaitement calés)
svg_calcul = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 820 280" width="100%" height="100%">
  <defs>
    <filter id="shadow2" x="-4%" y="-4%" width="108%" height="112%">
      <feDropShadow dx="0" dy="3" stdDeviation="4" flood-opacity="0.08" />
    </filter>
  </defs>

  <rect width="820" height="280" rx="14" fill="#ffffff" stroke="#e2d3bf" stroke-width="1.5"/>

  <text x="30" y="34" font-family="'Proza Libre', Georgia, serif" font-size="18" font-weight="bold" fill="#511227">La formule quotidienne : comment la juste quantité est calculée</text>
  <text x="30" y="52" font-family="'Red Hat Text', Arial, sans-serif" font-size="12" fill="#595959">Chaque nuit, l'outil analyse les 600 articles du rayon pour anticiper le besoin de livraison de demain.</text>

  <!-- Bloc 1 : Historique -->
  <g transform="translate(25, 70)" filter="url(#shadow2)">
    <rect width="168" height="190" rx="10" fill="#f5f1ec" stroke="#c8b39f" stroke-width="1"/>
    <rect width="168" height="34" rx="10" fill="#511227"/>
    <rect y="24" width="168" height="10" fill="#511227"/>
    <text x="84" y="22" font-family="Arial, sans-serif" font-size="12" font-weight="bold" fill="#ffffff" text-anchor="middle">1. VENTES RÉELLES</text>
    
    <text x="84" y="65" font-family="Georgia, serif" font-size="22" font-weight="bold" fill="#511227" text-anchor="middle">Moyenne</text>
    <text x="84" y="85" font-family="Arial, sans-serif" font-size="11" font-weight="bold" fill="#82072a" text-anchor="middle">sur ± 21 jours</text>
    
    <text x="14" y="114" font-family="Arial, sans-serif" font-size="10.5" fill="#333333">Ventes observées sur la</text>
    <text x="14" y="130" font-family="Arial, sans-serif" font-size="10.5" fill="#333333">même saison (historique).</text>
    <text x="14" y="154" font-family="Arial, sans-serif" font-size="10" fill="#595959">Zéro commande si hors</text>
    <text x="14" y="168" font-family="Arial, sans-serif" font-size="10" fill="#595959">saison (ex: clémentines en été).</text>
  </g>

  <!-- Opérateur × -->
  <text x="208" y="170" font-family="Georgia, serif" font-size="26" font-weight="bold" fill="#82072a" text-anchor="middle">×</text>

  <!-- Bloc 2 : Facteurs -->
  <g transform="translate(222, 70)" filter="url(#shadow2)">
    <rect width="168" height="190" rx="10" fill="#f5f1ec" stroke="#c8b39f" stroke-width="1"/>
    <rect width="168" height="34" rx="10" fill="#82072a"/>
    <rect y="24" width="168" height="10" fill="#82072a"/>
    <text x="84" y="22" font-family="Arial, sans-serif" font-size="12" font-weight="bold" fill="#ffffff" text-anchor="middle">2. FACTEURS CLÉS</text>
    
    <text x="14" y="60" font-family="Arial, sans-serif" font-size="11" font-weight="bold" fill="#262626">☀️ Météo d'été</text>
    <text x="24" y="75" font-family="Arial, sans-serif" font-size="10" fill="#595959">Chaleur (+7%) / Pluie (-10%)</text>

    <text x="14" y="98" font-family="Arial, sans-serif" font-size="11" font-weight="bold" fill="#262626">🎒 Vacances &amp; Fêtes</text>
    <text x="24" y="113" font-family="Arial, sans-serif" font-size="10" fill="#595959">Noël (+16%), Ponts, etc.</text>

    <text x="14" y="136" font-family="Arial, sans-serif" font-size="11" font-weight="bold" fill="#262626">📅 Profil du jour</text>
    <text x="24" y="151" font-family="Arial, sans-serif" font-size="10" fill="#595959">Samedi fort vs mardi calme</text>

    <text x="14" y="173" font-family="Arial, sans-serif" font-size="10.5" font-weight="bold" fill="#00674f">🛡️ Couverture casse 3%</text>
  </g>

  <!-- Opérateur − -->
  <text x="405" y="170" font-family="Georgia, serif" font-size="30" font-weight="bold" fill="#82072a" text-anchor="middle">−</text>

  <!-- Bloc 3 : Position en réserve -->
  <g transform="translate(420, 70)" filter="url(#shadow2)">
    <rect width="168" height="190" rx="10" fill="#f5f1ec" stroke="#c8b39f" stroke-width="1"/>
    <rect width="168" height="34" rx="10" fill="#511227"/>
    <rect y="24" width="168" height="10" fill="#511227"/>
    <text x="84" y="22" font-family="Arial, sans-serif" font-size="12" font-weight="bold" fill="#ffffff" text-anchor="middle">3. MARCHANDISE</text>
    
    <text x="84" y="65" font-family="Georgia, serif" font-size="22" font-weight="bold" fill="#511227" text-anchor="middle">Position</text>
    <text x="84" y="85" font-family="Arial, sans-serif" font-size="11" font-weight="bold" fill="#82072a" text-anchor="middle">en réserve</text>
    
    <text x="14" y="114" font-family="Arial, sans-serif" font-size="10.5" fill="#333333">La marchandise déjà au</text>
    <text x="14" y="130" font-family="Arial, sans-serif" font-size="10.5" fill="#333333">frais est soustraite.</text>
    <text x="14" y="154" font-family="Arial, sans-serif" font-size="10" fill="#595959">Si la réserve est vide,</text>
    <text x="14" y="168" font-family="Arial, sans-serif" font-size="10" fill="#595959">le manque est réintégré.</text>
  </g>

  <!-- Opérateur = -->
  <text x="603" y="170" font-family="Georgia, serif" font-size="30" font-weight="bold" fill="#00674f" text-anchor="middle">=</text>

  <!-- Bloc 4 : Proposition -->
  <g transform="translate(618, 70)" filter="url(#shadow2)">
    <rect width="176" height="190" rx="10" fill="#e8f5e9" stroke="#00674f" stroke-width="2"/>
    <rect width="176" height="34" rx="10" fill="#00674f"/>
    <rect y="24" width="176" height="10" fill="#00674f"/>
    <text x="88" y="22" font-family="Arial, sans-serif" font-size="12" font-weight="bold" fill="#ffffff" text-anchor="middle">PROPOSITION FINALE</text>
    
    <text x="88" y="68" font-family="Georgia, serif" font-size="24" font-weight="bold" fill="#00674f" text-anchor="middle">En Colis</text>
    <text x="88" y="88" font-family="Arial, sans-serif" font-size="11" font-weight="bold" fill="#004d3b" text-anchor="middle">Arrondi au plus juste</text>
    
    <text x="14" y="116" font-family="Arial, sans-serif" font-size="10.5" fill="#262626">Arrondi au colis entier.</text>
    <text x="14" y="144" font-family="Arial, sans-serif" font-size="10" font-weight="bold" fill="#82072a">Garde-fou promo :</text>
    <text x="14" y="160" font-family="Arial, sans-serif" font-size="10" fill="#595959">Bloqué à 0 si précommandé.</text>
  </g>
</svg>"""

with open(os.path.join(img_dir, 'schema_calcul.svg'), 'w', encoding='utf-8') as f:
    f.write(svg_calcul)

print("SVGs perfected.")

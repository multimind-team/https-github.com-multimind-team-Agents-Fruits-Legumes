"""Inventaire et validation syntaxique en lecture seule, sans accès aux secrets."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def principal():
    comptes = Counter()
    erreurs = []
    jsonl = {}
    sources = {}
    exclusions = {'.git', '.venv', '__pycache__', 'node_modules'}
    for fichier in sorted(ROOT.rglob('*')):
        if not fichier.is_file() or any(p in exclusions for p in fichier.parts) or fichier.name.startswith('.env'):
            continue
        relatif = fichier.relative_to(ROOT).as_posix()
        extension = fichier.suffix.lower()
        comptes[extension] += 1
        if extension not in {'.json', '.jsonl', '.py', '.js', '.html', '.md', '.css', '.txt', '.bat', '.vbs'}:
            continue
        texte = fichier.read_text(encoding='utf-8-sig')
        sources[relatif] = hashlib.sha256(fichier.read_bytes()).hexdigest()
        try:
            if extension == '.py':
                ast.parse(texte, filename=relatif)
            elif extension == '.json':
                json.loads(texte, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nombre non fini ' + x)))
            elif extension == '.jsonl':
                lignes = [l for l in texte.splitlines() if l.strip()]
                for ligne in lignes:
                    json.loads(ligne, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nombre non fini ' + x)))
                jsonl[relatif] = len(lignes)
            elif extension in {'.html', '.js'}:
                morceaux = re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', texte, flags=re.S | re.I) if extension == '.html' else [texte]
                for code in morceaux:
                    if not code.strip():
                        continue
                    resultat = subprocess.run(['node', '--check', '--input-type=commonjs'], input=code, capture_output=True, text=True, encoding='utf8')
                    if resultat.returncode:
                        raise ValueError(resultat.stderr)
        except Exception as exc:
            erreurs.append({'fichier': relatif, 'erreur': str(exc)})
    bilan = {'fichiers_par_extension': dict(comptes), 'jsonl': jsonl,
             'lignes_jsonl': sum(jsonl.values()), 'erreurs': erreurs}
    sortie = Path(tempfile.gettempdir()) / 'preparation-audit'
    sortie.mkdir(exist_ok=True)
    (sortie / 'inventaire.json').write_text(json.dumps(bilan, ensure_ascii=False, indent=2), encoding='utf8')
    (sortie / 'empreintes-sources.json').write_text(json.dumps(sources, indent=2), encoding='utf8')
    print(json.dumps(bilan, ensure_ascii=False, indent=2))
    return bool(erreurs)


if __name__ == '__main__':
    raise SystemExit(principal())

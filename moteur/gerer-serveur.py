"""Gestion prudente du serveur Windows : aucune terminaison par numéro de port."""
import argparse
import logging
import ctypes
from ctypes import wintypes
import ntpath
import json
import os
import subprocess
import sys
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]


def arguments_windows(commande):
    """Décode la vraie ligne Windows, y compris chemins contenant des espaces."""
    if not commande:
        return []
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel.LocalFree.restype = wintypes.HLOCAL
    taille = ctypes.c_int()
    tableau = shell.CommandLineToArgvW(commande, ctypes.byref(taille))
    if not tableau:
        return []
    try:
        return [tableau[index] for index in range(taille.value)]
    finally:
        kernel.LocalFree(tableau)


def processus_du_projet(processus, script, port=None):
    """Refuse les chemins relatifs, -c/-m, simples sous-chaînes et autres ports."""
    executable = processus.get("executable") or ""
    if ntpath.basename(executable).lower() not in {"python.exe", "pythonw.exe"}:
        return False
    args = arguments_windows(processus.get("command_line"))
    if not args or ntpath.basename(args.pop(0)).lower() != ntpath.basename(executable).lower():
        return False
    while args and args[0] in {"-u", "-B"}:
        args.pop(0)
    if not args:
        return False
    chemin = args.pop(0)
    if not ntpath.isabs(chemin):
        return False
    if ntpath.normcase(ntpath.normpath(chemin)) != ntpath.normcase(ntpath.normpath(str(script))):
        return False
    if port is not None:
        return args == [str(port)] or (not args and port == 8751)
    return True


class GestionErreur(RuntimeError):
    """Refus sûr, dont le texte ne contient ni commande brute ni secret."""


def inventaire_windows(port=8751):
    """Inventorie sans action ; toute erreur d'inspection interdit le lancement."""
    if os.name != "nt" or not isinstance(port, int) or not 1 <= port <= 65535:
        raise GestionErreur("Windows et un port valide sont nécessaires.")
    commande = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$connections = @(Get-NetTCPConnection -State Listen -ErrorAction Stop)
$owners = @($connections | Where-Object { $_.LocalPort -eq PORT_CIBLE } |
    Select-Object -ExpandProperty OwningProcess -Unique)
$processes = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
    ForEach-Object { [pscustomobject]@{pid=[int]$_.ProcessId; executable=$_.ExecutablePath;
        command_line=$_.CommandLine; created=[string]$_.CreationDate.ToFileTimeUtc()} })
[pscustomobject]@{listeners=$owners; processes=$processes} | ConvertTo-Json -Depth 4 -Compress
'''.replace("PORT_CIBLE", str(port))
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    try:
        resultat = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-Command", commande],
            capture_output=True, encoding="utf-8", timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=True,
        )
        inventaire = json.loads(resultat.stdout.lstrip("\ufeff"))
        if not isinstance(inventaire["listeners"], list) or not isinstance(inventaire["processes"], list):
            raise ValueError("Inventaire incomplet")
        return inventaire
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as erreur:
        raise GestionErreur("Identification des processus impossible ; aucune action effectuée.") from erreur


def arreter_processus(processus, script, port=None):
    """Arrête un handle vérifié par chemin ET date de création (anti-réemploi PID)."""
    if not processus_du_projet(processus, script, port):
        raise GestionErreur("Arrêt refusé : ce processus n'est pas celui du projet.")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x0001 | 0x1000 | 0x100000, False, int(processus["pid"]))
    if not handle:
        if ctypes.get_last_error() == 87:  # Le processus a déjà disparu.
            return
        raise GestionErreur("Arrêt refusé : impossible de vérifier le processus.")
    try:
        temps = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in temps)):
            raise GestionErreur("Arrêt refusé : identité du processus non vérifiable.")
        creation = (temps[0].dwHighDateTime << 32) | temps[0].dwLowDateTime
        # Win32_Process.CreationDate est précis à la microseconde, FILETIME à 100 ns.
        if creation // 10 != int(processus["created"]) // 10:
            raise GestionErreur("Arrêt refusé : le PID appartient maintenant à un autre processus.")
        if kernel.WaitForSingleObject(handle, 0) == 0:
            return
        if not kernel.TerminateProcess(handle, 0):
            raise GestionErreur("Le processus identifié n'a pas pu être arrêté.")
        if kernel.WaitForSingleObject(handle, 5000) != 0:
            raise GestionErreur("Arrêt non confirmé dans le délai prévu.")
    finally:
        kernel.CloseHandle(handle)


class VerrouOccupe(GestionErreur):
    pass


class VerrouLocal:
    """Verrou OS libéré à la fermeture ou au crash, sans PID périmé à nettoyer."""
    def __init__(self, chemin, attente=0):
        self.chemin = Path(chemin)
        self.attente = attente
        self.fichier = None

    def __enter__(self):
        import msvcrt
        self.fichier = self.chemin.open("a+b")
        try:
            if self.fichier.tell() == 0:
                self.fichier.write(b"0")
                self.fichier.flush()
            self.fichier.seek(0)
            limite = time.monotonic() + self.attente
            while True:
                try:
                    msvcrt.locking(self.fichier.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= limite:
                        raise
                    time.sleep(0.1)
        except OSError as erreur:
            self.fichier.close()
            self.fichier = None
            raise VerrouOccupe("Une autre gestion ou surveillance est déjà active.") from erreur
        return self

    def __exit__(self, *args):
        import msvcrt
        try:
            self.fichier.seek(0)
            msvcrt.locking(self.fichier.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self.fichier.close()
            self.fichier = None


def lancer_script(script, arguments, racine, sortie, erreurs):
    """Même installation Python, console valide et sorties ajoutées sans troncature."""
    executable = Path(sys.executable)
    if executable.name.lower() == "pythonw.exe":
        executable = executable.with_name("python.exe")
    if not executable.is_file() or executable.name.lower() != "python.exe":
        raise GestionErreur("Interpréteur python.exe introuvable ; aucun lancement effectué.")
    with Path(sortie).open("ab") as stdout, Path(erreurs).open("ab") as stderr:
        return subprocess.Popen(
            [str(executable), "-u", str(Path(script).resolve()), *arguments],
            cwd=racine, stdout=stdout, stderr=stderr,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


def application_repond(port=8751):
    """Santé de la page existante ; ni API de santé inventée ni écriture métier."""
    try:
        with urlopen(f"http://127.0.0.1:{port}/app/index.html", timeout=5) as reponse:
            return reponse.status == 200 and reponse.headers.get_content_type() == "text/html"
    except HTTPError as erreur:
        erreur.close()
        return False
    except (URLError, TimeoutError, OSError, HTTPException):
        return False


class GestionServeur:
    def __init__(self, racine=RACINE, port=8751, inventaire=None, termine=None, lance=None, verifie=None):
        self.racine = Path(racine).resolve()
        self.port = port
        self.serveur = self.racine / "moteur" / "serveur.py"
        self.surveillance = self.racine / "moteur" / "surveiller-serveur.py"
        self.pause = self.racine / ".serveur-arrete"
        self.verrou = self.racine / ".gestion-serveur.lock"
        self.inventaire = inventaire or inventaire_windows
        self.termine = termine or arreter_processus
        self.lance = lance or lancer_script
        self.verifie = verifie or application_repond
        self.enfants = []

    def inspecter(self):
        vue = self.inventaire(self.port)
        serveurs = [p for p in vue["processes"] if processus_du_projet(p, self.serveur, self.port)]
        surveillants = [p for p in vue["processes"] if processus_du_projet(p, self.surveillance)]
        propres = {p["pid"] for p in serveurs}
        etrangers = set(vue["listeners"]) - propres
        return vue, serveurs, surveillants, etrangers

    def _arreter_cibles(self, serveurs, surveillants):
        # Persiste même après réouverture de session ; les anciens watchdogs sont
        # arrêtés d'abord car ils ne connaissent pas encore ce marqueur.
        self.pause.write_text("Arrêt demandé. Reprise : demarrer-serveur.bat\n", encoding="utf-8")
        for processus in surveillants:
            self.termine(processus, self.surveillance)
        for processus in serveurs:
            self.termine(processus, self.serveur, self.port)
        _, restants, veilles, _ = self.inspecter()
        if restants or veilles:
            raise GestionErreur("Arrêt incomplet ; maintenance conservée, aucun lancement effectué.")
        for enfant in self.enfants:
            enfant.poll()

    def arreter(self):
        with VerrouLocal(self.verrou, attente=60):
            _, serveurs, surveillants, _ = self.inspecter()
            self._arreter_cibles(serveurs, surveillants)
            return "arrete"

    def demarrer(self, redemarrer=False, automatique=False):
        with VerrouLocal(self.verrou, attente=0 if automatique else 60):
            if automatique and self.pause.exists():
                return "maintenance"
            vue, serveurs, surveillants, etrangers = self.inspecter()
            if etrangers:
                raise GestionErreur(f"Port {self.port} occupé par un autre processus ; aucun arrêt effectué.")
            if serveurs and not redemarrer:
                if len(serveurs) == 1 and vue["listeners"] and self.verifie(self.port):
                    if not automatique:
                        self.pause.unlink(missing_ok=True)
                    return "actif"
                raise GestionErreur("Serveur du projet présent mais indisponible ; utiliser --redemarrer pour un arrêt ciblé.")
            if not self.serveur.is_file():
                raise GestionErreur("Script serveur absent ; aucun arrêt effectué.")
            if redemarrer:
                self._arreter_cibles(serveurs, surveillants)
                _, _, _, etrangers = self.inspecter()
                if etrangers:
                    raise GestionErreur("Port repris par un autre processus ; relance refusée.")
            self.pause.unlink(missing_ok=True)
            enfant = self.lance(self.serveur, [str(self.port)], self.racine,
                                self.racine / "serveur.log", self.racine / "serveur-erreurs.log")
            self.enfants.append(enfant)
            limite = time.monotonic() + 25
            while time.monotonic() < limite:
                if enfant.poll() is not None:
                    raise GestionErreur("Le serveur s'est arrêté au démarrage ; consulter serveur-erreurs.log.")
                if self.verifie(self.port):
                    vue, serveurs, _, etrangers = self.inspecter()
                    if not etrangers and enfant.pid in vue["listeners"] and len(serveurs) == 1:
                        return "demarre"
                    raise GestionErreur("Le répondant HTTP n'est pas le serveur lancé ; aucun processus étranger arrêté.")
                time.sleep(0.25)
            raise GestionErreur("Serveur sans réponse HTTP après 25 secondes ; consulter serveur-erreurs.log.")

    def assurer_surveillance(self):
        with VerrouLocal(self.verrou, attente=60):
            if self.pause.exists():
                raise GestionErreur("Maintenance demandée entre-temps ; surveillance non démarrée.")
            _, _, surveillants, _ = self.inspecter()
            if len(surveillants) == 1:
                return "active"
            if surveillants:
                raise GestionErreur("Plusieurs surveillances détectées ; utiliser demarrer --redemarrer.")
            if not self.surveillance.is_file():
                raise GestionErreur("Script de surveillance absent ; serveur laissé actif.")
            enfant = self.lance(self.surveillance, ["--intervalle", "30", "--port", str(self.port)], self.racine,
                                self.racine / "surveillance-sortie.log", self.racine / "surveillance-erreurs.log")
            self.enfants.append(enfant)
            limite = time.monotonic() + 10
            while time.monotonic() < limite:
                if enfant.poll() is not None:
                    raise GestionErreur("La surveillance a quitté ; consulter surveillance-serveur.log et surveillance-erreurs.log.")
                try:
                    with VerrouLocal(self.racine / ".surveillance-serveur.lock"):
                        pass
                except VerrouOccupe:
                    _, _, surveillants, _ = self.inspecter()
                    if len(surveillants) == 1 and surveillants[0]["pid"] == enfant.pid:
                        return "active"
                time.sleep(0.25)
            raise GestionErreur("Démarrage de la surveillance non confirmé ; serveur laissé actif.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["demarrer", "arreter", "etat"])
    parser.add_argument("--redemarrer", action="store_true", help="Maintenance : arrêt ciblé puis nouvelle version serveur et surveillance.")
    parser.add_argument("--port", type=int, default=8751)
    parser.add_argument("--silencieux", action="store_true", help="Option des lanceurs BAT : ne pas attendre une touche.")
    parser.add_argument("--automatique", action="store_true", help="Démarrage Windows : respecter l'arrêt de maintenance.")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("Le port doit être compris entre 1 et 65535.")
    if args.redemarrer and args.action != "demarrer":
        parser.error("--redemarrer s'utilise seulement avec demarrer.")
    if args.automatique and (args.action != "demarrer" or args.redemarrer):
        parser.error("--automatique s'utilise avec demarrer sans --redemarrer.")
    service = GestionServeur(RACINE, args.port)
    journal = None
    logger = logging.getLogger("preparation.gestion")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    # La consultation 'etat' reste strictement en lecture seule.
    if args.action != "etat":
        journal = logging.FileHandler(RACINE / "gestion-serveur.log", mode="a", encoding="utf-8")
        journal.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(journal)
    try:
        if args.action == "etat":
            vue, serveurs, surveillants, etrangers = service.inspecter()
            sain = bool(len(serveurs) == 1 and vue["listeners"] and not etrangers and service.verifie(args.port))
            print(f"Serveur identifié : {len(serveurs)} ; HTTP applicatif : {'OK' if sain else 'indisponible'}.")
            print(f"Surveillance identifiée : {len(surveillants)} ; maintenance : {'oui' if service.pause.exists() else 'non'}.")
            if etrangers:
                print(f"Port {args.port} occupé par un autre processus ; ne pas le tuer.")
            return 0 if sain else 1
        if args.action == "arreter":
            service.arreter()
            message = "Serveur et surveillance du projet arrêtés. Maintenance conservée même à la prochaine session Windows."
            print(message)
            print("Reprise explicite : demarrer-serveur.bat")
            logger.info(message)
            return 0
        etat = service.demarrer(redemarrer=args.redemarrer, automatique=args.automatique)
        if etat == "maintenance":
            logger.info("Démarrage automatique ignoré : maintenance demandée.")
            print("Maintenance conservée ; reprise explicite avec demarrer-serveur.bat.")
            return 0
        service.assurer_surveillance()
        message = "Serveur déjà sain, conservé." if etat == "actif" else "Serveur démarré ; identité et réponse HTTP vérifiées."
        print(message)
        print("Surveillance active. Arrêt sans relance : arreter-serveur.bat")
        print(f"PC          http://127.0.0.1:{args.port}/app/index.html")
        print(f"Maintenance http://127.0.0.1:{args.port}/app/maintenance.html")
        if args.port == 8751:
            print("Mobile      https://desktop-11kv59v.tail44b4ba.ts.net/app/index.html")
            print("L'accès mobile dépend de Tailscale Serve ; le contrôle ci-dessus vérifie uniquement le serveur local.")
        logger.info("%s Surveillance active.", message)
        return 0
    except GestionErreur as erreur:
        print(f"REFUS : {erreur}", file=sys.stderr)
        if journal:
            logger.warning("%s", erreur)
        return 1
    except Exception as erreur:
        message = f"Erreur de gestion ({type(erreur).__name__}) ; vérifier les journaux locaux."
        print(message, file=sys.stderr)
        if journal:
            logger.error(message)
        return 1
    finally:
        if journal:
            logger.removeHandler(journal)
            journal.close()


if __name__ == "__main__":
    sys.exit(main())

"""Coordination coopérative des lectures/modifications et calculs d'un dossier.

Le verrou OS est libéré même si le processus s'arrête. Un enfant synchrone peut
recevoir explicitement le bail de son parent via environnement_verrou(). Cela
ne constitue ni une authentification ni une transaction multi-fichiers : une
interruption peut laisser un lot partiel, qui doit être repris avec ses preuves.
"""
from contextlib import contextmanager
from functools import wraps
import errno
import json
import os
from pathlib import Path
import threading
import time
import uuid

_MUTEX = threading.RLock()
_LOCAL = threading.local()
_VARIABLE = "PREPARATION_VERROU_DONNEES"


def _cle(dossier):
    return str(Path(dossier).resolve())


def _bail_herite(dossier):
    try:
        bail = json.loads(os.environ.get(_VARIABLE, "null"))
        if not isinstance(bail, dict) or bail.get("dossier") != _cle(dossier):
            return None
        actif = json.loads((Path(dossier) / ".operations-bail.lock").read_text(encoding="utf-8"))
        return bail if actif == bail else None
    except (OSError, ValueError, TypeError):
        return None


@contextmanager
def verrou_donnees(dossier, timeout=120):
    """Sérialise toute l'opération, y compris sa lecture avant écriture."""
    dossier = Path(dossier).resolve()
    cle = _cle(dossier)
    with _MUTEX:
        tenus = getattr(_LOCAL, "tenus", {})
        if cle in tenus:
            yield
            return
        herite = _bail_herite(dossier)
        if herite:
            _LOCAL.tenus = tenus
            tenus[cle] = herite
            try:
                yield
            finally:
                tenus.pop(cle)
            return
        dossier.mkdir(parents=True, exist_ok=True)
        with (dossier / ".operations.lock").open("a+b") as flux:
            fin = time.monotonic() + timeout
            while True:
                try:
                    flux.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(flux.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(flux.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    if time.monotonic() >= fin:
                        raise TimeoutError("Données occupées par une autre opération ; réessayer après sa fin.") from exc
                    time.sleep(.02)
            bail = {"dossier": cle, "pid": os.getpid(), "jeton": uuid.uuid4().hex}
            fichier_bail = dossier / ".operations-bail.lock"
            try:
                fichier_bail.write_text(json.dumps(bail), encoding="utf-8")
                _LOCAL.tenus = tenus
                tenus[cle] = bail
                yield
            finally:
                tenus.pop(cle, None)
                fichier_bail.unlink(missing_ok=True)
                flux.seek(0)
                if os.name == "nt":
                    msvcrt.locking(flux.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(flux.fileno(), fcntl.LOCK_UN)


def operation_donnees(dossier):
    """Décorateur ; une fonction fournit le dossier au moment de l'appel."""
    def decorer(fonction):
        @wraps(fonction)
        def execute(*args, **kwargs):
            with verrou_donnees(dossier() if callable(dossier) else dossier):
                return fonction(*args, **kwargs)
        return execute
    return decorer


def environnement_verrou(dossier):
    """Environnement réservé aux enfants synchrones attendus sous le verrou."""
    environnement = os.environ.copy()
    environnement.pop(_VARIABLE, None)
    bail = getattr(_LOCAL, "tenus", {}).get(_cle(dossier)) or _bail_herite(dossier)
    if bail:
        environnement[_VARIABLE] = json.dumps(bail)
    return environnement


def identifiant_operation(dossier):
    """Identifie le producteur commun, y compris dans ses enfants synchrones."""
    bail = getattr(_LOCAL, "tenus", {}).get(_cle(dossier)) or _bail_herite(dossier)
    return bail.get("jeton") if bail else None


def append_jsonl(chemin, objets):
    """Ajoute un lot validé, sans jamais réparer ou réécrire le carnet passé.

    Le caller garde verrou_donnees pendant lecture, contrôle d'identifiants et
    ajout. Le verrou fichier protège également les appels d'ajout seuls.
    """
    chemin = Path(chemin)
    contenu = "".join(json.dumps(objet, ensure_ascii=False, allow_nan=False) + "\n" for objet in objets)
    if not contenu:
        return
    dossier = next((p for p in chemin.resolve().parents if p.name == "donnees"), chemin.parent)
    with verrou_donnees(dossier):
        chemin.parent.mkdir(parents=True, exist_ok=True)
        with chemin.open("a+b") as flux:
            flux.seek(0, os.SEEK_END)
            if flux.tell():
                flux.seek(-1, os.SEEK_END)
                if flux.read(1) != b"\n":
                    raise ValueError(f"Carnet incomplet ({chemin.name}) : dernière ligne non terminée. Aucun ajout effectué.")
            flux.seek(0, os.SEEK_END)
            flux.write(contenu.encode("utf-8"))
            flux.flush()
            os.fsync(flux.fileno())

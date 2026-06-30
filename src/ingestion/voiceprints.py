"""Base d'empreintes vocales auto-grandissante — reconnaissance instantanée des locuteurs.

Principe : Resemblyzer produit une empreinte (256 flottants) par voix. On garde une base
``{nom → empreinte moyenne}`` persistée en JSON. En direct, on compare l'empreinte de chaque
locuteur à la base → match immédiat (« cette voix = Bompard ») AVANT même qu'un nom soit prononcé.

La base S'AUTO-CONSTRUIT : chaque fois qu'un locuteur est identifié par le contexte (le LLM lit
les indices du transcript : « la parole à M. Wauquiez »…), on enregistre son empreinte sous son
nom. La prochaine vidéo où il apparaît → reconnu instantanément. 100% local, aucun token.
"""
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

VOICEPRINT_PATH = Path(os.environ.get("VOICEPRINT_DB", "data/voiceprints/db.json"))
# Similarité cosinus minimale pour considérer deux empreintes comme le même locuteur.
# Resemblyzer sur des enregistrements/micros différents : ~0.75 est un bon compromis
# (assez haut pour éviter les faux positifs entre voix proches).
MATCH_THRESHOLD = float(os.environ.get("VOICEPRINT_MATCH_THRESHOLD", "0.75"))


def _norm(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v) + 1e-9)


class VoiceprintDB:
    """Base persistante {nom → empreinte vocale moyenne}, avec match cosinus."""

    def __init__(self, path: Path = VOICEPRINT_PATH):
        self.path = Path(path)
        self.names: List[str] = []
        self.embs: Optional[np.ndarray] = None  # (N, dim)
        self.counts: Dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            self.names = list(d.get("names", []))
            self.counts = dict(d.get("counts", {}))
            embs = d.get("embeddings", [])
            self.embs = np.array(embs, dtype=np.float32) if embs else None
            logger.info(f"VoiceprintDB chargée : {len(self.names)} locuteur(s) connu(s).")
        except Exception as e:
            logger.warning(f"VoiceprintDB illisible ({e}) — repart à vide.")
            self.names, self.embs, self.counts = [], None, {}

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            embs = self.embs.tolist() if self.embs is not None else []
            self.path.write_text(json.dumps(
                {"names": self.names, "counts": self.counts, "embeddings": embs},
                ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Échec sauvegarde VoiceprintDB : {e}")

    def match(self, emb: np.ndarray,
              candidates: Optional[List[str]] = None) -> Tuple[Optional[str], float]:
        """Renvoie (nom le plus proche, similarité cosinus). Restreint aux `candidates`
        (noms probables tirés du titre) si fournis, pour limiter les faux positifs."""
        if self.embs is None or not self.names:
            return None, 0.0
        e = _norm(np.asarray(emb, dtype=np.float32))
        E = self.embs / (np.linalg.norm(self.embs, axis=1, keepdims=True) + 1e-9)
        sims = E @ e
        idxs = list(range(len(self.names)))
        if candidates:
            cand = {c.lower() for c in candidates}
            restricted = [i for i in idxs if any(tok in self.names[i].lower() or self.names[i].lower() in tok
                                                 for tok in cand)]
            if restricted:
                idxs = restricted
        best = max(idxs, key=lambda i: float(sims[i]))
        return self.names[best], float(sims[best])

    def add(self, name: str, emb: np.ndarray) -> None:
        """Ajoute/renforce l'empreinte d'un locuteur (moyenne glissante si déjà connu)."""
        name = name.strip()
        if not name:
            return
        e = np.asarray(emb, dtype=np.float32)
        if name in self.names:
            i = self.names.index(name)
            n = self.counts.get(name, 1)
            self.embs[i] = (self.embs[i] * n + e) / (n + 1)
            self.counts[name] = n + 1
        else:
            self.names.append(name)
            self.counts[name] = 1
            self.embs = e[None, :] if self.embs is None else np.vstack([self.embs, e])


if __name__ == "__main__":
    # Test rapide sur empreintes synthétiques
    import tempfile
    p = Path(tempfile.mktemp(suffix=".json"))
    db = VoiceprintDB(p)
    rng = np.random.RandomState(0)
    a = rng.randn(256); b = rng.randn(256)
    db.add("Bompard", a); db.add("Wauquiez", b); db.save()
    db2 = VoiceprintDB(p)
    # une empreinte proche de 'a' (+ bruit) doit matcher Bompard
    noisy = a + 0.1 * rng.randn(256)
    name, score = db2.match(noisy, candidates=["Bompard", "Wauquiez"])
    print(f"match → {name} (score {score:.3f}) | DB: {db2.names}")
    p.unlink(missing_ok=True)

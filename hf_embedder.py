import os
import time
import sqlite3
import hashlib
from typing import List
import numpy as np
from huggingface_hub import InferenceClient

HF_TOKEN = os.environ.get("HF_TOKEN", "")

# Modello di default: multilingue, supporta feature-extraction su Inference API
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL = os.environ.get("HF_EMBED_MODEL", DEFAULT_MODEL)

os.environ.setdefault("HF_HOME", "./.cache/huggingface")
os.environ.setdefault("TRANSFORMERS_CACHE", "./.cache/huggingface")

def _use_e5_prefixes(model_name: str) -> bool:
    return "e5" in model_name.lower()

class _Cache:
    def __init__(self, path: str = "./embedding_cache.sqlite"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v BLOB)")
        self.conn.commit()

    @staticmethod
    def _k(model: str, text: str, prefix: str) -> str:
        return hashlib.sha256((model + "|" + prefix + text).encode("utf-8")).hexdigest()

    def get(self, model: str, text: str, prefix: str):
        k = self._k(model, text, prefix)
        cur = self.conn.execute("SELECT v FROM cache WHERE k=?", (k,))
        row = cur.fetchone()
        if not row:
            return None
        return np.frombuffer(row[0], dtype=np.float32)

    def set(self, model: str, text: str, prefix: str, vec: np.ndarray):
        k = self._k(model, text, prefix)
        self.conn.execute("INSERT OR REPLACE INTO cache(k, v) VALUES(?, ?)", (k, vec.astype(np.float32).tobytes()))
        self.conn.commit()

def _l2norm(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True) + 1e-12
    return x / n

class HFEmbedder:
    def __init__(self, model: str = MODEL, cache_path: str = "./embedding_cache.sqlite", batch_size: int = 64):
        if not HF_TOKEN:
            raise RuntimeError("HF_TOKEN env var is missing.")
        self.model = model
        self.client = InferenceClient(model=self.model, token=HF_TOKEN)
        self.cache = _Cache(cache_path)
        self.batch_size = batch_size
        self.use_e5 = _use_e5_prefixes(self.model)

    def _remote_embed_batch(self, texts: List[str]):
        # retry semplice (alcuni modelli si "svegliano" al primo colpo)
        last_exc = None
        for attempt in range(4):
            try:
                return self.client.feature_extraction(texts)
            except Exception as e:
                last_exc = e
                time.sleep(0.8 * (attempt + 1))
        raise RuntimeError(f"HF feature_extraction failed: {last_exc}")

    def embed_texts(self, texts, is_query: bool = False) -> np.ndarray:
        if isinstance(texts, str):
            texts = [texts]

        prefix = ""
        if self.use_e5:
            prefix = "query: " if is_query else "passage: "

        out = [None] * len(texts)
        to_send, idxs = [], []

        # cache lookup
        for i, t in enumerate(texts):
            c = self.cache.get(self.model, t, prefix)
            if c is None:
                to_send.append(prefix + t)
                idxs.append(i)
            else:
                out[i] = c

        # remote batches
        for s in range(0, len(to_send), self.batch_size):
            batch = to_send[s:s + self.batch_size]
            resp = self._remote_embed_batch(batch)

            # --- parsing robusto: gestisce 1D / 2D / 3D ---
            arr = np.array(resp, dtype=np.float32)
            if arr.ndim == 3:
                # [batch, tokens, dim] -> mean pooling
                vecs = arr.mean(axis=1)
            elif arr.ndim == 2:
                # [batch, dim] -> ok
                vecs = arr
            elif arr.ndim == 1:
                # [dim] -> [1, dim]
                vecs = arr[None, :]
            else:
                raise RuntimeError(f"Unexpected response shape from feature_extraction: ndim={arr.ndim}")

            vecs = _l2norm(vecs)

            for j, v in enumerate(vecs):
                i = idxs[s + j]
                out[i] = v
                self.cache.set(self.model, texts[i], prefix, v)

        return np.stack(out, axis=0).astype(np.float32)

    def embed_one(self, text: str, is_query: bool = False) -> np.ndarray:
        return self.embed_texts([text], is_query=is_query)[0]
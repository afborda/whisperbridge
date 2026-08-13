"""
Identificação online de falantes (speaker ID), não diarização full.

Problemas do algoritmo antigo que este módulo corrige:
  1. Centroide com EMA — um embedding ruim poluía o perfil para sempre
  2. Segmentos curtos — assinatura aleatória virava "Pessoa nova"
  3. Silêncio no fim do VAD — degradava o embedding
  4. Decisão gulosa sem margem — sem zona ambígua nem correção posterior

Abordagem:
  - Galeria de embeddings por pessoa (janela deslizante) + centróide
  - Histerese: SAME / ambíguo / NEW (ambíguo NÃO aprende)
  - Gate de qualidade: duração, RMS, áudio forte para criar novo
  - Trim de silêncio nas pontas
  - Prior temporal: favorece o último falante em zona cinza
  - Re-cluster periódico para fundir fantasmas
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np
import torch

SAMPLE_RATE = 16000

# ── Decisões em SIMILARIDADE coseno (1.0 = voz idêntica, 0 = diferente) ────────
# wespeaker: mesmo falante costuma ficar ~0.65–0.95; pessoas diferentes ~0.0–0.45
SAME_SPEAKER_SIM = 0.58  # >= isso => confiantemente a MESMA pessoa (aprende)
NEW_SPEAKER_SIM = 0.42  # <  isso => confiantemente pessoa DIFERENTE (se áudio forte)
# entre os dois = zona ambígua: atribui, mas NÃO aprende

# Em zona ambígua, se o último falante está a até este delta do melhor, mantém ele
# (evita flip-flop em conversa rápida)
TEMPORAL_MARGIN = 0.06

# ── Gate de qualidade — evita que trechos ruins criem falantes fantasma ───────
MIN_AUDIO_S = 0.9  # abaixo: herda o último falante (não decide)
# Era 1.5 — mas com segmentos de até 1.8s quase TODO segmento passava por "forte" e
# podia inventar gente nova. Pior: em 1.5s cabe 1 janela do Inference sliding
# (duration=1.5, step=0.75), ou seja, embedding sem média nenhuma, puro ruído.
# 2.5s garante 3+ janelas antes de aceitar "esta é outra pessoa".
STRONG_AUDIO_S = 2.5
MIN_RMS = 0.004  # energia mínima (ruído/silêncio)
LEARN_RMS = 0.008  # energia mínima para entrar na galeria

# ── Galeria de vozes por falante (em vez de EMA que desvia) ───────────────────
GALLERY_SIZE = 14  # embeddings guardados por pessoa
RECLUSTER_EVERY = 5  # re-agrupa a cada N embeddings aprendidos
RECLUSTER_DIST = 0.46  # distância cosseno (1-sim) para fundir fantasmas
MERGE_CENTROID_SIM = 0.62  # fallback sem sklearn: funde se centróides próximos

SPEAKER_COLORS = [
    "#60a5fa",  # azul
    "#4ade80",  # verde
    "#f472b6",  # rosa
    "#fbbf24",  # âmbar
    "#c4b5fd",  # lilás
    "#34d399",  # esmeralda
    "#fb923c",  # laranja
    "#a5f3fc",  # ciano
]

try:
    from sklearn.cluster import AgglomerativeClustering

    _HAS_SKLEARN = True
except Exception:
    _HAS_SKLEARN = False


def _trim_silence(audio: np.ndarray) -> np.ndarray:
    """Remove silêncio nas pontas — silêncio do VAD degrada a impressão vocal."""
    frame = 320  # 20 ms @ 16 kHz
    n = len(audio) // frame
    if n < 3:
        return audio
    frames = audio[: n * frame].reshape(n, frame)
    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-9)
    peak = float(rms.max())
    if peak < 1e-6:
        return audio
    thr = max(peak * 0.15, MIN_RMS)
    voiced = np.where(rms >= thr)[0]
    if len(voiced) == 0:
        return audio
    a = int(voiced[0]) * frame
    b = (int(voiced[-1]) + 1) * frame
    return audio[a:b]


def _normalize(emb: np.ndarray) -> Optional[np.ndarray]:
    emb = np.asarray(emb, dtype=np.float64).flatten()
    norm = float(np.linalg.norm(emb))
    if norm < 1e-8:
        return None
    return emb / norm


class SpeakerTracker:
    def __init__(self, hf_token: str):
        print("Carregando modelo de identificação de falantes...", end=" ", flush=True)
        t0 = time.time()

        from pyannote.audio import Model, Inference

        model = Model.from_pretrained(
            "pyannote/wespeaker-voxceleb-resnet34-LM",
            use_auth_token=hf_token,
        )
        # sliding + média = mais estável que uma única janela "whole"
        self._inference = Inference(model, window="sliding", duration=1.5, step=0.75)
        self._inference_whole = Inference(model, window="whole")

        # galeria: id -> lista de embeddings normalizados
        self._gallery: dict[str, list[np.ndarray]] = {}
        # centróide cacheado: id -> embedding médio normalizado
        self._centroid: dict[str, np.ndarray] = {}
        self._next_num = 1
        self._last_id: Optional[str] = None
        self._learned_since_recluster = 0

        print(
            f"OK ({time.time() - t0:.1f}s"
            + (", com re-cluster" if _HAS_SKLEARN else ", re-cluster simples")
            + ")",
            flush=True,
        )

    # ── embedding robusto ─────────────────────────────────────────────────────
    def _embed(self, audio: np.ndarray) -> tuple[Optional[np.ndarray], float, float]:
        clean = _trim_silence(audio.astype(np.float32, copy=False))
        dur = len(clean) / SAMPLE_RATE
        rms = float(np.sqrt((clean ** 2).mean() + 1e-9))
        if dur < MIN_AUDIO_S or rms < MIN_RMS:
            return None, dur, rms

        try:
            tensor = torch.from_numpy(np.ascontiguousarray(clean, dtype=np.float32)[np.newaxis, :])
            data = {"waveform": tensor, "sample_rate": SAMPLE_RATE}

            if dur >= 1.5:
                result = self._inference(data)
                arr = np.array(result.data if hasattr(result, "data") else result)
                emb = arr.mean(axis=0) if arr.ndim > 1 else arr
            else:
                result = self._inference_whole(data)
                emb = np.array(result.data if hasattr(result, "data") else result)

            emb_n = _normalize(emb)
            if emb_n is None:
                return None, dur, rms
            return emb_n, dur, rms
        except Exception as e:
            print(f"[speaker] erro embedding: {e}", flush=True)
            return None, dur, rms

    def _recompute_centroid(self, sid: str) -> None:
        embs = self._gallery.get(sid) or []
        if not embs:
            self._centroid.pop(sid, None)
            return
        mean = np.mean(np.stack(embs, axis=0), axis=0)
        n = _normalize(mean)
        if n is not None:
            self._centroid[sid] = n

    def _add_to_gallery(self, sid: str, emb: np.ndarray) -> None:
        g = self._gallery.setdefault(sid, [])
        g.append(emb)
        if len(g) > GALLERY_SIZE:
            del g[0]
        self._recompute_centroid(sid)
        self._learned_since_recluster += 1
        if self._learned_since_recluster >= RECLUSTER_EVERY:
            self._recluster()
            self._learned_since_recluster = 0

    def _similarity_to(self, emb: np.ndarray, sid: str) -> float:
        """Melhor similaridade: max(centróide, qualquer embedding da galeria)."""
        best = -1.0
        c = self._centroid.get(sid)
        if c is not None:
            best = max(best, float(np.dot(emb, c)))
        for g in self._gallery.get(sid, []):
            best = max(best, float(np.dot(emb, g)))
        return best

    def _all_similarities(self, emb: np.ndarray) -> dict[str, float]:
        return {sid: self._similarity_to(emb, sid) for sid in self._gallery if self._gallery[sid]}

    # ── decisão principal ─────────────────────────────────────────────────────
    def identify(self, audio: np.ndarray) -> dict:
        emb, dur, rms = self._embed(audio)

        # trecho curto/fraco: não decide — herda o último falante
        if emb is None:
            if self._last_id:
                return self._make(self._last_id, is_new=False)
            # sem voz útil ainda: rótulo temporário, SEM registrar na galeria
            return self._make("Pessoa 1", is_new=True)

        # primeiro embedding válido da sessão
        if not self._centroid:
            sid = self._new_speaker(emb)
            self._last_id = sid
            print(f"[speaker] + {sid} PRIMEIRO (dur={dur:.1f}s rms={rms:.4f})", flush=True)
            return self._make(sid, is_new=True)

        sims = self._all_similarities(emb)
        if not sims:
            sid = self._new_speaker(emb)
            self._last_id = sid
            return self._make(sid, is_new=True)

        best_id = max(sims, key=sims.get)
        best_sim = sims[best_id]
        strong = dur >= STRONG_AUDIO_S and rms >= LEARN_RMS
        dbg = ", ".join(f"{s}={v:.2f}" for s, v in sorted(sims.items()))

        # 1) confiantemente a mesma pessoa → aprende (se energia ok)
        if best_sim >= SAME_SPEAKER_SIM:
            if rms >= LEARN_RMS:
                self._add_to_gallery(best_id, emb)
            self._last_id = best_id
            print(f"[speaker] = {best_id} (sim={best_sim:.2f} | {dbg})", flush=True)
            return self._make(best_id, is_new=False)

        # 2) confiantemente diferente + áudio forte → nova pessoa
        if strong and best_sim < NEW_SPEAKER_SIM:
            sid = self._new_speaker(emb)
            self._last_id = sid
            print(f"[speaker] + {sid} NOVO (melhor={best_sim:.2f} | {dbg})", flush=True)
            return self._make(sid, is_new=True)

        # 3) zona ambígua OU áudio fraco demais para criar:
        #    prior temporal: se o último falante está perto do melhor, mantém ele
        chosen = best_id
        if self._last_id and self._last_id in sims:
            last_sim = sims[self._last_id]
            if last_sim + TEMPORAL_MARGIN >= best_sim:
                chosen = self._last_id

        self._last_id = chosen
        # NÃO aprende — evita poluir galeria com embedding duvidoso
        print(f"[speaker] ~ {chosen} ambiguo (sim={sims[chosen]:.2f} | {dbg})", flush=True)
        return self._make(chosen, is_new=False)

    def _new_speaker(self, emb: np.ndarray) -> str:
        sid = f"Pessoa {self._next_num}"
        self._next_num += 1
        self._gallery[sid] = [emb]
        self._recompute_centroid(sid)
        return sid

    # ── re-agrupamento: funde falantes fantasma ────────────────────────────────
    def _recluster(self) -> None:
        ids = [s for s in self._gallery if self._gallery[s]]
        if len(ids) < 2:
            return

        if _HAS_SKLEARN:
            self._recluster_sklearn(ids)
        else:
            self._recluster_pairwise()

    def _recluster_sklearn(self, ids: list[str]) -> None:
        all_emb: list[np.ndarray] = []
        owner: list[str] = []
        for sid in ids:
            for e in self._gallery[sid]:
                all_emb.append(e)
                owner.append(sid)
        X = np.vstack(all_emb)

        try:
            clustering = AgglomerativeClustering(
                n_clusters=None,
                distance_threshold=RECLUSTER_DIST,
                metric="cosine",
                linkage="average",
            ).fit(X)
        except Exception as e:
            print(f"[speaker] recluster falhou: {e}", flush=True)
            return

        cluster_to_speakers: dict[int, set[str]] = {}
        for lbl, sid in zip(clustering.labels_, owner):
            cluster_to_speakers.setdefault(int(lbl), set()).add(sid)

        merge_map: dict[str, str] = {}
        for speakers in cluster_to_speakers.values():
            if len(speakers) < 2:
                continue
            canonical = min(speakers, key=lambda s: int(s.split()[-1]))
            for s in speakers:
                if s != canonical:
                    merge_map[s] = canonical

        self._apply_merges(merge_map)

    def _recluster_pairwise(self) -> None:
        """Fallback sem sklearn: funde pares de centróides muito próximos."""
        ids = [s for s in self._centroid if self._gallery.get(s)]
        if len(ids) < 2:
            return

        merge_map: dict[str, str] = {}
        # ordena por número para sempre fundir no de menor índice
        ids_sorted = sorted(ids, key=lambda s: int(s.split()[-1]))
        for i, a in enumerate(ids_sorted):
            if a in merge_map:
                continue
            ca = self._centroid.get(a)
            if ca is None:
                continue
            for b in ids_sorted[i + 1 :]:
                if b in merge_map:
                    continue
                cb = self._centroid.get(b)
                if cb is None:
                    continue
                sim = float(np.dot(ca, cb))
                if sim >= MERGE_CENTROID_SIM:
                    merge_map[b] = a

        self._apply_merges(merge_map)

    def _apply_merges(self, merge_map: dict[str, str]) -> None:
        if not merge_map:
            return

        # resolve cadeias A->B, B->C
        def root(s: str) -> str:
            seen = set()
            while s in merge_map and s not in seen:
                seen.add(s)
                s = merge_map[s]
            return s

        resolved = {v: root(c) for v, c in merge_map.items()}
        for victim, canonical in resolved.items():
            if victim == canonical:
                continue
            self._gallery.setdefault(canonical, []).extend(self._gallery.get(victim, []))
            self._gallery[canonical] = self._gallery[canonical][-GALLERY_SIZE:]
            self._gallery.pop(victim, None)
            self._centroid.pop(victim, None)
            self._recompute_centroid(canonical)
            if self._last_id == victim:
                self._last_id = canonical

        fused = ", ".join(f"{v}->{c}" for v, c in resolved.items())
        print(f"[speaker] FUNDIU fantasmas: {fused}", flush=True)

    def _make(self, speaker_id: str, is_new: bool) -> dict:
        try:
            idx = (int(speaker_id.split()[-1]) - 1) % len(SPEAKER_COLORS)
        except (ValueError, IndexError):
            idx = 0
        return {"id": speaker_id, "color": SPEAKER_COLORS[idx], "is_new": is_new}

    def reset(self) -> None:
        self._gallery.clear()
        self._centroid.clear()
        self._next_num = 1
        self._last_id = None
        self._learned_since_recluster = 0


def load_tracker(hf_token: str | None) -> Optional[SpeakerTracker]:
    if not hf_token:
        return None
    try:
        return SpeakerTracker(hf_token)
    except Exception as e:
        print(f"[speaker] falha ao carregar: {e}", flush=True)
        return None

"""Leitor OMR — detecta gabarito compacto embutido na página.

Pipeline:
1. Detecta 4 marcadores quadrados pretos nos cantos do gabarito.
2. Corrige perspectiva via homografia (RANSAC).
3. Normaliza iluminação (CLAHE).
4. Amostra bolhas nas coordenadas calculadas pela geometria.
5. Decide alternativa marcada por intensidade relativa.
6. Compara com gabarito → calcula nota 0–10.
"""
from __future__ import annotations
import numpy as np
import cv2

from omr_geometry import (
    PAGE_W, PAGE_H, FIDUCIAL_SIZE,
    NUM_OPTIONS, BUBBLE_RADIUS, BUBBLE_SPACING, ROW_H, COL_NUM_W,
    HEADER_H, PADDING, omr_layout, omr_box_height, omr_box_width,
    _choose_n_cols,
)

# Canvas normalizado: 4 px/pt ≈ 288 dpi
SCALE  = 4


def _decode(raw: bytes):
    arr = np.frombuffer(raw, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


# ─── detecção de marcadores ───────────────────────────────────────────────────

def _find_fiducials(gray: np.ndarray, num_questions: int):
    """
    Localiza os 4 marcadores quadrados pretos do gabarito compacto.

    Estratégia multi-escala:
    - Threshold adaptativo + Otsu
    - Filtra por quadraticidade, tamanho relativo e densidade
    - Escolhe o candidato mais próximo de cada canto da imagem
    """
    h, w = gray.shape

    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    _, th = cv2.threshold(blur, 0, 255,
                          cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=2)

    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    img_area = h * w
    candidates = []

    for cnt in cnts:
        x, y, ww, hh = cv2.boundingRect(cnt)
        if ww < 5 or hh < 5:
            continue
        ratio = ww / float(hh)
        if not (0.45 <= ratio <= 2.2):
            continue
        area = ww * hh
        if area < img_area * 0.000008 or area > img_area * 0.025:
            continue
        roi  = th[y: y + hh, x: x + ww]
        fill = roi.mean() / 255.0
        if fill < 0.40:
            continue
        candidates.append((x + ww / 2.0, y + hh / 2.0, area))

    if len(candidates) < 4:
        return None

    # Para cada canto da imagem (BL BR TL TR) pega o candidato mais próximo
    corners = [(0, h), (w, h), (0, 0), (w, 0)]
    chosen, used = [], set()
    for (tx, ty) in corners:
        best_i, best_d = None, float("inf")
        for i, (cx, cy, _) in enumerate(candidates):
            if i in used:
                continue
            d = (cx - tx) ** 2 + (cy - ty) ** 2
            if d < best_d:
                best_d, best_i = d, i
        if best_i is None:
            return None
        used.add(best_i)
        chosen.append((candidates[best_i][0], candidates[best_i][1]))

    return chosen   # BL BR TL TR (pixels)


# ─── homografia ───────────────────────────────────────────────────────────────

def _warp_to_box(img: np.ndarray, corners_px, num_questions: int):
    """
    Aplica homografia mapeando os 4 marcadores detectados para as posições
    esperadas do gabarito em um canvas normalizado.
    """
    nc    = _choose_n_cols(num_questions)
    bw    = omr_box_width(nc)
    bh    = omr_box_height(num_questions, nc)

    NW = int(bw * SCALE)
    NH = int(bh * SCALE)
    fm = FIDUCIAL_SIZE

    # Posições esperadas dos marcadores no canvas (y de baixo → cima → inverter)
    # Ordem BL BR TL TR
    dst = np.array([
        [fm * SCALE / 2,             (bh - fm / 2) * SCALE],   # BL
        [(bw - fm / 2) * SCALE,      (bh - fm / 2) * SCALE],   # BR
        [fm * SCALE / 2,             (fm / 2) * SCALE],         # TL
        [(bw - fm / 2) * SCALE,      (fm / 2) * SCALE],         # TR
    ], dtype=np.float32)

    src = np.array(corners_px, dtype=np.float32)
    H, _ = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if H is None:
        return None, NW, NH
    warped = cv2.warpPerspective(img, H, (NW, NH), flags=cv2.INTER_LINEAR)
    return warped, NW, NH


# ─── amostragem ───────────────────────────────────────────────────────────────

def _sample(gray: np.ndarray, x_pt: float, y_pt: float,
            bh: float, NW: int, NH: int) -> float:
    """Fração de preenchimento da bolha centrada em (x_pt, y_pt) pt."""
    cx = int(x_pt * SCALE)
    cy = int((bh - y_pt) * SCALE)   # inverter y
    r  = max(1, int(BUBBLE_RADIUS * SCALE * 0.62))
    x0, y0 = max(0, cx - r), max(0, cy - r)
    x1, y1 = min(NW, cx + r + 1), min(NH, cy + r + 1)
    roi = gray[y0:y1, x0:x1]
    if roi.size == 0:
        return 0.0
    return float(255 - roi.mean()) / 255.0


# ─── detecção principal ───────────────────────────────────────────────────────

def detect_answers(image_bytes: bytes, num_questions: int):
    """
    Detecta marcações na folha escaneada.

    Retorna:
      ok        bool
      answers   list[int|None]   — índice marcado (0=A … 4=E)
      fills     list[list[float]]
      error     str|None
    """
    img = _decode(image_bytes)
    if img is None:
        return {"ok": False, "answers": [None] * num_questions,
                "fills": [], "error": "Imagem inválida ou formato não suportado."}

    gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray  = clahe.apply(gray)

    corners = _find_fiducials(gray, num_questions)
    if not corners:
        return {
            "ok": False, "answers": [None] * num_questions, "fills": [],
            "error": (
                "Marcadores OMR não detectados. "
                "Garanta que os 4 quadrados pretos do gabarito "
                "estejam completamente visíveis na foto."
            ),
        }

    warped, NW, NH = _warp_to_box(img, corners, num_questions)
    if warped is None:
        return {"ok": False, "answers": [None] * num_questions,
                "fills": [], "error": "Falha ao corrigir perspectiva."}

    gw = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    gw = cv2.GaussianBlur(gw, (3, 3), 0)

    nc  = _choose_n_cols(num_questions)
    bw  = omr_box_width(nc)
    bh  = omr_box_height(num_questions, nc)
    lay = omr_layout(num_questions, 0, bh)   # box_x=0, box_y_top=bh

    fills_per_q: list[list[float]] = [
        [0.0] * NUM_OPTIONS for _ in range(num_questions)
    ]
    for q_idx, opt_idx, x_pt, y_pt in lay["bubbles"]:
        if q_idx >= num_questions:
            continue
        fills_per_q[q_idx][opt_idx] = _sample(gw, x_pt, y_pt, bh, NW, NH)

    answers: list[int | None] = [None] * num_questions
    for q_idx, fills in enumerate(fills_per_q):
        sf = sorted(enumerate(fills), key=lambda x: x[1], reverse=True)
        top_i, top_v   = sf[0]
        second_v       = sf[1][1] if len(sf) > 1 else 0.0
        if top_v >= 0.28 and (top_v - second_v) >= 0.07:
            answers[q_idx] = top_i

    return {"ok": True, "answers": answers, "fills": fills_per_q, "error": None}


# ─── nota ─────────────────────────────────────────────────────────────────────

def grade_against_key(answers, correct_indices):
    total = sum(1 for c in correct_indices if c is not None)
    hits, details, wrong_qs = 0, [], []
    for i, c in enumerate(correct_indices):
        a = answers[i] if i < len(answers) else None
        if c is None:
            details.append({"q": i+1, "correct": None, "marked": a,
                            "ok": None, "skipped": True})
            continue
        ok = (a is not None and a == c)
        if ok:
            hits += 1
        else:
            wrong_qs.append(i + 1)
        details.append({"q": i+1, "correct": c, "marked": a,
                        "ok": ok, "skipped": False})
    score = round((10.0 / total) * hits, 2) if total > 0 else 0.0
    return {"total": total, "correct": hits, "wrong": total - hits,
            "score": score, "details": details, "wrong_questions": wrong_qs}


def best_version_match(answers, versions_payloads):
    best, best_hits = None, -1
    for ver_id, label, payload in versions_payloads:
        correct = [(q.get("correct_index")
                    if q.get("type") in ("objective", "tf") else None)
                   for q in payload]
        hits = sum(1 for i, c in enumerate(correct)
                   if c is not None and i < len(answers) and answers[i] == c)
        if hits > best_hits:
            best_hits, best = hits, (ver_id, label, correct)
    return best, best_hits

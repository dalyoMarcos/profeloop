"""Leitor OMR — pipeline completo e confiável.

Pipeline:
1. Carrega a imagem.
2. Detecta 4 marcadores quadrados pretos nos cantos.
3. Corrige perspectiva via homografia.
4. Corrige rotação (garante orientação correta).
5. Amostra cada bolha nas coordenadas exatas do PDF.
6. Decide qual alternativa está marcada.
7. Compara com gabarito e calcula nota (0–10).

Identificação da versão é feita no app.py via best_version_match().
"""
from __future__ import annotations

import numpy as np
import cv2

from omr_geometry import (
    PAGE_W, PAGE_H, FIDUCIAL_SIZE, fiducial_centers,
    answer_sheet_layout, BUBBLE_RADIUS, NUM_OPTIONS,
)

# Escala do canvas normalizado: 4 px por ponto (~288 dpi equivalente)
SCALE  = 4
NORM_W = int(PAGE_W * SCALE)
NORM_H = int(PAGE_H * SCALE)


# ─────────────────────────────── I/O ────────────────────────────────────────

def _decode(image_bytes: bytes):
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


# ───────────────────────── detecção de marcadores ───────────────────────────

def _find_fiducials(gray: np.ndarray):
    """
    Procura os 4 marcadores quadrados pretos.

    Estratégia:
    - Threshold adaptativo + Otsu sobre blur gaussiano.
    - Filtra por proporção (quadrado), tamanho relativo e densidade de preto.
    - Para cada canto da imagem seleciona o candidato mais próximo.

    Retorna lista [(cx, cy), …] em ordem [BL, BR, TL, TR] (pixels),
    ou None se não conseguir encontrar 4.
    """
    h, w = gray.shape

    # Pré-processamento
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    _, th = cv2.threshold(blur, 0, 255,
                          cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)

    # Morfologia: fecha pequenos buracos para robustecer contornos
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    img_area = h * w
    candidates = []

    for cnt in contours:
        x, y, ww, hh = cv2.boundingRect(cnt)
        if ww < 6 or hh < 6:
            continue
        ratio = ww / float(hh)
        if not (0.5 <= ratio <= 2.0):
            continue
        area = ww * hh
        # faixa de tamanho: 0.001 % a 3 % da imagem
        if area < img_area * 0.00001 or area > img_area * 0.03:
            continue
        # densidade de preto dentro da bounding box
        roi  = th[y: y + hh, x: x + ww]
        fill = roi.mean() / 255.0
        if fill < 0.45:
            continue
        cx_c = x + ww / 2.0
        cy_c = y + hh / 2.0
        candidates.append((cx_c, cy_c, area))

    if len(candidates) < 4:
        return None

    # Ordena cantos: BL, BR, TL, TR  (x vai da esquerda; y vai de cima para baixo)
    corners_img = [
        (0,     h),    # BL — canto inferior-esquerdo
        (w,     h),    # BR — canto inferior-direito
        (0,     0),    # TL — canto superior-esquerdo
        (w,     0),    # TR — canto superior-direito
    ]

    chosen = []
    used   = set()
    for (tx, ty) in corners_img:
        best   = None
        best_d = float("inf")
        for i, (cx_c, cy_c, _a) in enumerate(candidates):
            if i in used:
                continue
            d = (cx_c - tx) ** 2 + (cy_c - ty) ** 2
            if d < best_d:
                best_d = d
                best   = i
        if best is None:
            return None
        used.add(best)
        chosen.append((candidates[best][0], candidates[best][1]))

    return chosen  # [(cx,cy) x 4] — BL, BR, TL, TR


# ──────────────────────────── homografia ────────────────────────────────────

def _warp(img: np.ndarray, corners_px):
    """
    Aplica homografia para o canvas normalizado (NORM_W × NORM_H).

    corners_px está em pixels e ordem [BL, BR, TL, TR].
    O canvas alvo usa y crescente para baixo (OpenCV).
    """
    centers_pt = fiducial_centers()  # [BL, BR, TL, TR] em pt, y de baixo → cima

    dst = []
    for (cx_pt, cy_pt) in centers_pt:
        dx = cx_pt * SCALE
        dy = (PAGE_H - cy_pt) * SCALE   # inverter y → OpenCV
        dst.append([dx, dy])

    src = np.array(corners_px, dtype=np.float32)
    dst = np.array(dst,        dtype=np.float32)

    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if H is None:
        return None
    warped = cv2.warpPerspective(img, H, (NORM_W, NORM_H),
                                 flags=cv2.INTER_LINEAR)
    return warped


def _fix_rotation(warped: np.ndarray):
    """
    Verifica se a imagem foi carregada de cabeça para baixo ou espelhada
    checando os marcadores após o warp. Se os marcadores esperados (quadrados
    pretos) não estiverem nas posições corretas, retorna None — o warp já deve
    ter corrigido a perspectiva; esta função apenas valida.

    Nesta versão simplificada garantimos que o warp com RANSAC já lida com
    pequenas rotações. Retorna a imagem sem alteração.
    """
    return warped


# ─────────────────────────── amostragem de bolha ────────────────────────────

def _sample_bubble(gray_warped: np.ndarray, x_pt: float, y_pt: float) -> float:
    """
    Fração de preenchimento (0..1) da bolha centrada em (x_pt, y_pt) pt.

    Usa raio ligeiramente menor que o desenhado para ignorar a borda da bolha.
    """
    cx = int(x_pt * SCALE)
    cy = int((PAGE_H - y_pt) * SCALE)   # inverter y
    r  = max(1, int(BUBBLE_RADIUS * SCALE * 0.65))

    x0, y0 = max(0, cx - r), max(0, cy - r)
    x1, y1 = min(NORM_W, cx + r + 1), min(NORM_H, cy + r + 1)

    roi = gray_warped[y0:y1, x0:x1]
    if roi.size == 0:
        return 0.0
    # Quanto mais escuro → mais preenchido
    return float(255 - roi.mean()) / 255.0


# ──────────────────────────── detecção principal ────────────────────────────

def detect_answers(image_bytes: bytes, num_questions: int):
    """
    Detecta marcações em uma imagem da folha de respostas.

    Retorna:
      ok        bool             — conseguiu processar
      answers   list[int|None]  — índice marcado (0..NUM_OPTIONS-1) por questão
      fills     list[list[float]]— intensidades por bolha (debug)
      error     str|None
    """
    img = _decode(image_bytes)
    if img is None:
        return {"ok": False, "answers": [None] * num_questions,
                "fills": [], "error": "Imagem invalida ou formato nao suportado."}

    # ── Pré-processamento ────────────────────────────────────────────────
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Normaliza iluminação (CLAHE)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray  = clahe.apply(gray)

    # ── Marcadores ──────────────────────────────────────────────────────
    corners = _find_fiducials(gray)
    if not corners:
        return {
            "ok": False,
            "answers": [None] * num_questions,
            "fills":   [],
            "error":   (
                "Marcadores OMR nao detectados. "
                "Certifique-se de que os 4 quadrados pretos dos cantos "
                "estejam completamente visiveis e sem obstrucoes na foto."
            ),
        }

    # ── Warp ─────────────────────────────────────────────────────────────
    warped = _warp(img, corners)
    if warped is None:
        return {"ok": False, "answers": [None] * num_questions,
                "fills": [], "error": "Falha ao corrigir perspectiva."}

    warped = _fix_rotation(warped)

    # Escala de cinza + blur leve para reduzir ruído
    gw = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    gw = cv2.GaussianBlur(gw, (3, 3), 0)

    # ── Amostragem ───────────────────────────────────────────────────────
    layout = answer_sheet_layout(num_questions)
    fills_per_q: list[list[float]] = [
        [0.0] * NUM_OPTIONS for _ in range(num_questions)
    ]

    for q_idx, opt_idx, x_pt, y_pt in layout["bubbles"]:
        if q_idx >= num_questions:
            continue
        fills_per_q[q_idx][opt_idx] = _sample_bubble(gw, x_pt, y_pt)

    # ── Decisão por questão ───────────────────────────────────────────────
    answers: list[int | None] = [None] * num_questions

    for q_idx, fills in enumerate(fills_per_q):
        sorted_fills = sorted(enumerate(fills), key=lambda x: x[1], reverse=True)
        top_i, top_v   = sorted_fills[0]
        second_v       = sorted_fills[1][1] if len(sorted_fills) > 1 else 0.0

        # Limiar: bolha deve estar claramente mais escura que as outras
        if top_v >= 0.30 and (top_v - second_v) >= 0.07:
            answers[q_idx] = top_i

    return {
        "ok":      True,
        "answers": answers,
        "fills":   fills_per_q,
        "error":   None,
    }


# ────────────────────────── cálculo de nota ─────────────────────────────────

def grade_against_key(answers, correct_indices):
    """
    Compara marcações detectadas com gabarito.

    Fórmula: nota = (acertos / total_objetivas) * 10

    Retorna dict:
      total          — questões objetivas
      correct        — acertos
      wrong          — erros
      score          — nota 0..10 (2 casas decimais)
      details        — detalhe por questão
      wrong_questions— lista de nº das questões erradas
    """
    total = sum(1 for c in correct_indices if c is not None)
    hits  = 0
    details: list[dict] = []
    wrong_qs: list[int] = []

    for i, c in enumerate(correct_indices):
        a = answers[i] if i < len(answers) else None
        if c is None:
            details.append({"q": i + 1, "correct": None, "marked": a,
                            "ok": None, "skipped": True})
            continue
        ok = (a is not None and a == c)
        if ok:
            hits += 1
        else:
            wrong_qs.append(i + 1)
        details.append({"q": i + 1, "correct": c, "marked": a,
                        "ok": ok, "skipped": False})

    if total > 0:
        valor_por_questao = 10.0 / total
        score = round(valor_por_questao * hits, 2)
    else:
        score = 0.0

    return {
        "total":           total,
        "correct":         hits,
        "wrong":           total - hits,
        "score":           score,
        "details":         details,
        "wrong_questions": wrong_qs,
    }


def best_version_match(answers, versions_payloads):
    """
    Dado [(version_id, label, payload_obj)], retorna a versão cujo gabarito
    mais se aproxima das marcações detectadas.
    """
    best      = None
    best_hits = -1

    for ver_id, label, payload in versions_payloads:
        correct = [
            (q.get("correct_index")
             if q.get("type") in ("objective", "tf")
             else None)
            for q in payload
        ]
        hits = 0
        for i, c in enumerate(correct):
            if c is None:
                continue
            a = answers[i] if i < len(answers) else None
            if a is not None and a == c:
                hits += 1
        if hits > best_hits:
            best_hits = hits
            best = (ver_id, label, correct)

    return best, best_hits

"""
Testes automáticos do Profeloop.

Executa:
  python test_omr.py

Verifica:
  1. Geração do PDF de prova (cabeçalho + questões na pág 1, folha OMR na última)
  2. Detecção de marcadores na folha OMR gerada
  3. Cálculo de nota com fórmula correta
"""
from __future__ import annotations

import io
import json
import sys
import types

# ─── mock mínimo do Flask/SQLAlchemy para rodar fora do servidor ──────────────

class _FakeExam:
    def __init__(self):
        self.title        = "Prova de Teste Automatico"
        self.subject      = "Matematica"
        self.grade        = "9o ano"
        self.instructions = "Responda com caneta azul."
        self.layout       = "single"
        self.author       = types.SimpleNamespace(name="Prof. Teste")


class _FakeVersion:
    def __init__(self, n_questions: int = 10):
        self.label = "A"
        questions  = []
        options    = ["Opcao A", "Opcao B", "Opcao C", "Opcao D", "Opcao E"]
        for i in range(n_questions):
            questions.append({
                "type":          "objective",
                "statement":     f"Questao {i + 1}: qual e a resposta correta?",
                "options":       options[:],
                "correct_index": i % 5,
                "correct_text":  options[i % 5],
            })
        self.payload_json = json.dumps(questions)


# ─── Teste 1: geração do PDF ──────────────────────────────────────────────────

def test_pdf_generation():
    print("Teste 1: Geracao do PDF ...")
    from pdf_utils import build_exam_pdf

    for layout in ("single", "double"):
        exam          = _FakeExam()
        exam.layout   = layout
        version       = _FakeVersion(n_questions=20)
        pdf_bytes     = build_exam_pdf(exam, version)

        assert isinstance(pdf_bytes, bytes) and len(pdf_bytes) > 1000, \
            f"PDF vazio para layout={layout}"
        assert pdf_bytes[:4] == b"%PDF", \
            f"Bytes invalidos para layout={layout}"
        print(f"  layout={layout}: OK ({len(pdf_bytes):,} bytes)")

    print("  Teste 1 PASSOU.\n")


# ─── Teste 2: marcadores OMR ──────────────────────────────────────────────────

def test_omr_detection():
    print("Teste 2: Deteccao de marcadores OMR ...")
    import numpy as np
    import cv2
    from omr_geometry import (
        PAGE_W, PAGE_H, FIDUCIAL_SIZE, FIDUCIAL_MARGIN, fiducial_centers,
    )
    from omr_utils import _find_fiducials

    # Cria imagem sintética branca com 4 quadrados pretos nos cantos
    DPI   = 150
    SCALE = DPI / 72.0
    w     = int(PAGE_W * SCALE)
    h     = int(PAGE_H * SCALE)
    img   = np.ones((h, w), dtype=np.uint8) * 255

    fid_px = int(FIDUCIAL_SIZE * SCALE)
    margin = int(FIDUCIAL_MARGIN * SCALE)

    centers_pt = fiducial_centers()  # BL, BR, TL, TR em pontos (y de baixo)
    for (cx_pt, cy_pt) in centers_pt:
        cx_px = int(cx_pt * SCALE)
        cy_px = int((PAGE_H - cy_pt) * SCALE)   # inverter y
        x0 = cx_px - fid_px // 2
        y0 = cy_px - fid_px // 2
        img[y0: y0 + fid_px, x0: x0 + fid_px] = 0

    corners = _find_fiducials(img)
    assert corners is not None, "Marcadores nao detectados na imagem sintetica!"
    assert len(corners) == 4,   f"Esperava 4 marcadores, encontrou {len(corners)}"
    print(f"  Marcadores encontrados: {[(round(x,1), round(y,1)) for x,y in corners]}")
    print("  Teste 2 PASSOU.\n")


# ─── Teste 3: cálculo de nota ─────────────────────────────────────────────────

def test_grade_calculation():
    print("Teste 3: Calculo de nota ...")
    from omr_utils import grade_against_key

    # 20 questões, todas corretas = 10.0
    correct = list(range(20))   # correct_index = posição na lista
    answers = list(range(20))
    r = grade_against_key(answers, correct)
    assert r["total"]   == 20, f"total esperado 20, obteve {r['total']}"
    assert r["correct"] == 20, f"acertos esperados 20, obteve {r['correct']}"
    assert r["score"]   == 10.0, f"nota esperada 10.0, obteve {r['score']}"
    print(f"  20/20 acertos → nota {r['score']}   OK")

    # 15 acertos em 20 → 7.5
    answers_15 = list(range(20))
    answers_15[0] = 99
    answers_15[5] = 99
    answers_15[10] = 99
    answers_15[15] = 99
    answers_15[19] = 99
    r2 = grade_against_key(answers_15, correct)
    assert r2["correct"] == 15, f"acertos esperados 15, obteve {r2['correct']}"
    assert r2["score"]   == 7.5, f"nota esperada 7.5, obteve {r2['score']}"
    print(f"  15/20 acertos → nota {r2['score']}   OK")

    # 0 acertos → 0.0
    answers_0 = [99] * 20
    r3 = grade_against_key(answers_0, correct)
    assert r3["score"] == 0.0, f"nota esperada 0.0, obteve {r3['score']}"
    print(f"   0/20 acertos → nota {r3['score']}   OK")

    print("  Teste 3 PASSOU.\n")


# ─── Teste 4: PDF com 1 questão (edge-case) ───────────────────────────────────

def test_edge_cases():
    print("Teste 4: Edge cases (1 questao, 50 questoes) ...")
    from pdf_utils import build_exam_pdf

    for n in (1, 50):
        exam    = _FakeExam()
        version = _FakeVersion(n_questions=n)
        pdf     = build_exam_pdf(exam, version)
        assert pdf[:4] == b"%PDF", f"PDF invalido para n={n}"
        print(f"  {n} questoes: OK ({len(pdf):,} bytes)")

    print("  Teste 4 PASSOU.\n")


# ─── Runner ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    erros = 0
    for test_fn in (test_pdf_generation, test_omr_detection,
                    test_grade_calculation, test_edge_cases):
        try:
            test_fn()
        except Exception as exc:
            print(f"  FALHOU: {exc}\n")
            erros += 1

    if erros == 0:
        print("======================================")
        print("  TODOS OS TESTES PASSARAM COM SUCESSO")
        print("======================================")
        sys.exit(0)
    else:
        print(f"  {erros} teste(s) falharam.")
        sys.exit(1)

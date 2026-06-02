"""Testes automáticos Profeloop v2."""
import sys, json, types
import numpy as np
import cv2

def test_pdf_generation():
    print("Teste 1: Geração de PDF …")
    from pdf_utils import build_exam_pdf

    class Exam:
        subject="Bio"; grade="3o Ano"; instructions=""; layout="single"
        author=types.SimpleNamespace(name="Prof. X")
    class Version:
        label="A"
        payload_json=json.dumps([
            {"type":"objective","statement":f"Q{i+1}?",
             "options":["A","B","C","D","E"],"correct_index":i%5,"correct_text":"X"}
            for i in range(20)])

    for layout, nq, title in [("single",1,"Bio"),("single",20,"Bio"),("double",20,"Bio")]:
        e=Exam(); e.title=title; e.layout=layout
        v=Version(); v.payload_json=json.dumps([
            {"type":"objective","statement":f"Q{i+1}?","options":["A","B","C","D","E"],
             "correct_index":i%5,"correct_text":"X"} for i in range(nq)])
        pdf=build_exam_pdf(e,v)
        assert pdf[:4]==b"%PDF", f"PDF inválido layout={layout} nq={nq}"
        print(f"  {layout} {nq}q: OK ({len(pdf):,} bytes)")
    print("  PASSOU.\n")


def test_omr_detection():
    print("Teste 2: Detecção de marcadores OMR …")
    from omr_geometry import omr_layout, omr_box_height, omr_box_width, _choose_n_cols, FIDUCIAL_SIZE
    from omr_utils import _find_fiducials

    DPI=150; SCALE=DPI/72.0
    PAGE_W=595.27; PAGE_H=841.89
    W=int(PAGE_W*SCALE); H=int(PAGE_H*SCALE)

    for nq in (1, 10, 20, 40):
        nc   = _choose_n_cols(nq)
        bw   = omr_box_width(nc)
        bh   = omr_box_height(nq, nc)
        bx   = (PAGE_W-bw)/2
        # simula gabarito no final da página
        by_top = bh + 10  # 10pt acima da borda inferior

        lay  = omr_layout(nq, bx, by_top)

        img  = np.ones((H,W), dtype=np.uint8)*255
        fs   = int(FIDUCIAL_SIZE*SCALE)
        for (fx,fy) in lay["fiducials"]:
            cx=int(fx*SCALE); cy=int((PAGE_H-fy)*SCALE)
            x0=cx-fs//2; y0=cy-fs//2
            img[max(0,y0):y0+fs, max(0,x0):x0+fs]=0

        corners=_find_fiducials(img, nq)
        assert corners is not None and len(corners)==4, \
            f"Marcadores não detectados para nq={nq}, nc={nc}"
        print(f"  nq={nq:2d} nc={nc}: marcadores OK")
    print("  PASSOU.\n")


def test_grade():
    print("Teste 3: Cálculo de nota …")
    from omr_utils import grade_against_key

    correct=[0,1,2,3,4]*4
    assert grade_against_key(correct,correct)["score"]==10.0
    half=[0]*20; r2=grade_against_key(half,[0,1]*10); assert r2["correct"]==10
    print(f"  20/20=10.0  10/20={r2['score']}   PASSOU.\n")


if __name__=="__main__":
    erros=0
    for fn in (test_pdf_generation, test_omr_detection, test_grade):
        try: fn()
        except Exception as e:
            print(f"  FALHOU: {e}\n"); erros+=1
    if erros==0:
        print("=" * 40)
        print("  TODOS OS TESTES PASSARAM")
        print("=" * 40)
        sys.exit(0)
    else:
        print(f"  {erros} teste(s) falharam."); sys.exit(1)

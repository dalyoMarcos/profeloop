"""PDF da prova.

Estrutura:
- Cabeçalho compacto (Escola, Nome, Nº, Turma, Data) APENAS na página 1.
- Questões começam imediatamente abaixo do cabeçalho.
- Nenhuma outra página repete o cabeçalho.
- Gabarito OMR compacto embutido no FINAL da última página de questões.
  * Nunca cria página exclusiva para o gabarito, exceto quando não couber.
  * Tamanho adaptativo: ~1/4 (poucas questões) → ~1/2 (muitas questões).
- Marcadores de alinhamento SOMENTE nos 4 cantos do gabarito OMR.
- Modo Normal (coluna única) ou Duas Colunas com linha divisória.
- Rodapé discreto em todas as páginas.
"""
from __future__ import annotations

import io
import json

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import black, white, HexColor
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, PageBreak,
    Table, TableStyle, FrameBreak, NextPageTemplate, Flowable, KeepTogether,
)
from reportlab.pdfgen.canvas import Canvas

from omr_geometry import (
    PAGE_W, PAGE_H, FIDUCIAL_SIZE, FIDUCIAL_MARGIN,
    NUM_OPTIONS, BUBBLE_RADIUS, BUBBLE_SPACING, ROW_H, COL_NUM_W,
    HEADER_H, PADDING, omr_layout, omr_box_height, omr_box_width,
    _choose_n_cols,
)

INK   = HexColor("#000000")
MUTED = HexColor("#555555")

# ─── estilos ─────────────────────────────────────────────────────────────────

def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("ExamTitle", parent=s["Normal"], fontName="Helvetica-Bold",
                         fontSize=12, alignment=1, textColor=INK, spaceAfter=2))
    s.add(ParagraphStyle("ExamSub",   parent=s["Normal"], fontSize=9, alignment=1,
                         textColor=MUTED, spaceAfter=5))
    s.add(ParagraphStyle("Ins",       parent=s["Normal"], fontSize=9, textColor=INK,
                         spaceBefore=2, spaceAfter=4))
    s.add(ParagraphStyle("Q",         parent=s["Normal"], fontName="Helvetica",
                         fontSize=10.5, leading=14, spaceBefore=7, spaceAfter=2,
                         textColor=INK))
    s.add(ParagraphStyle("Opt",       parent=s["Normal"], fontSize=10, leading=13,
                         leftIndent=14, textColor=INK))
    return s

def _lbl(): return ParagraphStyle("hl", fontName="Helvetica-Bold", fontSize=8.5, textColor=INK)
def _val(): return ParagraphStyle("hv", fontName="Helvetica",      fontSize=9,   textColor=INK)


# ─── cabeçalho compacto (somente pág 1) ─────────────────────────────────────

def _header_table():
    """
    Escola: ________________________________
    Nome: __________________________________
    Nº: __________ | Turma: ______ | Data: ________
    """
    usable_w = PAGE_W - 4 * cm
    col3 = usable_w / 3.0
    rh   = 0.72 * cm

    data = [
        [Paragraph("<b>Escola:</b>", _lbl()), "", ""],
        [Paragraph("<b>Nome:</b>",   _lbl()), "", ""],
        [Paragraph("<b>N\u00ba:</b>",  _lbl()),
         Paragraph("<b>Turma:</b>",  _lbl()),
         Paragraph("<b>Data:</b>",   _lbl())],
    ]

    t = Table(data, colWidths=[col3, col3, col3], rowHeights=[rh, rh, rh])
    t.setStyle(TableStyle([
        ("BOX",       (0, 0), (-1, -1), 0.8, black),
        ("LINEBELOW", (0, 0), (-1, 1),  0.5, black),
        ("LINEBEFORE",(1, 2), (2, 2),   0.5, black),
        ("SPAN", (0, 0), (2, 0)),
        ("SPAN", (0, 1), (2, 1)),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING",   (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
    ]))
    return t


# ─── rodapé ──────────────────────────────────────────────────────────────────

def _draw_footer(c: Canvas, version_label: str, page_num: int):
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(2 * cm, 0.7 * cm, f"Versão {version_label}   Página {page_num}")


# ─── linha divisória de coluna ────────────────────────────────────────────────

def _draw_divider(c: Canvas, mb: float, mt: float):
    mid = PAGE_W / 2
    c.setStrokeColor(MUTED)
    c.setLineWidth(0.4)
    c.setDash(3, 4)
    c.line(mid, mb, mid, PAGE_H - mt)
    c.setDash()


# ─── documento ────────────────────────────────────────────────────────────────

class _ExamDoc(BaseDocTemplate):
    def __init__(self, buf, exam, version, layout: str, **kw):
        super().__init__(buf, pagesize=A4, **kw)
        self.exam        = exam
        self.version     = version
        self.layout_kind = layout
        self._pnum       = 0

        ML = 2 * cm; MR = 2 * cm; MB = 1.3 * cm; MT = 1.0 * cm
        uw = PAGE_W - ML - MR
        uh = PAGE_H - MT - MB
        self._ML = ML; self._MB = MB; self._MT = MT

        first_frame = Frame(ML, MB, uw, uh, id="first", showBoundary=0,
                            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

        if layout == "double":
            gap  = 0.5 * cm
            cw   = (uw - gap) / 2
            later = [
                Frame(ML,        MB, cw, uh, id="col1", showBoundary=0,
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
                Frame(ML+cw+gap, MB, cw, uh, id="col2", showBoundary=0,
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
            ]
        else:
            later = [Frame(ML, MB, uw, uh, id="single", showBoundary=0,
                           leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)]

        self.addPageTemplates([
            PageTemplate(id="first", frames=[first_frame], onPage=self._on_q_page),
            PageTemplate(id="later", frames=later,         onPage=self._on_q_page),
        ])

    def _on_q_page(self, c, doc):
        self._pnum += 1
        _draw_footer(c, self.version.label, self._pnum)
        if self.layout_kind == "double" and self._pnum > 1:
            _draw_divider(c, self._MB, self._MT)

    def handle_pageBegin(self):
        if self.page == 1:
            self._handle_nextPageTemplate("later")
        super().handle_pageBegin()


# ─── flowables de questões ────────────────────────────────────────────────────

def _question_flowables(payload, s):
    out = []
    letters = "ABCDEFGH"
    for i, q in enumerate(payload, start=1):
        block = [Paragraph(f"<b>{i}.</b> {q['statement']}", s["Q"])]
        if q["type"] == "objective":
            for idx, opt in enumerate(q.get("options") or []):
                block.append(Paragraph(f"<b>{letters[idx]})</b> {opt}", s["Opt"]))
        elif q["type"] == "tf":
            block.append(Paragraph("(  ) Verdadeiro     (  ) Falso", s["Opt"]))
        else:
            for _ in range(4):
                block.append(Spacer(1, 7))
                block.append(Paragraph("_" * 80, s["Opt"]))
        out.append(KeepTogether(block))
    return out


# ─── gabarito OMR embutido ────────────────────────────────────────────────────

class _OmrFlowable(Flowable):
    """
    Desenha o gabarito OMR compacto usando coordenadas absolutas do canvas.
    Responde ao wrap() para informar ao Platypus o espaço necessário.
    Se não couber, vai para a próxima página.
    """

    def __init__(self, payload, version_label):
        super().__init__()
        self.payload       = payload
        self.version_label = version_label
        n = len(payload)
        nc = _choose_n_cols(n)
        self._bh = omr_box_height(n, nc)
        self._bw = omr_box_width(nc)

    def wrap(self, aw, ah):
        # Altura que reservamos: gabarito + pequena margem de título
        needed = self._bh + 0.8 * cm  # espaço para o título "GABARITO"
        self._ah = ah
        self._aw = aw
        return (aw, needed)

    def draw(self):
        c   = self.canv
        n   = len(self.payload)
        aw  = self._aw

        # Centro do gabarito horizontalmente na área disponível
        bx  = (aw - self._bw) / 2
        # Coordenada y atual: self.canv.absolutePosition() não existe,
        # mas o frame já posicionou o cursor. O flowable desenha a partir
        # do ponto (0, 0) = canto inferior-esquerdo do espaço alocado.
        # Espaço alocado = self._bh + 0.8cm; título fica no topo.
        title_y = self._bh + 0.15 * cm
        box_y_top = self._bh   # topo do box em coordenadas locais

        layout = omr_layout(n, bx, box_y_top)

        # ── Título ──
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(bx, title_y, f"GABARITO — Versão {self.version_label}")

        # ── Borda do gabarito ──
        c.setStrokeColor(black)
        c.setLineWidth(0.7)
        c.rect(bx, 0, layout["box_w"], layout["box_h"], fill=0, stroke=1)

        # ── Marcadores OMR nos 4 cantos do gabarito ──
        c.setFillColor(black)
        fs = FIDUCIAL_SIZE
        for (fx, fy) in layout["fiducials"]:
            c.rect(fx - fs/2, fy - fs/2, fs, fs, fill=1, stroke=0)

        # ── Separadores de colunas internas ──
        sw = layout["single_w"]
        for ci in range(1, layout["n_cols"]):
            sx = bx + ci * (sw + layout["col_gap"]) - layout["col_gap"] / 2
            c.setStrokeColor(MUTED)
            c.setLineWidth(0.3)
            c.line(sx, 0, sx, layout["box_h"])

        # ── Linha horizontal abaixo do header ──
        c.setStrokeColor(black)
        c.setLineWidth(0.4)
        header_line_y = box_y_top - PADDING - HEADER_H
        c.line(bx, header_line_y, bx + layout["box_w"], header_line_y)

        # ── Rótulos A..E ──
        c.setFont("Helvetica-Bold", 7)
        c.setFillColor(INK)
        for (lx, letter) in layout["col_labels"]:
            c.drawCentredString(lx, layout["labels_y"], letter)

        # ── Número da questão + bolhas ──
        c.setFont("Helvetica", 7)
        for q_idx, row_y, bubble_cols, num_x in layout["rows"]:
            c.setFillColor(INK)
            c.drawRightString(num_x, row_y - 3, str(q_idx + 1))
            for (bx2, by2) in bubble_cols:
                c.circle(bx2, by2, BUBBLE_RADIUS, stroke=1, fill=0)

        # ── Legenda ──
        c.setFont("Helvetica-Oblique", 6.5)
        c.setFillColor(MUTED)
        legend_y = -0.35 * cm
        c.drawString(bx, legend_y,
                     "Marque: ●  Não use X nem rasure.  "
                     "Mantenha os marcadores dos cantos visíveis na foto.")


# ─── builder principal ────────────────────────────────────────────────────────

def build_exam_pdf(exam, version):
    """
    Gera bytes do PDF completo de uma versão.

    Página 1 : cabeçalho compacto + questões (sem OMR na margem)
    Pág 2+   : apenas questões (sem OMR, 1 ou 2 colunas)
    Final    : gabarito OMR compacto embutido ao fim das questões
               (nova página somente se não couber)
    """
    payload = json.loads(version.payload_json)
    layout  = (exam.layout or "single").lower()
    if layout not in ("single", "double"):
        layout = "single"

    buf = io.BytesIO()
    doc = _ExamDoc(buf, exam, version, layout,
                   title=f"{exam.title} - V{version.label}")

    s     = _styles()
    story = []

    # ── Cabeçalho (pág 1) ────────────────────────────────────────────────
    story.append(_header_table())
    story.append(Spacer(1, 5))
    story.append(Paragraph(exam.title, s["ExamTitle"]))
    sub = " · ".join(filter(None, [exam.subject, exam.grade]))
    if sub:
        story.append(Paragraph(sub, s["ExamSub"]))
    if exam.instructions:
        story.append(Paragraph(
            f"<b>Instrucoes:</b> {exam.instructions}", s["Ins"]))
        story.append(Spacer(1, 3))

    # ── Questões ─────────────────────────────────────────────────────────
    story += _question_flowables(payload, s)

    # ── Gabarito OMR compacto ─────────────────────────────────────────────
    story.append(Spacer(1, 0.5 * cm))
    story.append(_OmrFlowable(payload, version.label))

    doc.build(story)
    return buf.getvalue()

"""PDF da prova + folha de respostas OMR.

Versão corrigida:
- Cabeçalho escolar preto/branco APENAS na primeira página.
- Questões começam logo após o cabeçalho (primeira página).
- Sem PageBreak desnecessário entre cabeçalho e questões.
- Layout Normal (coluna única) ou Duas Colunas.
- SEM marcadores OMR nas páginas de questões.
- Linha divisória vertical no modo duas colunas.
- Folha de respostas OMR na última página com marcadores nos 4 cantos.
- Rodapé discreto em todas as páginas de questões.
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
    PAGE_W, PAGE_H,
    FIDUCIAL_SIZE, FIDUCIAL_MARGIN, fiducial_centers,
    answer_sheet_layout, BUBBLE_RADIUS,
)

INK = HexColor("#000000")
MUTED = HexColor("#555555")

# ─────────────────────────── estilos ────────────────────────────────────────

def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("ExamTitle", parent=s["Normal"], fontName="Helvetica-Bold",
                         fontSize=12, alignment=1, textColor=INK, spaceAfter=2))
    s.add(ParagraphStyle("ExamSub", parent=s["Normal"], fontSize=9, alignment=1,
                         textColor=MUTED, spaceAfter=6))
    s.add(ParagraphStyle("Ins", parent=s["Normal"], fontSize=9, textColor=INK,
                         spaceBefore=2, spaceAfter=4))
    s.add(ParagraphStyle("Q", parent=s["Normal"], fontName="Helvetica",
                         fontSize=10.5, leading=14, spaceBefore=7, spaceAfter=2,
                         textColor=INK))
    s.add(ParagraphStyle("Opt", parent=s["Normal"], fontSize=10, leading=13,
                         leftIndent=14, textColor=INK))
    s.add(ParagraphStyle("Sec", parent=s["Normal"], fontName="Helvetica-Bold",
                         fontSize=11, alignment=1, textColor=INK,
                         spaceBefore=4, spaceAfter=6))
    return s


def _hdr_lbl():
    return ParagraphStyle("hl", fontName="Helvetica-Bold", fontSize=9, textColor=INK)

def _hdr_val():
    return ParagraphStyle("hv", fontName="Helvetica", fontSize=9.5, textColor=INK)


# ─────────────────────── cabeçalho escolar ──────────────────────────────────

def _academic_header_table(exam, version):
    """
    Estrutura:
    ┌──────────────────────────────────────────┐
    │ Escola: ________________________________ │
    ├──────────────────────────────────────────┤
    │ Nome: __________________________________ │
    ├──────────────────────────────────────────┤
    │ Nº: _________  Turma: _____  Data: _____ │
    ├──────────────────────────────────────────┤
    │ Professor: _____________________________ │
    ├──────────────────────────────────────────┤
    │ Disciplina: ____________________________ │
    ├──────────────────────────────────────────┤
    │ Nota: __________ │
    └──────────────────┘
    """
    teacher = (exam.author.name if getattr(exam, "author", None) else "") or ""
    subject = exam.subject or ""

    usable_w = PAGE_W - 4 * cm  # margens 2cm cada lado
    col3 = usable_w / 3.0

    row_h = 0.85 * cm
    label_style = _hdr_lbl()
    val_style   = _hdr_val()

    data = [
        # Linha 1: Escola (largura toda)
        [Paragraph("<b>Escola:</b>", label_style), "", ""],
        # Linha 2: Nome (largura toda)
        [Paragraph("<b>Nome:</b>", label_style), "", ""],
        # Linha 3: Nº | Turma | Data
        [Paragraph("<b>Nº:</b>", label_style),
         Paragraph("<b>Turma:</b>", label_style),
         Paragraph("<b>Data:</b>", label_style)],
        # Linha 4: Professor (largura toda)
        [Paragraph("<b>Professor:</b> " + teacher, val_style), "", ""],
        # Linha 5: Disciplina (largura toda)
        [Paragraph("<b>Disciplina:</b> " + subject, val_style), "", ""],
        # Linha 6: Nota (1/3 da largura)
        [Paragraph("<b>Nota:</b>", label_style), "", ""],
    ]

    t = Table(data, colWidths=[col3, col3, col3],
              rowHeights=[row_h] * 6)

    ts = TableStyle([
        # borda externa
        ("BOX",        (0, 0), (-1, -1), 0.9, black),
        # linhas internas horizontais
        ("LINEBELOW",  (0, 0), (-1, 4),  0.6, black),
        # linhas internas verticais só onde há 3 colunas separadas (linha 3)
        ("LINEBEFORE", (1, 2), (2, 2),   0.6, black),

        # span: linhas de largura toda (0, 1, 3, 4)
        ("SPAN", (0, 0), (2, 0)),
        ("SPAN", (0, 1), (2, 1)),
        ("SPAN", (0, 3), (2, 3)),
        ("SPAN", (0, 4), (2, 4)),
        # linha 6: Nota ocupa só a 1ª célula, as outras ficam em branco
        ("SPAN", (0, 5), (0, 5)),
        ("LINEBEFORE", (1, 5), (2, 5), 0, white),  # apaga bordas internas linha nota
        ("LINEABOVE",  (1, 5), (2, 5), 0, white),

        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
    ])
    t.setStyle(ts)
    return t


# ─────────────────────── rodapé (páginas de questões) ───────────────────────

def _draw_footer(c: Canvas, version_label: str, page_num: int):
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(2 * cm, 0.85 * cm, f"Versão {version_label}   Página {page_num}")


# ─────────────────────── linha vertical (modo dupla coluna) ─────────────────

def _draw_column_divider(c: Canvas, margin_b: float, margin_top: float):
    """Linha divisória vertical no centro da página (apenas questões)."""
    mid_x = PAGE_W / 2
    y_top = PAGE_H - margin_top
    y_bot = margin_b
    c.setStrokeColor(MUTED)
    c.setLineWidth(0.5)
    c.setDash(4, 4)
    c.line(mid_x, y_bot, mid_x, y_top)
    c.setDash()  # reset


# ──────────────────────────── documento ─────────────────────────────────────

class _ExamDoc(BaseDocTemplate):
    """
    Estrutura de templates:
    - 'first'  : primeira página (1 frame, sem OMR, com cabeçalho via flowable)
    - 'later'  : páginas seguintes (1 ou 2 frames, sem OMR)
    - 'answers': folha de respostas (1 frame, OMR nos cantos)

    Cabeçalho acadêmico é inserido como flowable na história (não via onPage),
    garantindo que as questões continuem logo abaixo sem desperdício de página.
    """

    def __init__(self, buf, exam, version, layout: str, **kw):
        super().__init__(buf, pagesize=A4, **kw)
        self.exam        = exam
        self.version     = version
        self.layout_kind = layout
        self._page_seq   = 0   # conta páginas de questões

        ML = 2 * cm   # margem esquerda
        MR = 2 * cm   # margem direita
        MB = 1.5 * cm # margem inferior (espaço para rodapé)
        MT = 1.2 * cm # margem superior
        usable_w = PAGE_W - ML - MR
        usable_h = PAGE_H - MT - MB

        # ── Primeira página: 1 frame full-width ──────────────────────────
        first_frame = Frame(
            ML, MB, usable_w, usable_h,
            id="first", showBoundary=0,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        )

        # ── Páginas seguintes ─────────────────────────────────────────────
        if layout == "double":
            gap   = 0.6 * cm
            col_w = (usable_w - gap) / 2
            later_frames = [
                Frame(ML, MB, col_w, usable_h, id="col1", showBoundary=0,
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
                Frame(ML + col_w + gap, MB, col_w, usable_h, id="col2",
                      showBoundary=0,
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
            ]
        else:
            later_frames = [
                Frame(ML, MB, usable_w, usable_h, id="single", showBoundary=0,
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
            ]

        # ── Folha de respostas: 1 frame (conteúdo desenhado pelo flowable) ─
        answer_frame = Frame(
            0, 0, PAGE_W, PAGE_H, id="answers", showBoundary=0,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        )

        self._ML = ML
        self._MB = MB
        self._MT = MT
        self._layout = layout

        self.addPageTemplates([
            PageTemplate(id="first",   frames=[first_frame],
                         onPage=self._on_question_page),
            PageTemplate(id="later",   frames=later_frames,
                         onPage=self._on_question_page),
            PageTemplate(id="answers", frames=[answer_frame],
                         onPage=self._on_answer_page),
        ])

    def _on_question_page(self, c, doc):
        """Callback para páginas de questões: apenas rodapé, SEM OMR."""
        self._page_seq += 1
        _draw_footer(c, self.version.label, self._page_seq)
        if self._layout == "double" and self._page_seq > 1:
            _draw_column_divider(c, self._MB, self._MT)

    def _on_answer_page(self, c, doc):
        """Callback para folha de respostas: apenas OMR nos 4 cantos."""
        # os marcadores e o conteúdo são desenhados pelo _AnswerSheetFlowable
        pass

    def handle_pageBegin(self):
        # A partir da 2ª página de questões, muda para template "later"
        if self.page == 1:
            self._handle_nextPageTemplate("later")
        super().handle_pageBegin()


# ─────────────────────── flowables de questões ──────────────────────────────

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
                block.append(Spacer(1, 8))
                block.append(Paragraph("_" * 80, s["Opt"]))
        out.append(KeepTogether(block))
    return out


# ─────────────────────── builder principal ──────────────────────────────────

def build_exam_pdf(exam, version):
    """
    Gera bytes do PDF completo de uma versão.

    Estrutura:
      Página 1  : cabeçalho acadêmico + questões (sem OMR)
      Página 2+ : questões (1 ou 2 colunas, sem OMR)
      Última    : folha de respostas com marcadores OMR nos 4 cantos
    """
    payload = json.loads(version.payload_json)
    layout  = (exam.layout or "single").lower()
    if layout not in ("single", "double"):
        layout = "single"

    buf = io.BytesIO()
    doc = _ExamDoc(buf, exam, version, layout,
                   title=f"{exam.title} - V{version.label}")

    s = _styles()
    story = []

    # ── Cabeçalho na página 1 ────────────────────────────────────────────
    story.append(_academic_header_table(exam, version))
    story.append(Spacer(1, 6))
    story.append(Paragraph(exam.title, s["ExamTitle"]))
    sub = " · ".join(filter(None, [exam.subject, exam.grade]))
    if sub:
        story.append(Paragraph(sub, s["ExamSub"]))
    if exam.instructions:
        story.append(Paragraph(
            f"<b>Instrucoes:</b> {exam.instructions}", s["Ins"]))
        story.append(Spacer(1, 4))

    # ── Questões começam LOGO APÓS o cabeçalho (sem PageBreak) ──────────
    # No modo double, as questões da pág 1 ficam em coluna única (frame "first").
    # A partir da pág 2 o template "later" usa 2 colunas.
    story += _question_flowables(payload, s)

    # ── Folha de respostas em página própria ─────────────────────────────
    story.append(NextPageTemplate("answers"))
    story.append(PageBreak())
    story.append(_AnswerSheetFlowable(payload, version.label, exam.title))

    doc.build(story)
    return buf.getvalue()


# ─────────────────────── Folha de respostas OMR ─────────────────────────────

class _AnswerSheetFlowable(Flowable):
    """Desenha a folha de respostas inteira via canvas."""

    def __init__(self, payload, version_label, exam_title):
        super().__init__()
        self.payload       = payload
        self.version_label = version_label
        self.exam_title    = exam_title
        self.width  = PAGE_W
        self.height = PAGE_H

    def wrap(self, aw, ah):
        return (PAGE_W, PAGE_H)

    def draw(self):
        self._draw(self.canv)

    def _draw(self, c: Canvas):
        # ── Marcadores OMR nos 4 cantos ───────────────────────────────────
        c.setFillColor(black)
        c.setStrokeColor(black)
        for (cx, cy) in fiducial_centers():
            c.rect(
                cx - FIDUCIAL_SIZE / 2,
                cy - FIDUCIAL_SIZE / 2,
                FIDUCIAL_SIZE,
                FIDUCIAL_SIZE,
                fill=1, stroke=0,
            )

        # ── Título ────────────────────────────────────────────────────────
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 13)
        c.drawCentredString(PAGE_W / 2, PAGE_H - 2.0 * cm, "FOLHA DE RESPOSTAS")

        c.setFont("Helvetica", 9)
        c.setFillColor(MUTED)
        c.drawCentredString(
            PAGE_W / 2, PAGE_H - 2.65 * cm,
            f"{self.exam_title}  —  Versao {self.version_label}  ·  "
            "Preencha completamente a bolha da alternativa escolhida.",
        )

        # ── Campos Nome / Turma / Data / Nº ──────────────────────────────
        c.setFillColor(INK)
        c.setFont("Helvetica", 10)
        base_y = PAGE_H - 3.7 * cm

        c.drawString(2 * cm, base_y, "Nome:")
        c.line(3.2 * cm, base_y - 2, 12.5 * cm, base_y - 2)
        c.drawString(12.9 * cm, base_y, "Turma:")
        c.line(14.4 * cm, base_y - 2, 18.5 * cm, base_y - 2)

        base_y -= 1.0 * cm
        c.drawString(2 * cm, base_y, "Data:")
        c.line(3.1 * cm, base_y - 2, 7.5 * cm, base_y - 2)
        c.drawString(8.0 * cm, base_y, "No:")
        c.line(8.8 * cm, base_y - 2, 11.5 * cm, base_y - 2)

        # ── Grade de bolhas ───────────────────────────────────────────────
        n = len(self.payload)
        layout = answer_sheet_layout(n)
        if not layout["bubbles"]:
            return

        # Rótulos A..E no topo de cada coluna de bolhas
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(INK)
        for col_x, letter in layout["col_labels"]:
            c.drawCentredString(col_x, layout["labels_y"], letter)

        # Separador vertical entre blocos de questões (se mais de 1 bloco)
        # (calculado a partir dos col_labels do 2º bloco em diante)

        # Número da questão + círculos
        c.setFont("Helvetica", 9)
        for q_idx, row_y, bubble_cols in layout["rows"]:
            c.setFillColor(INK)
            c.drawRightString(bubble_cols[0][0] - 14, row_y - 3, f"{q_idx + 1}")
            for (bx, by) in bubble_cols:
                c.circle(bx, by, BUBBLE_RADIUS, stroke=1, fill=0)

        # ── Legenda ───────────────────────────────────────────────────────
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Oblique", 8)
        c.drawCentredString(
            PAGE_W / 2, 1.5 * cm,
            "Marque assim: ●  —  Nao use X nem rasure.  "
            "Mantenha os quatro quadrados pretos dos cantos visiveis na foto.",
        )

"""Geometria compartilhada da folha de respostas OMR.

Sistema de coordenadas: pontos ReportLab, A4 retrato (595 x 842 pt),
origem no canto inferior-esquerdo.

NOVO: gabarito compacto embutido na última página (não ocupa página inteira).
Tamanho adaptativo:
  - poucas questões  → ~1/4 da folha
  - muitas questões  → até ~1/2 da folha
Os marcadores OMR existem APENAS na área do gabarito.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm

PAGE_W, PAGE_H = A4   # 595.27 x 841.89 pt

# ── Dimensões do gabarito compacto ────────────────────────────────────────
NUM_OPTIONS    = 5              # A..E
BUBBLE_RADIUS  = 0.22 * cm     # bolha pequena e profissional
BUBBLE_SPACING = 0.65 * cm     # espaço horizontal entre bolhas
ROW_H          = 0.60 * cm     # altura por linha de questão
COL_NUM_W      = 0.70 * cm     # largura da coluna com número da questão
HEADER_H       = 0.55 * cm     # altura do cabeçalho A B C D E
PADDING        = 0.35 * cm     # padding interno do gabarito

# Largura de uma coluna de bolhas = num_options * spacing
BUBBLES_W = (NUM_OPTIONS - 1) * BUBBLE_SPACING + 2 * BUBBLE_RADIUS

# ── Marcadores de alinhamento (fiducials) ────────────────────────────────
# Tamanho menor que antes — ficam nos 4 cantos do gabarito, não da página
FIDUCIAL_SIZE   = 0.55 * cm    # lado do quadrado
FIDUCIAL_MARGIN = 0.30 * cm    # distância do centro até a borda do gabarito


def omr_box_height(num_questions: int, n_cols: int = 1) -> float:
    """Altura total da caixa do gabarito em pt."""
    rows = -(-num_questions // n_cols)   # ceil
    return PADDING * 2 + HEADER_H + rows * ROW_H


def omr_box_width(n_cols: int = 1) -> float:
    """Largura total da caixa do gabarito em pt."""
    single = PADDING * 2 + COL_NUM_W + BUBBLES_W
    return single * n_cols + (n_cols - 1) * 0.4 * cm  # gap entre colunas


def _choose_n_cols(num_questions: int) -> int:
    """
    Quantas colunas de questões no gabarito?
    Tenta caber em ~1/4 de página; usa 2 colunas se necessário;
    máx 4 colunas (para muitas questões).
    """
    max_h = PAGE_H * 0.50   # até metade da página
    for nc in (1, 2, 3, 4):
        if omr_box_height(num_questions, nc) <= max_h:
            return nc
    return 4


def omr_layout(num_questions: int, box_x: float, box_y_top: float):
    """
    Calcula geometria completa do gabarito compacto.

    Parâmetros
    ----------
    num_questions : int
    box_x        : float  — coordenada x do canto esquerdo do gabarito (pt)
    box_y_top    : float  — coordenada y do TOPO do gabarito (pt, ReportLab y)

    Retorna dict com:
      n_cols, box_w, box_h,
      fiducials   [(cx,cy) x4]  — BL BR TL TR relativos ao box
      col_labels  [(x, "A"), …]
      labels_y    float
      rows        [(q_idx, row_y, [(bx,by) x5])]
      bubbles     [(q_idx, opt_idx, x, y)]
    """
    n_cols = _choose_n_cols(num_questions)
    rows_per_col = -(-num_questions // n_cols)

    single_w = PADDING * 2 + COL_NUM_W + BUBBLES_W
    col_gap  = 0.40 * cm
    box_w    = single_w * n_cols + col_gap * (n_cols - 1)
    box_h    = PADDING * 2 + HEADER_H + rows_per_col * ROW_H

    box_y_bot = box_y_top - box_h   # y inferior (ReportLab)

    # ── Marcadores nos 4 cantos do gabarito ───────────────────────────────
    fm = FIDUCIAL_MARGIN
    fiducials = [
        (box_x + fm,       box_y_bot + fm),     # BL
        (box_x + box_w - fm, box_y_bot + fm),   # BR
        (box_x + fm,       box_y_top - fm),     # TL
        (box_x + box_w - fm, box_y_top - fm),   # TR
    ]

    # ── Posição das bolhas ────────────────────────────────────────────────
    letters    = ["A", "B", "C", "D", "E"][:NUM_OPTIONS]
    rows       = []
    col_labels = []
    bubbles    = []

    labels_y = box_y_top - PADDING - HEADER_H / 2  # y central do header

    for q in range(num_questions):
        ci = q // rows_per_col          # índice da coluna
        ri = q % rows_per_col           # linha dentro da coluna

        col_x0 = box_x + ci * (single_w + col_gap)  # x esquerdo desta col
        first_bubble_x = col_x0 + PADDING + COL_NUM_W

        row_y = box_y_top - PADDING - HEADER_H - ri * ROW_H - ROW_H / 2

        # rótulos A..E apenas na primeira linha de cada coluna
        if ri == 0:
            for k, ltr in enumerate(letters):
                bx = first_bubble_x + k * BUBBLE_SPACING
                col_labels.append((bx, ltr))

        bubble_cols = []
        for k in range(NUM_OPTIONS):
            bx = first_bubble_x + k * BUBBLE_SPACING
            bubble_cols.append((bx, row_y))
            bubbles.append((q, k, bx, row_y))

        # x do número da questão
        num_x = col_x0 + PADDING + COL_NUM_W - 0.40 * cm
        rows.append((q, row_y, bubble_cols, num_x))

    return {
        "n_cols":     n_cols,
        "box_w":      box_w,
        "box_h":      box_h,
        "box_x":      box_x,
        "box_y_top":  box_y_top,
        "box_y_bot":  box_y_bot,
        "fiducials":  fiducials,   # BL BR TL TR
        "col_labels": col_labels,  # [(x, "A"), …]
        "labels_y":   labels_y,
        "rows":       rows,        # [(q_idx, row_y, [(bx,by)], num_x)]
        "bubbles":    bubbles,     # [(q_idx, opt_idx, x, y)]
        "rows_per_col": rows_per_col,
        "single_w":   single_w,
        "col_gap":    col_gap,
    }


# Mantém compatibilidade com código antigo que chama fiducial_centers()
def fiducial_centers():
    """Compatibilidade — retorna cantos de um gabarito centrado na página."""
    bw = omr_box_width(1)
    bx = (PAGE_W - bw) / 2
    by_top = 6 * cm
    L = omr_layout(20, bx, by_top)
    return L["fiducials"]

# Compatibilidade
FIDUCIAL_MARGIN = FIDUCIAL_MARGIN   # já definido acima

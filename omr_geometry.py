"""Geometria compartilhada da folha de respostas OMR.

Tanto a geração do PDF (pdf_utils.py) quanto o detector (omr_utils.py)
usam estas constantes/funções, de modo que as bolhas desenhadas no PDF
ficam exatamente nas coordenadas amostradas pelo detector após o
alinhamento por homografia usando os quatro marcadores de canto.

Sistema de coordenadas: pontos do ReportLab, A4 retrato (595 x 842 pt),
origem no canto inferior-esquerdo.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm

PAGE_W, PAGE_H = A4  # 595.27 x 841.89

# --- marcadores OMR (quadrados pretos) ---------------------------------
FIDUCIAL_SIZE = 0.9 * cm        # lado do quadrado
FIDUCIAL_MARGIN = 1.1 * cm      # distância do centro até a borda da folha


def fiducial_centers():
    """Centros dos 4 marcadores: (BL, BR, TL, TR) em pontos."""
    m = FIDUCIAL_MARGIN
    return [
        (m, m),                     # bottom-left
        (PAGE_W - m, m),            # bottom-right
        (m, PAGE_H - m),            # top-left
        (PAGE_W - m, PAGE_H - m),   # top-right
    ]


# --- folha de respostas ------------------------------------------------
NUM_OPTIONS = 5                 # A..E
BUBBLE_RADIUS = 0.32 * cm       # ~9 pt → bolha grande
BUBBLE_SPACING_X = 0.95 * cm    # distância horizontal entre bolhas
ROW_SPACING = 0.85 * cm         # distância vertical entre linhas


def answer_sheet_layout(num_questions: int):
    """Calcula as coordenadas absolutas (em pt) das bolhas, rótulos
    A..E e número de cada questão, para `num_questions` questões.

    A folha é dividida automaticamente em até 4 blocos lado a lado,
    com no máximo `max_rows_per_block` questões por bloco.
    """
    margin_top = 6.2 * cm        # espaço para título + cabeçalho da folha
    margin_bottom = 2.5 * cm     # espaço para rodapé + legenda
    available_h = PAGE_H - margin_top - margin_bottom
    max_rows = int(available_h // ROW_SPACING)

    # Define quantos blocos (colunas de questões na folha) precisamos
    n_blocks = 1
    while n_blocks * max_rows < num_questions and n_blocks < 4:
        n_blocks += 1
    rows_per_block = -(-num_questions // n_blocks)  # ceil
    rows_per_block = min(rows_per_block, max_rows)

    # Largura de cada bloco: número da questão + 5 bolhas + espaço
    block_w = (NUM_OPTIONS - 1) * BUBBLE_SPACING_X + 2.4 * cm
    total_w = block_w * n_blocks
    start_x = (PAGE_W - total_w) / 2

    top_y = PAGE_H - margin_top  # y do topo das linhas de bolhas
    labels_y = top_y + 0.55 * cm

    rows = []
    col_labels = []

    # rótulos A..E são iguais em todos os blocos — guardamos por bloco
    letters = ["A", "B", "C", "D", "E"][:NUM_OPTIONS]

    for q in range(num_questions):
        block_idx = q // rows_per_block
        row_in_block = q % rows_per_block

        block_left = start_x + block_idx * block_w
        # primeira bolha começa após o número da questão
        first_bubble_x = block_left + 1.6 * cm
        row_y = top_y - row_in_block * ROW_SPACING

        bubble_cols = []
        for k in range(NUM_OPTIONS):
            bx = first_bubble_x + k * BUBBLE_SPACING_X
            by = row_y
            bubble_cols.append((bx, by))
            # registra rótulos apenas para a primeira linha de cada bloco
            if row_in_block == 0:
                col_labels.append((bx, letters[k]))
        rows.append((q, row_y, bubble_cols))

    # achata a lista de bolhas para detecção (índice → (x,y))
    bubbles = []  # [(q_idx, opt_idx, x, y)]
    for q_idx, _y, cols in rows:
        for opt_idx, (bx, by) in enumerate(cols):
            bubbles.append((q_idx, opt_idx, bx, by))

    return {
        "rows": rows,                # [(q_idx, row_y, [(x,y) x5])]
        "bubbles": bubbles,          # [(q_idx, opt_idx, x, y)]
        "col_labels": col_labels,    # [(x, "A"), ...] (apenas linhas-topo de cada bloco)
        "labels_y": labels_y,
        "num_options": NUM_OPTIONS,
    }

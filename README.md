# ProfeLoop

**Ensinar, compartilhar e evoluir — em um ciclo contínuo.**

MVP completo da plataforma educacional ProfeLoop, construído com HTML + CSS + JavaScript puro no frontend e Python (Flask) no backend.

## Recursos

- Landing page moderna estilo SaaS
- Autenticação de professores (cadastro / login)
- Dashboard com sidebar, cards e gráficos
- **Biblioteca de Conteúdos** colaborativa (upload, busca, filtros, curtir, favoritar, comentar, avaliar, baixar)
- **Criação de Provas** (objetivas, V/F, subjetivas, alternativas dinâmicas)
- **Geração de versões embaralhadas** (A, B, C…) com respostas mantidas
- **PDF profissional** da prova pronto para impressão (ReportLab)
- **Gabarito OMR** com QR Code único (ID + versão + respostas corretas)
- **Correção automática via câmera** (escanear QR + detecção das bolhas marcadas com OpenCV)
- **Relatórios** (acertos, erros, questões mais erradas, gráficos)
- **Banco de Provas** (editar, duplicar, reutilizar)

## Como rodar

```bash
# 1. Criar ambiente virtual
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Instalar dependências
pip install -r requirements.txt

# Para o scanner OMR (correção via câmera) instale também os binários do zbar:
#   macOS:    brew install zbar
#   Ubuntu:   sudo apt-get install libzbar0
#   Windows:  já vem com pyzbar

# 3. Rodar
python app.py
```

Acesse http://localhost:5000

Um usuário demo é criado automaticamente:
- e-mail: `demo@profeloop.com`
- senha: `demo1234`

## Estrutura

```
profeloop/
├── app.py                  # Aplicação Flask (rotas + API)
├── models.py               # SQLAlchemy: User, Content, Exam, Version, Attempt...
├── pdf_utils.py            # Geração de PDF da prova + gabarito OMR + QR
├── omr_utils.py            # Leitura de QR e detecção de bolhas (OpenCV)
├── requirements.txt
├── instance/profeloop.db   # SQLite (gerado em runtime)
├── static/
│   ├── css/styles.css
│   ├── js/                 # JS puro por página
│   └── uploads/            # arquivos da biblioteca
└── templates/              # Jinja2 (HTML puro)
```

## Stack

- **Frontend:** HTML5 semântico, CSS3 (variáveis, grid, flexbox, animações), JavaScript ES6 vanilla, Chart.js via CDN
- **Backend:** Python 3.10+, Flask, SQLAlchemy, ReportLab, qrcode, OpenCV, pyzbar
- **Banco:** SQLite (zero configuração)

Nenhum framework JS (sem React/Vue/Angular). Sem TypeScript.

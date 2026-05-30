import os, json, random, io
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for, jsonify,
    send_from_directory, send_file, flash, abort
)
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from werkzeug.utils import secure_filename
from sqlalchemy import or_, func

from models import (
    db, User, Content, Like, Favorite, Comment, Rating,
    Exam, ExamVersion, Attempt,
)
from pdf_utils import build_exam_pdf
from omr_utils import detect_answers, grade_against_key, best_version_match

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE, "instance"), exist_ok=True)

app = Flask(__name__, instance_relative_config=True)
app.config.update(
    SECRET_KEY=os.environ.get("PROFELOOP_SECRET", "dev-secret-change-me"),
    SQLALCHEMY_DATABASE_URI="sqlite:///" + os.path.join(BASE, "instance", "profeloop.db"),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=64 * 1024 * 1024,  # 64MB
)

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(uid):
    return db.session.get(User, int(uid))


ALLOWED = {"pdf", "png", "jpg", "jpeg", "gif", "webp", "mp4", "webm", "mov",
           "ppt", "pptx", "doc", "docx", "odt", "odp", "txt", "md", "zip"}
KINDS = ["Slide", "PDF", "Mapa mental", "Vídeo", "Imagem", "Plano de aula",
         "Exercícios", "Resumo"]
SUBJECTS = ["Matemática", "Português", "História", "Geografia", "Biologia",
            "Física", "Química", "Inglês", "Filosofia", "Sociologia", "Artes",
            "Ed. Física", "Outro"]
GRADES = ["6º ano", "7º ano", "8º ano", "9º ano",
          "1ª série EM", "2ª série EM", "3ª série EM", "Outro"]


def allowed_file(name):
    return "." in name and name.rsplit(".", 1)[1].lower() in ALLOWED


# ---------- Public ---------- #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        u = User.query.filter_by(email=email).first()
        if u and u.check_password(password):
            login_user(u, remember=True)
            return redirect(url_for("dashboard"))
        flash("E-mail ou senha inválidos.", "error")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not (name and email and len(password) >= 6):
            flash("Preencha todos os campos (senha com 6+ caracteres).", "error")
            return render_template("register.html")
        if User.query.filter_by(email=email).first():
            flash("E-mail já cadastrado.", "error")
            return render_template("register.html")
        u = User(name=name, email=email, school=request.form.get("school"),
                 subject=request.form.get("subject"))
        u.set_password(password)
        db.session.add(u); db.session.commit()
        login_user(u)
        return redirect(url_for("dashboard"))
    return render_template("register.html", subjects=SUBJECTS)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("landing"))


# ---------- Dashboard ---------- #

@app.route("/dashboard")
@login_required
def dashboard():
    exams_count = Exam.query.filter_by(user_id=current_user.id).count()
    contents_count = Content.query.filter_by(user_id=current_user.id).count()
    downloads = db.session.query(func.coalesce(func.sum(Content.downloads), 0))\
        .filter(Content.user_id == current_user.id).scalar() or 0
    attempts_count = db.session.query(Attempt).join(ExamVersion).join(Exam)\
        .filter(Exam.user_id == current_user.id).count()
    recent_exams = Exam.query.filter_by(user_id=current_user.id)\
        .order_by(Exam.created_at.desc()).limit(5).all()
    recent_contents = Content.query.order_by(Content.created_at.desc()).limit(6).all()
    return render_template("dashboard.html",
        stats=dict(exams=exams_count, contents=contents_count,
                   downloads=downloads, attempts=attempts_count),
        recent_exams=recent_exams, recent_contents=recent_contents)


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.name = request.form.get("name", current_user.name)
        current_user.school = request.form.get("school")
        current_user.subject = request.form.get("subject")
        current_user.bio = request.form.get("bio")
        db.session.commit()
        flash("Perfil atualizado.", "success")
        return redirect(url_for("profile"))
    return render_template("profile.html", subjects=SUBJECTS)


# ---------- Biblioteca ---------- #

@app.route("/library")
@login_required
def library():
    q = request.args.get("q", "").strip()
    subject = request.args.get("subject", "")
    grade_f = request.args.get("grade", "")
    kind = request.args.get("kind", "")
    sort = request.args.get("sort", "recent")

    query = Content.query
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Content.title.ilike(like),
                                 Content.description.ilike(like),
                                 Content.tags.ilike(like)))
    if subject: query = query.filter(Content.subject == subject)
    if grade_f: query = query.filter(Content.grade == grade_f)
    if kind:    query = query.filter(Content.kind == kind)
    if sort == "popular":
        query = query.order_by(Content.downloads.desc())
    else:
        query = query.order_by(Content.created_at.desc())

    fav_ids = {f.content_id for f in Favorite.query.filter_by(user_id=current_user.id)}
    like_ids = {l.content_id for l in Like.query.filter_by(user_id=current_user.id)}

    return render_template("library.html", contents=query.all(),
        subjects=SUBJECTS, grades=GRADES, kinds=KINDS,
        filters=dict(q=q, subject=subject, grade=grade_f, kind=kind, sort=sort),
        fav_ids=fav_ids, like_ids=like_ids)


@app.route("/library/upload", methods=["GET", "POST"])
@login_required
def library_upload():
    if request.method == "POST":
        f = request.files.get("file")
        if not f or not allowed_file(f.filename):
            flash("Arquivo inválido.", "error")
            return redirect(url_for("library_upload"))
        fname = secure_filename(f"{int(datetime.utcnow().timestamp())}_{f.filename}")
        f.save(os.path.join(UPLOAD_DIR, fname))
        c = Content(
            title=request.form["title"], description=request.form.get("description"),
            subject=request.form.get("subject"), grade=request.form.get("grade"),
            kind=request.form.get("kind"), tags=request.form.get("tags"),
            filename=fname, user_id=current_user.id,
        )
        db.session.add(c); db.session.commit()
        flash("Conteúdo publicado!", "success")
        return redirect(url_for("library"))
    return render_template("library_upload.html",
        subjects=SUBJECTS, grades=GRADES, kinds=KINDS)


@app.route("/library/<int:cid>")
@login_required
def content_detail(cid):
    c = db.session.get(Content, cid) or abort(404)
    is_fav = bool(Favorite.query.filter_by(user_id=current_user.id, content_id=cid).first())
    is_like = bool(Like.query.filter_by(user_id=current_user.id, content_id=cid).first())
    my_rating = Rating.query.filter_by(user_id=current_user.id, content_id=cid).first()
    return render_template("content_detail.html", c=c, is_fav=is_fav, is_like=is_like,
                           my_rating=my_rating.stars if my_rating else 0)


@app.route("/library/<int:cid>/download")
@login_required
def content_download(cid):
    c = db.session.get(Content, cid) or abort(404)
    c.downloads = (c.downloads or 0) + 1
    db.session.commit()
    return send_from_directory(UPLOAD_DIR, c.filename, as_attachment=True)


@app.post("/api/library/<int:cid>/like")
@login_required
def api_like(cid):
    existing = Like.query.filter_by(user_id=current_user.id, content_id=cid).first()
    if existing:
        db.session.delete(existing); liked = False
    else:
        db.session.add(Like(user_id=current_user.id, content_id=cid)); liked = True
    db.session.commit()
    count = Like.query.filter_by(content_id=cid).count()
    return jsonify(liked=liked, count=count)


@app.post("/api/library/<int:cid>/favorite")
@login_required
def api_favorite(cid):
    existing = Favorite.query.filter_by(user_id=current_user.id, content_id=cid).first()
    if existing:
        db.session.delete(existing); fav = False
    else:
        db.session.add(Favorite(user_id=current_user.id, content_id=cid)); fav = True
    db.session.commit()
    return jsonify(favorited=fav)


@app.post("/api/library/<int:cid>/rate")
@login_required
def api_rate(cid):
    stars = int(request.json.get("stars", 0))
    if stars < 1 or stars > 5: return jsonify(error="invalid"), 400
    r = Rating.query.filter_by(user_id=current_user.id, content_id=cid).first()
    if r: r.stars = stars
    else: db.session.add(Rating(user_id=current_user.id, content_id=cid, stars=stars))
    db.session.commit()
    c = db.session.get(Content, cid)
    return jsonify(avg=c.avg_rating, count=len(c.ratings))


@app.post("/api/library/<int:cid>/comment")
@login_required
def api_comment(cid):
    body = (request.json.get("body") or "").strip()
    if not body: return jsonify(error="empty"), 400
    c = Comment(user_id=current_user.id, content_id=cid, body=body)
    db.session.add(c); db.session.commit()
    return jsonify(id=c.id, user=current_user.name, body=c.body,
                   created_at=c.created_at.strftime("%d/%m/%Y %H:%M"))


# ---------- Provas ---------- #

@app.route("/exams")
@login_required
def exams_bank():
    items = Exam.query.filter_by(user_id=current_user.id)\
        .order_by(Exam.created_at.desc()).all()
    return render_template("exams_bank.html", exams=items)


@app.route("/exams/new")
@login_required
def exam_new():
    return render_template("exam_editor.html", exam=None)


@app.route("/exams/<int:eid>/edit")
@login_required
def exam_edit(eid):
    e = db.session.get(Exam, eid) or abort(404)
    if e.user_id != current_user.id: abort(403)
    return render_template("exam_editor.html", exam=e)


@app.post("/api/exams/save")
@login_required
def api_save_exam():
    data = request.json
    eid = data.get("id")
    if eid:
        e = db.session.get(Exam, int(eid)) or abort(404)
        if e.user_id != current_user.id: abort(403)
    else:
        e = Exam(user_id=current_user.id)
        db.session.add(e)
    e.title = data.get("title") or "Prova sem título"
    e.subject = data.get("subject")
    e.grade = data.get("grade")
    e.instructions = data.get("instructions")
    layout = (data.get("layout") or "single").lower()
    e.layout = layout if layout in ("single", "double") else "single"
    e.questions_json = json.dumps(data.get("questions") or [], ensure_ascii=False)
    db.session.commit()
    return jsonify(id=e.id)


@app.post("/exams/<int:eid>/duplicate")
@login_required
def exam_duplicate(eid):
    e = db.session.get(Exam, eid) or abort(404)
    if e.user_id != current_user.id: abort(403)
    copy = Exam(title=e.title + " (cópia)", subject=e.subject, grade=e.grade,
                instructions=e.instructions, layout=e.layout,
                questions_json=e.questions_json, user_id=current_user.id)
    db.session.add(copy); db.session.commit()
    return redirect(url_for("exam_edit", eid=copy.id))


@app.post("/exams/<int:eid>/delete")
@login_required
def exam_delete(eid):
    e = db.session.get(Exam, eid) or abort(404)
    if e.user_id != current_user.id: abort(403)
    db.session.delete(e); db.session.commit()
    return redirect(url_for("exams_bank"))


@app.post("/exams/<int:eid>/generate")
@login_required
def exam_generate(eid):
    """Gera N versões embaralhadas."""
    e = db.session.get(Exam, eid) or abort(404)
    if e.user_id != current_user.id: abort(403)
    n = max(1, min(10, int(request.form.get("versions", 2))))
    # zera versões anteriores
    ExamVersion.query.filter_by(exam_id=e.id).delete()
    db.session.commit()

    base = json.loads(e.questions_json)
    labels = "ABCDEFGHIJ"
    for v in range(n):
        qs = base.copy()
        random.shuffle(qs)
        payload = []
        for q in qs:
            item = {"type": q["type"], "statement": q["statement"]}
            if q["type"] == "objective":
                opts = list(q.get("options") or [])
                correct_text = q.get("correct")
                random.shuffle(opts)
                item["options"] = opts
                item["correct_index"] = opts.index(correct_text) if correct_text in opts else 0
                item["correct_text"] = correct_text
            elif q["type"] == "tf":
                item["options"] = ["Verdadeiro", "Falso"]
                item["correct_index"] = 0 if (q.get("correct") in (True, "true", "Verdadeiro", "V")) else 1
                item["correct_text"] = item["options"][item["correct_index"]]
            else:
                item["options"] = []
            payload.append(item)
        ver = ExamVersion(exam_id=e.id, label=labels[v],
                          payload_json=json.dumps(payload, ensure_ascii=False))
        db.session.add(ver)
    db.session.commit()
    return redirect(url_for("exam_versions", eid=e.id))


@app.route("/exams/<int:eid>/versions")
@login_required
def exam_versions(eid):
    e = db.session.get(Exam, eid) or abort(404)
    if e.user_id != current_user.id: abort(403)
    return render_template("exam_versions.html", exam=e)


@app.route("/exams/version/<int:vid>/pdf")
@login_required
def exam_version_pdf(vid):
    v = db.session.get(ExamVersion, vid) or abort(404)
    if v.exam.user_id != current_user.id: abort(403)
    pdf = build_exam_pdf(v.exam, v)
    return send_file(io.BytesIO(pdf), mimetype="application/pdf",
        as_attachment=True, download_name=f"{v.exam.title}-V{v.label}.pdf")


# ---------- Scanner ---------- #

@app.route("/scan")
@login_required
def scan_page():
    exams = Exam.query.filter_by(user_id=current_user.id)\
        .order_by(Exam.created_at.desc()).all()
    # apenas provas com versões geradas
    exams = [e for e in exams if e.versions]
    return render_template("scan.html", exams=exams)


@app.post("/api/scan")
@login_required
def api_scan():
    f = request.files.get("image")
    student = (request.form.get("student") or "").strip()
    exam_id = request.form.get("exam_id")
    if not f:
        return jsonify(error="Imagem obrigatória."), 400
    if not exam_id:
        return jsonify(error="Selecione a prova."), 400

    e = db.session.get(Exam, int(exam_id))
    if not e or e.user_id != current_user.id:
        return jsonify(error="Prova inválida."), 404
    if not e.versions:
        return jsonify(error="Esta prova ainda não tem versões geradas."), 400

    base_questions = json.loads(e.questions_json)
    n = len(base_questions)
    raw = f.read()

    det = detect_answers(raw, n)
    if not det["ok"]:
        return jsonify(error=det["error"] or "Falha na leitura."), 400
    detected = det["answers"]

    # identifica a versão pelo melhor casamento
    versions_payloads = [
        (v.id, v.label, json.loads(v.payload_json)) for v in e.versions
    ]
    best, _hits = best_version_match(detected, versions_payloads)
    if best is None:
        return jsonify(error="Não foi possível identificar a versão."), 400
    ver_id, ver_label, correct = best
    result = grade_against_key(detected, correct)

    a = Attempt(version_id=ver_id, student_name=student,
                answers_json=json.dumps(detected),
                score=result["score"], correct_count=result["correct"],
                total=result["total"])
    db.session.add(a); db.session.commit()

    return jsonify(
        result=result,
        version={"id": ver_id, "label": ver_label},
        student=student,
        exam={"id": e.id, "title": e.title},
    )


# ---------- Relatórios ---------- #

@app.route("/reports")
@login_required
def reports():
    rows = db.session.query(Exam, func.count(Attempt.id), func.avg(Attempt.score))\
        .outerjoin(ExamVersion, ExamVersion.exam_id == Exam.id)\
        .outerjoin(Attempt, Attempt.version_id == ExamVersion.id)\
        .filter(Exam.user_id == current_user.id)\
        .group_by(Exam.id).all()
    data = [{"title": r[0].title, "attempts": r[1] or 0,
             "avg": round(r[2] or 0, 2)} for r in rows]
    return render_template("reports.html", data=data)


@app.route("/reports/<int:eid>")
@login_required
def report_detail(eid):
    e = db.session.get(Exam, eid) or abort(404)
    if e.user_id != current_user.id: abort(403)
    attempts = db.session.query(Attempt).join(ExamVersion)\
        .filter(ExamVersion.exam_id == e.id).all()
    base = json.loads(e.questions_json)
    n = len(base)
    wrong_per_q = [0] * n
    total_attempts = len(attempts)
    for a in attempts:
        marks = json.loads(a.answers_json or "[]")
        ver = db.session.get(ExamVersion, a.version_id)
        payload = json.loads(ver.payload_json)
        for i, q in enumerate(payload):
            if i >= n: break
            if q["type"] in ("objective", "tf"):
                if marks[i] != q.get("correct_index"):
                    wrong_per_q[i] += 1
    return render_template("report_detail.html", exam=e, attempts=attempts,
        wrong_per_q=wrong_per_q, total_attempts=total_attempts,
        questions=base)


# ---------- bootstrap ---------- #

def seed():
    if User.query.first(): return
    u = User(name="Prof. Demo", email="demo@profeloop.com",
             school="Escola ProfeLoop", subject="Matemática",
             bio="Conta demo para experimentar a plataforma.")
    u.set_password("demo1234")
    db.session.add(u); db.session.commit()


def _migrate_sqlite():
    """Migrações leves para bancos criados em versões anteriores."""
    from sqlalchemy import text, inspect
    insp = inspect(db.engine)
    cols = [c["name"] for c in insp.get_columns("exams")]
    if "layout" not in cols:
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE exams ADD COLUMN layout VARCHAR(10) DEFAULT 'single'"))


with app.app_context():
    db.create_all()
    _migrate_sqlite()
    seed()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

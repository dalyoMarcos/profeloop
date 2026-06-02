from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(120), nullable=False)
    email         = db.Column(db.String(180), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    school        = db.Column(db.String(180))
    subject       = db.Column(db.String(120))
    bio           = db.Column(db.Text)
    avatar        = db.Column(db.String(255))
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)


class Content(db.Model):
    __tablename__ = "contents"
    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(220), nullable=False)
    description = db.Column(db.Text)
    subject     = db.Column(db.String(120))
    grade       = db.Column(db.String(60))
    kind        = db.Column(db.String(40))
    tags        = db.Column(db.String(255))
    filename    = db.Column(db.String(255))
    downloads   = db.Column(db.Integer, default=0)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    author      = db.relationship("User", backref="contents")
    likes       = db.relationship("Like",     backref="content", cascade="all, delete-orphan")
    favorites   = db.relationship("Favorite", backref="content", cascade="all, delete-orphan")
    comments    = db.relationship("Comment",  backref="content", cascade="all, delete-orphan")
    ratings     = db.relationship("Rating",   backref="content", cascade="all, delete-orphan")

    @property
    def avg_rating(self):
        if not self.ratings:
            return 0
        return round(sum(r.stars for r in self.ratings) / len(self.ratings), 1)


class Like(db.Model):
    __tablename__ = "likes"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content_id = db.Column(db.Integer, db.ForeignKey("contents.id"), nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "content_id"),)


class Favorite(db.Model):
    __tablename__ = "favorites"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content_id = db.Column(db.Integer, db.ForeignKey("contents.id"), nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "content_id"),)


class Comment(db.Model):
    __tablename__ = "comments"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content_id = db.Column(db.Integer, db.ForeignKey("contents.id"), nullable=False)
    body       = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user       = db.relationship("User")


class Rating(db.Model):
    __tablename__ = "ratings"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    content_id = db.Column(db.Integer, db.ForeignKey("contents.id"), nullable=False)
    stars      = db.Column(db.Integer, nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "content_id"),)


class Exam(db.Model):
    __tablename__   = "exams"
    id              = db.Column(db.Integer, primary_key=True)
    title           = db.Column(db.String(220), nullable=False)
    subject         = db.Column(db.String(120))
    grade           = db.Column(db.String(60))
    instructions    = db.Column(db.Text)
    layout          = db.Column(db.String(10), default="single")
    questions_json  = db.Column(db.Text, nullable=False, default="[]")
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    author          = db.relationship("User", backref="exams")
    versions        = db.relationship("ExamVersion", backref="exam",
                                      cascade="all, delete-orphan")


class ExamVersion(db.Model):
    __tablename__ = "exam_versions"
    id           = db.Column(db.Integer, primary_key=True)
    exam_id      = db.Column(db.Integer, db.ForeignKey("exams.id"), nullable=False)
    label        = db.Column(db.String(8))
    payload_json = db.Column(db.Text, nullable=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    attempts     = db.relationship("Attempt", backref="version",
                                   cascade="all, delete-orphan")


class Attempt(db.Model):
    """Tentativa de correção por escaneamento OMR."""
    __tablename__  = "attempts"
    id             = db.Column(db.Integer, primary_key=True)
    version_id     = db.Column(db.Integer, db.ForeignKey("exam_versions.id"), nullable=False)
    student_name   = db.Column(db.String(180))
    turma          = db.Column(db.String(80))          # ← NOVO
    answers_json   = db.Column(db.Text)
    score          = db.Column(db.Float)
    correct_count  = db.Column(db.Integer)
    total          = db.Column(db.Integer)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

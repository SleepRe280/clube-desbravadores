import json
from datetime import date, datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    full_name = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    children = db.relationship(
        "Member", back_populates="parent", foreign_keys="Member.parent_id"
    )
    posts = db.relationship("BoardPost", backref="author", lazy="dynamic")
    reset_tokens = db.relationship(
        "PasswordResetToken", backref="user", lazy="dynamic", cascade="all, delete-orphan"
    )

    def is_admin(self):
        return self.role == "admin"

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Member(db.Model):
    __tablename__ = "members"
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    unit = db.Column(db.String(60), nullable=True)
    birth_date = db.Column(db.Date, nullable=True)
    photo_filename = db.Column(db.String(200), nullable=True)
    cpf = db.Column(db.String(14), unique=True, nullable=True, index=True)
    blood_type = db.Column(db.String(8), nullable=True)
    father_name = db.Column(db.String(120), nullable=True)
    mother_name = db.Column(db.String(120), nullable=True)
    emergency_contact_name = db.Column(db.String(120), nullable=True)
    emergency_contact_phone = db.Column(db.String(40), nullable=True)
    notebook_current = db.Column(db.String(200), nullable=True)
    overall_performance = db.Column(db.Integer, default=0)
    activities_30_json = db.Column(db.Text, nullable=True)
    notebook_checklist_30_json = db.Column(db.Text, nullable=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    parent = db.relationship("User", back_populates="children", foreign_keys=[parent_id])
    activities = db.relationship("ActivityRecord", backref="member", lazy="dynamic")
    attendances = db.relationship("Attendance", backref="member", lazy="dynamic")
    duques_entries = db.relationship(
        "MeetingDuque", backref="member", lazy="dynamic", cascade="all, delete-orphan"
    )

    @property
    def age_years(self):
        if not self.birth_date:
            return None
        today = date.today()
        y = today.year - self.birth_date.year
        if (today.month, today.day) < (self.birth_date.month, self.birth_date.day):
            y -= 1
        return y

    def attendance_stats(self):
        rows = list(self.attendances)
        if not rows:
            return 0, 0, 0
        present = sum(1 for a in rows if a.present)
        return present, len(rows), round(100 * present / len(rows))

    def activity_progress_avg(self):
        rows = list(self.activities)
        if not rows:
            return None
        return round(sum(r.progress_percent or 0 for r in rows) / len(rows))

    def _legacy_ints_to_bools(self, data):
        out = []
        for i in range(30):
            if i < len(data):
                x = data[i]
                if isinstance(x, bool):
                    out.append(x)
                else:
                    try:
                        out.append(int(x) > 0)
                    except (TypeError, ValueError):
                        out.append(False)
            else:
                out.append(False)
        return out

    def get_notebook_checklist_30(self):
        """Checklist 1–30 do caderno atual: True/False por item."""
        if self.notebook_checklist_30_json:
            try:
                data = json.loads(self.notebook_checklist_30_json)
                if isinstance(data, list):
                    return self._legacy_ints_to_bools(data)
            except json.JSONDecodeError:
                pass
        if self.activities_30_json:
            try:
                data = json.loads(self.activities_30_json)
                if isinstance(data, list):
                    return self._legacy_ints_to_bools(data)
            except json.JSONDecodeError:
                pass
        return [False] * 30

    def notebook_checklist_progress_percent(self):
        c = self.get_notebook_checklist_30()
        n = sum(1 for x in c if x)
        return round(100 * n / 30)


class AgendaEvent(db.Model):
    """Compromissos e tarefas da agenda do clube (visível aos pais)."""

    __tablename__ = "agenda_events"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=True)
    event_date = db.Column(db.Date, nullable=False, index=True)
    event_time = db.Column(db.String(8), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DirectorateMember(db.Model):
    """Equipe de diretoria — apenas o essencial para o app dos pais e gestão."""

    __tablename__ = "directorate_members"
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    cargo = db.Column(db.String(120), nullable=False)
    photo_filename = db.Column(db.String(200), nullable=True)
    phone = db.Column(db.String(40), nullable=True)
    email_public = db.Column(db.String(120), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    display_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ClubNews(db.Model):
    __tablename__ = "club_news"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    level = db.Column(db.String(20), nullable=False, index=True)
    image_filename = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)


class ActivityRecord(db.Model):
    __tablename__ = "activity_records"
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(80), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    progress_percent = db.Column(db.Integer, default=0)
    completed = db.Column(db.Boolean, default=False)
    recorded_at = db.Column(db.Date, default=date.today)


class MeetingDuque(db.Model):
    """Duques registrados por reunião (moeda do clube), por desbravador."""

    __tablename__ = "meeting_duques"
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False, index=True)
    meeting_date = db.Column(db.Date, nullable=False, index=True)
    duques = db.Column(db.Integer, nullable=False, default=0)
    note = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Attendance(db.Model):
    __tablename__ = "attendances"
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("members.id"), nullable=False)
    meeting_date = db.Column(db.Date, nullable=False)
    present = db.Column(db.Boolean, default=True)
    note = db.Column(db.String(200), nullable=True)


class BoardPost(db.Model):
    __tablename__ = "board_posts"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

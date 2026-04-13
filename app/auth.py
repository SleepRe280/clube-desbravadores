from datetime import datetime, timedelta
from functools import wraps
import secrets

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.models import PasswordResetToken, User

bp = Blueprint("auth", __name__)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not current_user.is_admin():
            flash("Esta área é só para a diretoria.", "warning")
            return redirect(url_for("parent.home"))
        return f(*args, **kwargs)

    return decorated


def parent_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.is_admin():
            if current_user.is_authenticated and current_user.is_admin():
                return redirect(url_for("admin.dashboard"))
            flash("Faça login como responsável.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            next_url = request.args.get("next")
            if next_url:
                return redirect(next_url)
            if user.is_admin():
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("parent.home"))
        flash("E-mail ou senha incorretos.", "danger")
    return render_template("auth/login.html")


@bp.route("/logout")
def logout():
    logout_user()
    flash("Sessão encerrada.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/esqueci-senha", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        user = User.query.filter_by(email=email, role="parent").first()
        if user:
            PasswordResetToken.query.filter_by(user_id=user.id).delete()
            token = secrets.token_urlsafe(32)
            row = PasswordResetToken(
                user_id=user.id,
                token=token,
                expires_at=datetime.utcnow() + timedelta(hours=24),
            )
            db.session.add(row)
            db.session.commit()
            reset_url = url_for("auth.reset_password", token=token, _external=True)
            if current_app.debug:
                flash(
                    f"Desenvolvimento: abra este link para criar uma nova senha — {reset_url}",
                    "info",
                )
        flash(
            "Se este e-mail estiver cadastrado como responsável, você poderá redefinir a senha pelas instruções enviadas (ou pela mensagem em modo desenvolvimento). Caso contrário, procure o clube.",
            "success",
        )
        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html")


@bp.route("/redefinir-senha/<token>", methods=["GET", "POST"])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    row = PasswordResetToken.query.filter_by(token=token).first()
    if not row or row.expires_at < datetime.utcnow():
        flash("Link inválido ou expirado. Solicite um novo.", "danger")
        return redirect(url_for("auth.forgot_password"))

    user = db.session.get(User, row.user_id)
    if not user or user.role != "parent":
        flash("Conta inválida.", "danger")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        p1 = request.form.get("password") or ""
        p2 = request.form.get("password2") or ""
        if len(p1) < 6:
            flash("A senha deve ter pelo menos 6 caracteres.", "warning")
            return render_template("auth/reset_password.html", token=token)
        if p1 != p2:
            flash("As senhas não coincidem.", "warning")
            return render_template("auth/reset_password.html", token=token)
        user.set_password(p1)
        PasswordResetToken.query.filter_by(user_id=user.id).delete()
        db.session.commit()
        flash("Senha atualizada. Faça login.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", token=token)


@bp.route("/cadastro", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        full_name = (request.form.get("full_name") or "").strip()

        if not email or not password or not full_name:
            flash("Preencha todos os campos.", "warning")
            return render_template("auth/register.html")

        if email == "admin@clube.com":
            flash("Este e-mail é reservado para a conta da diretoria.", "warning")
            return render_template("auth/register.html")

        if len(password) < 6:
            flash("A senha deve ter pelo menos 6 caracteres.", "warning")
            return render_template("auth/register.html")

        if User.query.filter_by(email=email).first():
            flash("Este e-mail já está cadastrado. Use o login.", "warning")
            return render_template("auth/register.html")

        user = User(email=email, role="parent", full_name=full_name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user, remember=True)
        flash(
            "Conta criada. A diretoria associa seu filho à sua conta ao editar o desbravador.",
            "success",
        )
        return redirect(url_for("parent.home"))

    return render_template("auth/register.html")


@bp.route("/conta/senha", methods=["GET", "POST"])
@login_required
def change_password():
    if current_user.is_admin():
        flash("Use o painel da diretoria para alterações administrativas.", "info")
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        cur = request.form.get("current_password") or ""
        p1 = request.form.get("password") or ""
        p2 = request.form.get("password2") or ""
        if not current_user.check_password(cur):
            flash("Senha atual incorreta.", "danger")
            return render_template("auth/change_password.html")
        if len(p1) < 6:
            flash("A nova senha deve ter pelo menos 6 caracteres.", "warning")
            return render_template("auth/change_password.html")
        if p1 != p2:
            flash("As senhas novas não coincidem.", "warning")
            return render_template("auth/change_password.html")
        current_user.set_password(p1)
        db.session.commit()
        flash("Senha alterada com sucesso.", "success")
        return redirect(url_for("parent.account"))

    return render_template("auth/change_password.html")

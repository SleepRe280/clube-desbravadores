from datetime import datetime, timedelta
from functools import wraps
import secrets

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.email_util import send_simple_email
from app.extensions import db
from app.models import EmailConfirmationToken, PasswordResetToken, User

bp = Blueprint("auth", __name__)

_CONFIRM_CODE_ALPHABET = "ABDEFGHJKLMNPQRSTUVWXYZ23456789"


def _normalize_confirmation_code(raw: str) -> str:
    s = (raw or "").upper().replace(" ", "").replace("-", "")
    return "".join(c for c in s if c in _CONFIRM_CODE_ALPHABET)


def _generate_confirmation_code() -> str:
    for _ in range(64):
        code = "".join(secrets.choice(_CONFIRM_CODE_ALPHABET) for _ in range(8))
        if not EmailConfirmationToken.query.filter_by(confirmation_code=code).first():
            return code
    raise RuntimeError("Não foi possível gerar código de confirmação.")


def _format_code_for_display(code: str) -> str:
    c = (code or "").strip().upper()
    if len(c) == 8:
        return f"{c[:4]}-{c[4:]}"
    return c


def _login_next_url():
    n = request.form.get("next") if request.method == "POST" else request.args.get("next")
    return (n or "").strip() or None


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
            if user.role == "parent" and not user.email_verified:
                flash(
                    "Confirme seu e-mail antes de entrar. Verifique a caixa de entrada ou o spam.",
                    "warning",
                )
                return render_template("auth/login.html", next_url=_login_next_url())
            login_user(user, remember=True)
            next_url = _login_next_url()
            if next_url:
                return redirect(next_url)
            if user.is_admin():
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("parent.home"))
        flash("E-mail ou senha incorretos.", "danger")
    return render_template("auth/login.html", next_url=_login_next_url())


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
            body = (
                f"Olá!\n\nPara criar uma nova senha no portal do clube, acesse:\n{reset_url}\n\n"
                "O link expira em 24 horas.\n"
            )
            sent = send_simple_email(
                user.email, "Recuperação de senha — Portal do clube", body
            )
            if not sent and current_app.debug:
                flash(
                    f"Desenvolvimento: abra este link para criar uma nova senha — {reset_url}",
                    "info",
                )
        flash(
            "Se este e-mail estiver cadastrado como responsável, você receberá instruções para redefinir a senha. "
            "Caso contrário, procure o clube.",
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

        user = User(
            email=email, role="parent", full_name=full_name, email_verified=False
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        EmailConfirmationToken.query.filter_by(user_id=user.id).delete()
        ctoken = secrets.token_urlsafe(32)
        confirm_code = _generate_confirmation_code()
        conf_row = EmailConfirmationToken(
            user_id=user.id,
            token=ctoken,
            confirmation_code=confirm_code,
            expires_at=datetime.utcnow() + timedelta(hours=48),
        )
        db.session.add(conf_row)
        db.session.commit()

        code_display = _format_code_for_display(confirm_code)
        confirm_page = url_for("auth.confirm_registration_code", _external=True)
        subj = "Código para confirmar seu cadastro — Duque De Caxias"
        body = (
            f"Olá, {full_name}!\n\n"
            "Obrigado por se cadastrar no portal do clube de Desbravadores.\n\n"
            "Para ativar sua conta de responsável, acesse o portal e digite o código abaixo "
            f"na página de confirmação:\n{confirm_page}\n\n"
            f"Seu código de confirmação (válido por 48 horas):\n\n"
            f"    {code_display}\n\n"
            "Você pode digitar com ou sem o traço. Use apenas letras e números em maiúsculas.\n\n"
            "Depois de confirmar, você poderá entrar com seu e-mail e senha. "
            "A diretoria associa seu filho à sua conta ao cadastrar o desbravador.\n\n"
            "Se você não fez este cadastro, ignore este e-mail.\n"
        )
        sent = send_simple_email(user.email, subj, body)
        if sent:
            flash(
                "Enviamos um e-mail com o código de confirmação. "
                "Digite o código na próxima tela (verifique também o spam).",
                "success",
            )
        else:
            if current_app.debug:
                flash(
                    f"Desenvolvimento — e-mail não enviado. Seu código: {code_display}. "
                    "Digite-o na próxima tela.",
                    "warning",
                )
            else:
                flash(
                    "Conta criada, mas o e-mail com o código não pôde ser enviado. "
                    "Entre em contato com o clube ou tente novamente mais tarde.",
                    "danger",
                )
                return redirect(url_for("auth.login"))
        return redirect(url_for("auth.confirm_registration_code"))

    return render_template("auth/register.html")


@bp.route("/confirmar-cadastro", methods=["GET", "POST"])
def confirm_registration_code():
    """Responsável digita o código recebido por e-mail para ativar a conta."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        normalized = _normalize_confirmation_code(request.form.get("code", ""))
        if len(normalized) != 8:
            flash("O código tem 8 caracteres (letras e números). Confira o e-mail e tente de novo.", "warning")
            return render_template("auth/confirm_registration.html")

        row = EmailConfirmationToken.query.filter_by(confirmation_code=normalized).first()
        if not row or row.expires_at < datetime.utcnow():
            flash("Código inválido ou expirado. Peça um novo cadastro ou fale com o clube.", "danger")
            return render_template("auth/confirm_registration.html")

        user = db.session.get(User, row.user_id)
        if not user or user.role != "parent":
            flash("Conta inválida.", "danger")
            return redirect(url_for("auth.login"))

        user.email_verified = True
        db.session.delete(row)
        db.session.commit()
        flash(
            "Cadastro confirmado. Agora você pode entrar com seu e-mail e senha. "
            "A diretoria associa seu filho à sua conta ao cadastrar o desbravador.",
            "success",
        )
        return redirect(url_for("auth.login"))

    return render_template("auth/confirm_registration.html")


@bp.route("/confirmar-email/<token>")
def confirm_email(token):
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    row = EmailConfirmationToken.query.filter_by(token=token).first()
    if not row or row.expires_at < datetime.utcnow():
        flash("Link inválido ou expirado. Cadastre-se novamente ou fale com o clube.", "danger")
        return redirect(url_for("auth.register"))

    user = db.session.get(User, row.user_id)
    if not user or user.role != "parent":
        flash("Conta inválida.", "danger")
        return redirect(url_for("auth.login"))

    user.email_verified = True
    db.session.delete(row)
    db.session.commit()
    flash(
        "E-mail confirmado. Agora você pode entrar com sua senha. "
        "A diretoria associa seu filho à sua conta ao editar o desbravador.",
        "success",
    )
    return redirect(url_for("auth.login"))


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

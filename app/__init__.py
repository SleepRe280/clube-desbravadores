import os

import click
from flask import Flask, send_from_directory
from flask_login import LoginManager
from werkzeug.middleware.proxy_fix import ProxyFix

from app.extensions import db
from config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if os.environ.get("FLASK_ENV") == "production" and app.config.get(
        "SECRET_KEY"
    ) in (None, "", "troque-esta-chave-em-producao"):
        raise RuntimeError(
            "Em produção defina SECRET_KEY (variável de ambiente) com um valor longo e aleatório."
        )

    if os.environ.get("TRUST_PROXY", "").strip().lower() in ("1", "true", "yes", "on"):
        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1
        )

    instance_path = os.path.join(os.path.dirname(app.root_path), "instance")
    os.makedirs(instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)

    from app import models  # noqa: F401

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(models.User, int(user_id))

    from app.auth import bp as auth_bp

    app.register_blueprint(auth_bp)

    from app.admin_routes import bp as admin_bp

    app.register_blueprint(admin_bp, url_prefix="/admin")

    from app.parent_routes import bp as parent_bp

    app.register_blueprint(parent_bp, url_prefix="/pais")

    @app.route("/")
    def index():
        from flask import redirect, url_for
        from flask_login import current_user

        if current_user.is_authenticated:
            if current_user.is_admin():
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("parent.home"))
        return redirect(url_for("auth.login"))

    @app.route("/uploads/<path:rel_path>")
    def uploaded_file(rel_path):
        return send_from_directory(app.config["UPLOAD_FOLDER"], rel_path)

    @app.route("/health")
    def health():
        return {"status": "ok"}, 200

    prefix = (app.config.get("URL_PREFIX") or "").strip()
    if prefix:
        app.config["APPLICATION_ROOT"] = prefix
        app.config["SESSION_COOKIE_PATH"] = prefix + "/"
        from app.prefix_middleware import PrefixMiddleware

        app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix)

    with app.app_context():
        db.create_all()
        from app.db_migrate import ensure_users_email_verified_column, migrate_sqlite_schema

        migrate_sqlite_schema(app)
        ensure_users_email_verified_column(app)
        _ensure_default_admin(app)

    @app.cli.command("create-admin")
    @click.argument("email")
    @click.argument("password")
    @click.option("--full-name", default="Diretoria do Clube", show_default=True)
    def create_admin_command(email, password, full_name):
        """Cria ou promove conta de diretoria (use no Render após o primeiro deploy)."""
        from app.models import User

        email = email.strip().lower()
        u = User.query.filter_by(email=email).first()
        if u:
            u.role = "admin"
            u.email_verified = True
            u.full_name = full_name.strip() or u.full_name
            u.set_password(password)
        else:
            u = User(
                email=email,
                role="admin",
                full_name=full_name.strip() or "Admin",
                email_verified=True,
            )
            u.set_password(password)
            db.session.add(u)
        db.session.commit()
        click.echo(f"Conta de diretoria configurada: {email}")

    return app


def _ensure_default_admin(app):
    """Evita admin/senha padrão em PostgreSQL (produção)."""
    uri = (app.config.get("SQLALCHEMY_DATABASE_URI") or "").lower()
    if "sqlite" not in uri:
        return

    from app.models import User

    target = "admin@clube.com"
    if User.query.filter_by(email=target).first():
        return
    existing = User.query.filter_by(role="admin").first()
    if existing:
        existing.email = target
        existing.email_verified = True
        existing.set_password("admin123")
        db.session.commit()
        return
    u = User(
        email=target, role="admin", full_name="Diretoria do Clube", email_verified=True
    )
    u.set_password("admin123")
    db.session.add(u)
    db.session.commit()

"""Envio de e-mail via SMTP (configuração por variáveis de ambiente)."""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app


def mail_is_configured() -> bool:
    return bool(
        (current_app.config.get("MAIL_SERVER") or "").strip()
        and (current_app.config.get("MAIL_DEFAULT_SENDER") or "").strip()
    )


def send_simple_email(to_addr: str, subject: str, body_text: str) -> bool:
    """Envia e-mail texto simples. Retorna False se SMTP não estiver configurado ou falhar."""
    server = (current_app.config.get("MAIL_SERVER") or "").strip()
    sender = (current_app.config.get("MAIL_DEFAULT_SENDER") or "").strip()
    if not server or not sender:
        current_app.logger.warning(
            "E-mail não enviado: MAIL_SERVER ou MAIL_DEFAULT_SENDER ausente."
        )
        return False

    user = (current_app.config.get("MAIL_USERNAME") or "").strip()
    password = (current_app.config.get("MAIL_PASSWORD") or "").strip()
    port = int(current_app.config.get("MAIL_PORT") or 587)
    use_ssl = current_app.config.get("MAIL_USE_SSL", False)
    use_tls = current_app.config.get("MAIL_USE_TLS", True)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_addr
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(server, port, timeout=30) as smtp:
                if user:
                    smtp.login(user, password)
                smtp.sendmail(sender, [to_addr], msg.as_string())
        else:
            with smtplib.SMTP(server, port, timeout=30) as smtp:
                if use_tls:
                    smtp.starttls()
                if user:
                    smtp.login(user, password)
                smtp.sendmail(sender, [to_addr], msg.as_string())
        return True
    except Exception as exc:
        current_app.logger.exception("Falha ao enviar e-mail para %s: %s", to_addr, exc)
        return False

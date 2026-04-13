"""Permite servir o app sob um prefixo de URL (ex.: /portal) com SCRIPT_NAME correto."""

from typing import Tuple


def _normalize_prefix(prefix: str) -> str:
    p = (prefix or "").strip()
    if not p:
        return ""
    if not p.startswith("/"):
        p = "/" + p
    return p.rstrip("/") or "/"


class PrefixMiddleware:
    """Ajusta PATH_INFO/SCRIPT_NAME para rotas abaixo de `prefix`.

    Rotas isentas (sem prefixo) permanecem acessíveis na raiz — ex.: `/health` para o Render.
    Demais caminhos na raiz redirecionam para o equivalente sob o prefixo.
    """

    def __init__(self, app, prefix: str, exempt_paths: Tuple[str, ...] = ("/health",)):
        self.app = app
        self.prefix = _normalize_prefix(prefix)
        self.exempt_paths = exempt_paths

    def __call__(self, environ, start_response):
        if not self.prefix:
            return self.app(environ, start_response)

        path = environ.get("PATH_INFO") or "/"

        if self._is_exempt(path):
            return self.app(environ, start_response)

        if path == self.prefix or path.startswith(self.prefix + "/"):
            new_path = path[len(self.prefix) :] or "/"
            if not new_path.startswith("/"):
                new_path = "/" + new_path
            environ = environ.copy()
            base = environ.get("SCRIPT_NAME") or ""
            environ["SCRIPT_NAME"] = base + self.prefix
            environ["PATH_INFO"] = new_path
            return self.app(environ, start_response)

        if path == "/":
            return self._redirect(start_response, self.prefix + "/")

        loc = self.prefix + (path if path.startswith("/") else "/" + path)
        return self._redirect(start_response, loc)

    def _is_exempt(self, path: str) -> bool:
        for ex in self.exempt_paths:
            if path == ex or path.startswith(ex + "/"):
                return True
        return False

    @staticmethod
    def _redirect(start_response, location: str):
        start_response(
            "302 Found",
            [("Location", location), ("Content-Type", "text/plain; charset=utf-8")],
        )
        return [b""]

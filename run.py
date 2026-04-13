import os

if __name__ == "__main__":
    os.environ.setdefault("FLASK_DEBUG", "1")

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"Servidor: http://{host}:{port}")
    if "sqlite" in (app.config.get("SQLALCHEMY_DATABASE_URI") or "").lower():
        print("Admin padrão (só SQLite local): admin@clube.com / admin123")
    app.run(debug=app.config.get("DEBUG", False), host=host, port=port)

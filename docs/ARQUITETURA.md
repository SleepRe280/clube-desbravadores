# Arquitetura do projeto (Duque De Caxias)

## Visão geral

Aplicação **Flask** monolítica com **SQLite**, autenticação por papéis (`admin` / `parent`) e interface em **Jinja2** + **Tailwind CDN** + **CSS próprio** para layout e componentes.

```
Projeto Duque De Caxias/
├── app/
│   ├── __init__.py          # create_app, blueprints, uploads, migrate
│   ├── auth.py              # login, cadastro, recuperação de senha
│   ├── admin_routes.py      # painel da diretoria
│   ├── parent_routes.py     # área família (estilo rede social)
│   ├── models.py            # SQLAlchemy
│   ├── extensions.py        # db
│   ├── db_migrate.py        # ALTER TABLE SQLite incremental
│   ├── uploads_util.py      # salvar imagens
│   ├── static/css/          # arquitetura de estilos (ver abaixo)
│   └── templates/           # HTML por área (admin/, parent/, auth/)
├── config.py
├── run.py
├── instance/                # club.db + uploads (gitignore)
└── docs/ARQUITETURA.md
```

## Camada CSS (`app/static/css/`)

Ordem de import em **`app.css`**:

| Arquivo         | Função |
|----------------|--------|
| `tokens.css`   | Variáveis (`--color-*`, `--surface-*`, `--tap-min`, `clamp` para tipografia). |
| `layout.css`   | Shell responsivo: admin (menu mobile + sidebar desktop), pais (`parent-app`, painel, nav inferior), utilitários (`table-responsive`). |
| `components.css` | Botões (`.btn-primary`, `.btn-ghost`), cartões (`.card`), formulários (`.form-stack`, `.grid-form-2`). |

**Tailwind** continua disponível nos templates para utilitários rápidos; o CSS próprio concentra **tokens**, **comportamento multiplataforma** e **componentes estáveis**.

## Responsividade

- **Mobile-first** nas media queries (`layout.css`, ~1024px para admin em duas colunas).
- **Áreas de toque** mínimas (~44px) em navegação e botões.
- **Tabelas** admin envolvidas em `.table-responsive` (scroll horizontal em telas estreitas).
- **`100dvh`** / `safe-area` onde faz sentido (viewport móvel, notch).

## Diretoria (modelo enxuto)

`DirectorateMember` guarda apenas o necessário para o app dos pais e para a lista administrativa:

- `full_name`, `cargo`, `photo_filename`
- `phone`, `email_public` (públicos)
- `bio` (texto livre: apresentação, experiência, etc.)
- `display_order`, `created_at`

Campos removidos da modelagem atual: ficha escolar detalhada, RG/CPF interno, endereço, data de nascimento e vínculo com usuário admin — reduzem ruído; o que for institucional pode ir na **bio** ou na ficha dos **desbravadores**.

## Rotas principais

| Prefixo    | Público-alvo |
|-----------|----------------|
| `/`       | Redireciona por sessão |
| `/login`, `/cadastro`, `/esqueci-senha` | Todos |
| `/admin/` | Diretoria (`admin`) |
| `/pais/`  | Responsáveis (`parent`) |
| `/uploads/…` | Arquivos enviados (imagens) |

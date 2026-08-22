import os
from pathlib import Path
from datetime import datetime

import clickhouse_connect
from jinja2 import Template


# ============================================================
# Настройки
# ============================================================
# Можно выбрать формат:
#   DOC_FORMAT=md
#   DOC_FORMAT=html
#
# Приоритет:
#   1. аргумент командной строки: md / html
#   2. переменная DOC_FORMAT в .env / окружении
#   3. md по умолчанию
#
# Примеры:
#   python database_schema.py md
#   python database_schema.py html
#   python database_schema.py
#
# Подключение ClickHouse также можно настроить через .env:
#   CLICKHOUSE_HOST=localhost
#   CLICKHOUSE_PORT=8123
#   CLICKHOUSE_USER=default
#   CLICKHOUSE_PASSWORD=
#   CLICKHOUSE_DATABASE=
# ============================================================


def load_env_file(path=".env"):
    """Простой загрузчик .env без дополнительных зависимостей."""
    env_path = Path(path)

    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


load_env_file()

CLI_FORMAT = os.sys.argv[1].lower() if len(os.sys.argv) > 1 else None
DOC_FORMAT = (CLI_FORMAT or os.getenv("DOC_FORMAT", "md")).lower()

if DOC_FORMAT not in {"md", "html"}:
    raise SystemExit(
        f"Неизвестный формат: {DOC_FORMAT}. Используйте 'md' или 'html'."
    )


CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT"))
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD")
CLICKHOUSE_DATABASE = os.getenv("CLICKHOUSE_DATABASE")

OUTPUT_DIR = Path(os.getenv("DOC_OUTPUT_DIR", "docs"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# Подключение
# ============================================================
client = clickhouse_connect.get_client(
    host=CLICKHOUSE_HOST,
    port=CLICKHOUSE_PORT,
    username=CLICKHOUSE_USER,
    password=CLICKHOUSE_PASSWORD,
    database=CLICKHOUSE_DATABASE,
)


# ============================================================
# Получаем список таблиц
# ============================================================
tables = client.query("""
    SELECT
        database,
        name,
        engine,
        total_rows,
        total_bytes,
        metadata_modification_time,
        comment
    FROM system.tables
    WHERE database NOT IN ('system', 'INFORMATION_SCHEMA')
      AND engine NOT IN ('View', 'MaterializedView')
    ORDER BY database, name
""").result_rows


# ============================================================
# Получаем структуру таблиц
# ============================================================
columns = client.query("""
    SELECT
        database,
        table,
        name,
        type,
        position,
        default_expression,
        comment
    FROM system.columns
    WHERE database NOT IN ('system', 'INFORMATION_SCHEMA')
    ORDER BY database, table, position
""").result_rows


# ============================================================
# Материализованные представления
# ============================================================
mv = client.query("""
    SELECT
        database,
        name,
        query,
        engine,
        comment
    FROM system.tables
    WHERE engine = 'MaterializedView'
      AND database NOT IN ('system', 'INFORMATION_SCHEMA')
    ORDER BY database, name
""").result_rows


# ============================================================
# Представления VIEW
# ============================================================
views = client.query("""
    SELECT
        database,
        name,
        create_table_query,
        comment
    FROM system.tables
    WHERE engine = 'View'
      AND database NOT IN ('system', 'INFORMATION_SCHEMA')
    ORDER BY database, name
""").result_rows


# ============================================================
# Данные для шаблонов
# ============================================================
generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def mb(value):
    return round(value / 1024 / 1024, 2)


# ============================================================
# Markdown
# ============================================================
MD_TEMPLATE = Template(r"""# Документация базы данных

> Сгенерировано: **{{ generated_at }}**

## Содержание

- [Таблицы](#таблицы)
- [Материализованные представления](#материализованные-представления)
- [Представления VIEW](#представления-view)

---

## Таблицы

{% if tables %}
{% for db, name, engine, rows, bytes, modified, comment in tables %}
### `{{ db }}.{{ name }}`

| Параметр | Значение |
|---|---|
| Движок | `{{ engine }}` |
| Строк | {{ rows }} |
| Размер | {{ mb(bytes) }} MB |
| Изменена | {{ modified }} |
| Комментарий | {{ comment or '—' }} |

#### Структура

| # | Поле | Тип | Значение по умолчанию | Комментарий |
|---:|---|---|---|---|
{% for col in columns if col[0] == db and col[1] == name %}
| {{ col[4] }} | `{{ col[2] }}` | `{{ col[3] }}` | `{{ col[5] or '—' }}` | {{ col[6] or '—' }} |
{% endfor %}

---
{% endfor %}
{% else %}
Таблицы отсутствуют.
{% endif %}

## Материализованные представления

{% if mv %}
{% for db, name, query, engine, comment in mv %}
### `{{ db }}.{{ name }}`

| Параметр | Значение |
|---|---|
| Движок | `{{ engine }}` |
| Комментарий | {{ comment or '—' }} |

#### Запрос

```sql
{{ query }}
```

---
{% endfor %}
{% else %}
Материализованные представления отсутствуют.
{% endif %}

## Представления VIEW

{% if views %}
{% for db, name, query, comment in views %}
### `{{ db }}.{{ name }}`

| Параметр | Значение |
|---|---|
| Комментарий | {{ comment or '—' }} |

#### Создание

```sql
{{ query }}
```

---
{% endfor %}
{% else %}
Представления отсутствуют.
{% endif %}
""")


# ============================================================
# HTML
# ============================================================
HTML_TEMPLATE = Template(r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Документация базы данных</title>
<style>
    :root {
        color-scheme: light;
        --bg: #f4f6f8;
        --card: #ffffff;
        --text: #20252b;
        --muted: #6b7280;
        --border: #e5e7eb;
        --accent: #2563eb;
        --code-bg: #f3f4f6;
        --header-bg: #111827;
    }

    * {
        box-sizing: border-box;
    }

    html {
        scroll-behavior: smooth;
    }

    body {
        margin: 0;
        background: var(--bg);
        color: var(--text);
        font-family:
            -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
            Helvetica, Arial, sans-serif;
        line-height: 1.6;
    }

    .container {
        width: min(1200px, calc(100% - 32px));
        margin: 0 auto;
    }

    header {
        background: var(--header-bg);
        color: white;
        padding: 42px 0;
        margin-bottom: 28px;
    }

    header h1 {
        margin: 0 0 8px;
        font-size: 32px;
        letter-spacing: -0.02em;
    }

    header p {
        margin: 0;
        color: #d1d5db;
    }

    nav {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 24px;
    }

    nav h2 {
        margin-top: 0;
        font-size: 18px;
    }

    nav a {
        color: var(--accent);
        text-decoration: none;
    }

    nav a:hover {
        text-decoration: underline;
    }

    section {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 28px;
        margin-bottom: 24px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
    }

    h2 {
        margin-top: 0;
        font-size: 26px;
    }

    h3 {
        margin-top: 28px;
        font-size: 20px;
        color: var(--accent);
    }

    .table-title {
        margin-top: 34px;
    }

    table {
        width: 100%;
        border-collapse: collapse;
        margin: 16px 0 24px;
        font-size: 14px;
    }

    th, td {
        border: 1px solid var(--border);
        padding: 9px 11px;
        text-align: left;
        vertical-align: top;
    }

    th {
        background: #f9fafb;
        font-weight: 600;
    }

    tr:nth-child(even) td {
        background: #fcfcfd;
    }

    code {
        background: var(--code-bg);
        border-radius: 5px;
        padding: 2px 5px;
        font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
        font-size: 0.9em;
    }

    pre {
        overflow-x: auto;
        background: #111827;
        color: #e5e7eb;
        padding: 18px;
        border-radius: 8px;
        line-height: 1.5;
    }

    pre code {
        background: transparent;
        padding: 0;
        color: inherit;
    }

    .meta {
        width: 100%;
        max-width: 900px;
    }

    .empty {
        color: var(--muted);
        font-style: italic;
    }

    footer {
        color: var(--muted);
        text-align: center;
        padding: 10px 0 36px;
        font-size: 13px;
    }

    @media (max-width: 700px) {
        .container {
            width: min(100% - 20px, 1200px);
        }

        header {
            padding: 28px 0;
        }

        header h1 {
            font-size: 25px;
        }

        section {
            padding: 18px;
        }

        table {
            display: block;
            overflow-x: auto;
            white-space: nowrap;
        }
    }

    @media print {
        body {
            background: white;
        }

        header {
            background: white;
            color: black;
            padding: 10px 0;
        }

        header p {
            color: #444;
        }

        section, nav {
            box-shadow: none;
            break-inside: avoid;
        }

        nav {
            display: none;
        }

        a {
            color: black;
        }
    }
</style>
</head>

<body>
<header>
    <div class="container">
        <h1>Документация базы данных</h1>
        <p>Сгенерировано: {{ generated_at }}</p>
    </div>
</header>

<main class="container">
    <nav>
        <h2>Содержание</h2>
        <ul>
            <li><a href="#tables">Таблицы</a></li>
            <li><a href="#materialized-views">Материализованные представления</a></li>
            <li><a href="#views">Представления VIEW</a></li>
        </ul>
    </nav>

    <section id="tables">
        <h2>Таблицы</h2>

        {% if tables %}
        {% for db, name, engine, rows, bytes, modified, comment in tables %}
        <h3 class="table-title" id="table-{{ loop.index }}">
            <code>{{ db }}.{{ name }}</code>
        </h3>

        <table class="meta">
            <tr><th>Параметр</th><th>Значение</th></tr>
            <tr><td>Движок</td><td><code>{{ engine }}</code></td></tr>
            <tr><td>Строк</td><td>{{ rows }}</td></tr>
            <tr><td>Размер</td><td>{{ mb(bytes) }} MB</td></tr>
            <tr><td>Изменена</td><td>{{ modified }}</td></tr>
            <tr><td>Комментарий</td><td>{{ comment or '—' }}</td></tr>
        </table>

        <h4>Структура</h4>
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Поле</th>
                    <th>Тип</th>
                    <th>Значение по умолчанию</th>
                    <th>Комментарий</th>
                </tr>
            </thead>
            <tbody>
            {% for col in columns if col[0] == db and col[1] == name %}
                <tr>
                    <td>{{ col[4] }}</td>
                    <td><code>{{ col[2] }}</code></td>
                    <td><code>{{ col[3] }}</code></td>
                    <td>{{ col[5] or '—' }}</td>
                    <td>{{ col[6] or '—' }}</td>
                </tr>
            {% endfor %}
            </tbody>
        </table>
        {% endfor %}
        {% else %}
        <p class="empty">Таблицы отсутствуют.</p>
        {% endif %}
    </section>

    <section id="materialized-views">
        <h2>Материализованные представления</h2>

        {% if mv %}
        {% for db, name, query, engine, comment in mv %}
        <h3><code>{{ db }}.{{ name }}</code></h3>

        <table class="meta">
            <tr><th>Параметр</th><th>Значение</th></tr>
            <tr><td>Движок</td><td><code>{{ engine }}</code></td></tr>
            <tr><td>Комментарий</td><td>{{ comment or '—' }}</td></tr>
        </table>

        <h4>Запрос</h4>
        <pre><code>{{ query }}</code></pre>
        {% endfor %}
        {% else %}
        <p class="empty">Материализованные представления отсутствуют.</p>
        {% endif %}
    </section>

    <section id="views">
        <h2>Представления VIEW</h2>

        {% if views %}
        {% for db, name, query, comment in views %}
        <h3><code>{{ db }}.{{ name }}</code></h3>

        <table class="meta">
            <tr><th>Параметр</th><th>Значение</th></tr>
            <tr><td>Комментарий</td><td>{{ comment or '—' }}</td></tr>
        </table>

        <h4>Создание</h4>
        <pre><code>{{ query }}</code></pre>
        {% endfor %}
        {% else %}
        <p class="empty">Представления отсутствуют.</p>
        {% endif %}
    </section>

    <footer>
        Database Schema Documentation
    </footer>
</main>
</body>
</html>
""")


# ============================================================
# Генерация
# ============================================================
context = {
    "tables": tables,
    "columns": columns,
    "mv": mv,
    "views": views,
    "generated_at": generated_at,
    "mb": mb,
}

if DOC_FORMAT == "html":
    output_file = OUTPUT_DIR / "database_schema.html"
    content = HTML_TEMPLATE.render(**context)
else:
    output_file = OUTPUT_DIR / "database_schema.md"
    content = MD_TEMPLATE.render(**context)

output_file.write_text(content, encoding="utf-8")

print(f"Готово: {output_file}")
print(f"Формат: {DOC_FORMAT.upper()}")

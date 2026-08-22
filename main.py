import os
from pathlib import Path
from datetime import datetime

import clickhouse_connect
from jinja2 import Template


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
tables = client.query(f"""
    SELECT
        database,
        name,
        engine,
        total_rows,
        total_bytes,
        metadata_modification_time,
        comment
    FROM system.tables
    WHERE database = '{CLICKHOUSE_DATABASE}'
      AND engine NOT IN ('View', 'MaterializedView')
    ORDER BY database, name
""").result_rows


# ============================================================
# Получаем структуру таблиц
# ============================================================
columns = client.query(f"""
    SELECT
        database,
        table,
        name,
        type,
        position,
        default_expression,
        comment
    FROM system.columns
    WHERE database = '{CLICKHOUSE_DATABASE}'
    ORDER BY database, table, position
""").result_rows


# ============================================================
# Материализованные представления
# ============================================================
mv = client.query(f"""
    SELECT
        database,
        name,
        engine,
        comment
    FROM system.tables
    WHERE engine = 'MaterializedView'
      AND database = '{CLICKHOUSE_DATABASE}'
    ORDER BY database ASC, name ASC
""").result_rows


# ============================================================
# Представления VIEW
# ============================================================
views = client.query(f"""
    SELECT
        database,
        name,
        comment
    FROM system.tables
    WHERE engine = 'View'
      AND database = '{CLICKHOUSE_DATABASE}'
    ORDER BY database, name
""").result_rows


# ============================================================
# Данные для шаблонов
# ============================================================
generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def mb(value):
    if value is None:
        return "—"
    return round(value / 1024 / 1024, 2)


# ============================================================
# Markdown
# ============================================================
MD_TEMPLATE = Template(r"""# 📊 Документация базы данных ClickHouse

**База данных:** `{{ database }}`  
**Сгенерировано:** {{ generated_at }}

---

## 📑 Содержание

- [📋 Таблицы](#таблицы)
- [🔄 Материализованные представления](#материализованные-представления)
- [👁️ Представления VIEW](#представления-view)

---

## 📋 Таблицы

{% if tables %}
{% for db, name, engine, rows, bytes, modified, comment in tables %}
### `{{ name }}`

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
{%- for col in columns if col[0] == db and col[1] == name %}
| {{ col[4] }} | `{{ col[2] }}` | `{{ col[3] }}` | `{{ col[5] or '—' }}` | {{ col[6] or '—' }} |
{%- endfor %}

---
{% endfor %}
{% else %}
Таблицы отсутствуют.
{% endif %}

## 🔄 Материализованные представления

{% if mv %}
{% for db, name, engine, comment in mv %}
### `{{ name }}`

| Параметр | Значение |
|---|---|
| Движок | `{{ engine }}` |
| Комментарий | {{ comment or '—' }} |

---
{% endfor %}
{% else %}
Материализованные представления отсутствуют.
{% endif %}

## 👁️ Представления VIEW

{% if views %}
{% for db, name, comment in views %}
### `{{ name }}`

| Параметр | Значение |
|---|---|
| Комментарий | {{ comment or '—' }} |

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
    <title>📊 Документация ClickHouse</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        h1 { color: #333; }
        h2 { color: #555; margin-top: 30px; border-bottom: 2px solid #007bff; padding-bottom: 10px; }
        h3 { color: #007bff; }
        table { border-collapse: collapse; width: 100%; background: white; margin: 15px 0; }
        th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
        th { background: #007bff; color: white; }
        tr:nth-child(even) { background: #f9f9f9; }
        .meta { color: #666; font-size: 14px; }
        code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Документация базы данных ClickHouse</h1>
        <p class="meta"><strong>База данных:</strong> <code>{{ database }}</code><br><strong>Сгенерировано:</strong> {{ generated_at }}</p>
        <hr>

        <h2>📋 Таблицы</h2>
        {% if tables %}
            {% for db, name, engine, rows, bytes, modified, comment in tables %}
            <h3>{{ name }}</h3>
            <table>
                <tr><th>Параметр</th><th>Значение</th></tr>
                <tr><td>Движок</td><td><code>{{ engine }}</code></td></tr>
                <tr><td>Строк</td><td>{{ rows }}</td></tr>
                <tr><td>Размер</td><td>{{ mb(bytes) }} MB</td></tr>
                <tr><td>Изменена</td><td>{{ modified }}</td></tr>
                <tr><td>Комментарий</td><td>{{ comment or '—' }}</td></tr>
            </table>

            <h4>Структура</h4>
            <table>
                <tr><th>#</th><th>Поле</th><th>Тип</th><th>Значение по умолчанию</th><th>Комментарий</th></tr>
                {%- for col in columns if col[0] == db and col[1] == name %}
                <tr><td>{{ col[4] }}</td><td><code>{{ col[2] }}</code></td><td><code>{{ col[3] }}</code></td><td><code>{{ col[5] or '—' }}</code></td><td>{{ col[6] or '—' }}</td></tr>
                {%- endfor %}
            </table>
            {% endfor %}
        {% else %}
            <p>Таблицы отсутствуют.</p>
        {% endif %}

        <h2>🔄 Материализованные представления</h2>
        {% if mv %}
            {% for db, name, engine, comment in mv %}
            <h3>{{ name }}</h3>
            <table>
                <tr><th>Параметр</th><th>Значение</th></tr>
                <tr><td>Движок</td><td><code>{{ engine }}</code></td></tr>
                <tr><td>Комментарий</td><td>{{ comment or '—' }}</td></tr>
            </table>
            {% endfor %}
        {% else %}
            <p>Материализованные представления отсутствуют.</p>
        {% endif %}

        <h2>👁️ Представления VIEW</h2>
        {% if views %}
            {% for db, name, comment in views %}
            <h3>{{ name }}</h3>
            <table>
                <tr><th>Параметр</th><th>Значение</th></tr>
                <tr><td>Комментарий</td><td>{{ comment or '—' }}</td></tr>
            </table>
            {% endfor %}
        {% else %}
            <p>Представления отсутствуют.</p>
        {% endif %}
    </div>
</body>
</html>""")

# ============================================================
# Генерируем документацию
# ============================================================
if DOC_FORMAT == "md":
    md_content = MD_TEMPLATE.render(
        database=CLICKHOUSE_DATABASE,
        generated_at=generated_at,
        tables=tables,
        columns=columns,
        mv=mv,
        views=views,
        mb=mb
    )
    
    output_file = OUTPUT_DIR / f"database_schema.{DOC_FORMAT}"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(md_content)
    
    print(f"✅ Документация сгенерирована: {output_file}")

elif DOC_FORMAT == "html":
    html_content = HTML_TEMPLATE.render(
        database=CLICKHOUSE_DATABASE,
        generated_at=generated_at,
        tables=tables,
        columns=columns,
        mv=mv,
        views=views,
        mb=mb
    )
    
    output_file = OUTPUT_DIR / f"database_schema.{DOC_FORMAT}"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"✅ Документация сгенерирована: {output_file}")

import os
import re
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

# Ссылка на интерактивную ER-диаграмму (GitLab Pages) в документации.
ER_PAGES_URL = os.getenv("ER_PAGES_URL")

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
# Версия ClickHouse
# ============================================================
server_info = client.query("SELECT version()").result_rows
clickhouse_version = server_info[0][0] if server_info else None


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
        metadata_modification_time,  -- время последнего изменения СТРУКТУРЫ (DDL), а не данных
        comment,
        sorting_key,
        primary_key
    FROM system.tables
    WHERE database = '{CLICKHOUSE_DATABASE}'
      AND engine NOT IN ('View', 'MaterializedView', 'Dictionary')
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
mv_raw = client.query(f"""
    SELECT
        database,
        name,
        engine,
        comment,
        create_table_query
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
# Словари
# ============================================================
dict_raw = client.query(f"""
    SELECT
        t.database,
        t.name,
        t.comment,
        d.source
    FROM system.tables AS t
    LEFT JOIN system.dictionaries AS d
      ON t.database = d.database AND t.name = d.name
    WHERE t.database = '{CLICKHOUSE_DATABASE}'
      AND t.engine = 'Dictionary'
    ORDER BY t.name ASC
""").result_rows


# ============================================================
# Данные для шаблонов
# ============================================================
generated_at = datetime.now().strftime("%d-%m-%Y")


def format_size(value):
    """Форматирует размер таблицы в читаемый вид (B, KB, MB, GB).

    value — размер в байтах (total_bytes из system.tables).
    Для мелких таблиц возвращает KB/B, чтобы не показывать «0.0 MB».
    """
    if value is None:
        return "—"
    value = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if value < 1024.0 or unit == "PB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024.0


def clean_identifier(name):
    """Убирает обратные кавычки и префикс базы данных из имени таблицы."""
    if not name:
        return None
    name = name.replace("`", "").strip()
    if "." in name:
        name = name.rsplit(".", 1)[-1]
    return name


def extract_mv_target(create_query):
    """Извлекает целевую таблицу из 'CREATE MATERIALIZED VIEW ... TO <table> ...'."""
    if not create_query:
        return None
    m = re.search(r"\bTO\s+([^\s]+)", create_query, re.IGNORECASE)
    if not m:
        return None
    return clean_identifier(m.group(1))


def parse_dict_source(source):
    """Разбирает колонку source словаря. Возвращает (описание, исходная таблица).

    В разных версиях ClickHouse source бывает String ('тип: бд.таблица')
    или Map(String, String). Если конкретная таблица не задана (источник
    через query и т.п.), исходная таблица = None.
    """
    if not source:
        return None, None

    if isinstance(source, dict):
        stype = source.get("type")
        table = source.get("table") or ""
        db = source.get("db") or ""
    else:
        text = str(source)
        stype, _, rest = text.partition(":")
        stype = stype.strip() or None
        rest = rest.strip()
        if "." in rest:
            db, table = rest.rsplit(".", 1)
        else:
            db, table = rest, ""
        db = db.strip() or None
        table = table.strip() or None

    desc = ": ".join(p for p in (stype, db) if p) or None
    if table:
        desc = f"{desc}.{table}" if desc else table

    source_table = f"{db}.{table}" if db and table else None
    return desc, source_table


# Обрабатываем материализованные представления: добавляем целевую таблицу (TO ...)
mv = [
    (db, name, engine, comment, extract_mv_target(create_query))
    for db, name, engine, comment, create_query in mv_raw
]

# Обрабатываем словари: добавляем описание источника и исходную таблицу
dictionaries = []
for db, name, comment, source in dict_raw:
    source_desc, source_table = parse_dict_source(source)
    dictionaries.append((db, name, comment, source_desc, source_table))


# ============================================================
# Markdown
# ============================================================
MD_TEMPLATE = Template(r"""# 📊 Документация по объектам БД
**СУБД:** `ClickHouse (v.{{ clickhouse_version }})`

**Контур:** `Stage`

**БД:** `{{ database }}`  

**Сгенерировано:** {{ generated_at }}

---

## 📑 Содержание

- [📋 Таблицы](#таблицы)
- [🔄 Материализованные представления](#материализованные-представления)
- [👁️ Представления VIEW](#представления-view)
- [📖 Словари](#словари)
- 🕸️ ER-диаграмма: [Markdown](er_diagram.md) · [Интерактивная HTML]({{ er_pages_url }})

---

<a id="таблицы"></a>
## 📋 Таблицы

{% if tables %}
{% for db, name, engine, rows, bytes, modified, comment, sorting_key, primary_key in tables %}
### `{{ name }}`

| Параметр | Значение |
|---|---|
| Движок | `{{ engine }}` |
| Строк | {{ rows }} |
| Сортировка | `{{ sorting_key or '—' }}` |
| Первичный ключ | `{{ primary_key or '—' }}` |
| Размер | {{ format_size(bytes) }} |
| Изменена (структура) | {{ modified }} |
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

<a id="материализованные-представления"></a>
## 🔄 Материализованные представления

{% if mv %}
{% for db, name, engine, comment, target in mv %}
### `{{ name }}`

| Параметр | Значение |
|---|---|
| Движок | `{{ engine }}` |
| Целевая таблица | `{{ target or '—' }}` |
| Комментарий | {{ comment or '—' }} |

---
{% endfor %}
{% else %}
Материализованные представления отсутствуют.
{% endif %}

<a id="представления-view"></a>
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

<a id="словари"></a>
## 📖 Словари

{% if dictionaries %}
{% for db, name, comment, source_desc, source_table in dictionaries %}
### `{{ name }}`

| Параметр | Значение |
|---|---|
| Источник | {{ source_desc or '—' }} |
| Комментарий | {{ comment or '—' }} |

---
{% endfor %}
{% else %}
Словари отсутствуют.
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
        <p class="meta">
            <strong>База данных:</strong> <code>{{ database }}</code><br>
            <strong>Версия ClickHouse:</strong> <code>{{ clickhouse_version }}</code><br>
            <strong>Сгенерировано:</strong> {{ generated_at }}<br>
            <strong>ER-диаграмма:</strong> <a href="er_diagram.md">Markdown</a> · <a href="{{ er_pages_url }}">Интерактивная HTML</a>
        </p>
        <hr>

        <h2>📋 Таблицы</h2>
        {% if tables %}
            {% for db, name, engine, rows, bytes, modified, comment, sorting_key, primary_key in tables %}
            <h3>{{ name }}</h3>
            <table>
                <tr><th>Параметр</th><th>Значение</th></tr>
                <tr><td>Движок</td><td><code>{{ engine }}</code></td></tr>
                <tr><td>Строк</td><td>{{ rows }}</td></tr>
                <tr><td>Сортировка</td><td><code>{{ sorting_key or '—' }}</code></td></tr>
                <tr><td>Первичный ключ</td><td><code>{{ primary_key or '—' }}</code></td></tr>
                <tr><td>Размер</td><td>{{ format_size(bytes) }}</td></tr>
                <tr><td>Изменена (структура)</td><td>{{ modified }}</td></tr>
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
            {% for db, name, engine, comment, target in mv %}
            <h3>{{ name }}</h3>
            <table>
                <tr><th>Параметр</th><th>Значение</th></tr>
                <tr><td>Движок</td><td><code>{{ engine }}</code></td></tr>
                <tr><td>Целевая таблица</td><td><code>{{ target or '—' }}</code></td></tr>
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

        <h2>📖 Словари</h2>
        {% if dictionaries %}
            {% for db, name, comment, source_desc, source_table in dictionaries %}
            <h3>{{ name }}</h3>
            <table>
                <tr><th>Параметр</th><th>Значение</th></tr>
                <tr><td>Источник</td><td>{{ source_desc or '—' }}</td></tr>
                <tr><td>Комментарий</td><td>{{ comment or '—' }}</td></tr>
            </table>
            {% endfor %}
        {% else %}
            <p>Словари отсутствуют.</p>
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
        clickhouse_version=clickhouse_version,
        er_pages_url=ER_PAGES_URL,
        tables=tables,
        columns=columns,
        mv=mv,
        views=views,
        dictionaries=dictionaries,
        format_size=format_size
    )
    
    output_file = OUTPUT_DIR / f"database_schema.{DOC_FORMAT}"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(md_content)
    
    print(f"✅ Документация сгенерирована: {output_file}")

elif DOC_FORMAT == "html":
    html_content = HTML_TEMPLATE.render(
        database=CLICKHOUSE_DATABASE,
        generated_at=generated_at,
        clickhouse_version=clickhouse_version,
        er_pages_url=ER_PAGES_URL,
        tables=tables,
        columns=columns,
        mv=mv,
        views=views,
        dictionaries=dictionaries,
        format_size=format_size
    )
    
    output_file = OUTPUT_DIR / f"database_schema.{DOC_FORMAT}"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"✅ Документация сгенерирована: {output_file}")

import clickhouse_connect
from jinja2 import Template
import os

# Подключение
client = clickhouse_connect.get_client(
    host='localhost', 
    port=8123,
    username='default',
    password=''
)

# Получаем список таблиц
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
    ORDER BY database, name
""").result_rows

# Получаем структуру каждой таблицы
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

# Материализованные представления
mv = client.query("""
    SELECT 
        database,
        name,
        query,
        engine,
        comment
    FROM system.tables
    WHERE engine = 'MaterializedView'
""").result_rows

# Представления (VIEW)
views = client.query("""
    SELECT 
        database,
        name,
        create_table_query,
        comment
    FROM system.tables
    WHERE engine = 'View'
""").result_rows

# Генерируем MD
template = Template("""
# Документация базы данных

## Таблицы
{% for db, name, engine, rows, bytes, modified, comment in tables %}
### {{ db }}.{{ name }}
- **Движок:** {{ engine }}
- **Строк:** {{ rows }}
- **Размер:** {{ (bytes/1024/1024)|round(2) }} MB
- **Изменена:** {{ modified }}
- **Комментарий:** {{ comment or 'Нет' }}

**Структура:**
| Поле | Тип | Позиция | Значение по умолчанию | Коммент |
|------|-----|---------|----------------------|---------|
{% for col in columns if col[0] == db and col[1] == name %}
| {{ col[2] }} | {{ col[3] }} | {{ col[4] }} | {{ col[5] or '' }} | {{ col[6] or '' }} |
{% endfor %}

---
{% endfor %}

## Материализованные представления
{% for db, name, query, engine, comment in mv %}
### {{ db }}.{{ name }}
- **Запрос:** `{{ query }}`
- **Движок:** {{ engine }}
- **Коммент:** {{ comment or 'Нет' }}
{% endfor %}

## Представления (VIEW)
{% for db, name, query, comment in views %}
### {{ db }}.{{ name }}
- **Создание:** `{{ query[:200] }}...`
- **Коммент:** {{ comment or 'Нет' }}
{% endfor %}
""")

# Сохраняем
with open('docs/database_schema.md', 'w', encoding='utf-8') as f:
    f.write(template.render(
        tables=tables,
        columns=columns,
        mv=mv,
        views=views
    ))
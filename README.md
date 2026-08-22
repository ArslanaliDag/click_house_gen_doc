# ClickHouse Database Documentation Generator

Автоматическое генерирование документации для ClickHouse баз данных в форматах **Markdown** и **HTML**.

## 🎯 Описание

Скрипт подключается к ClickHouse серверу, извлекает информацию о:
- **Таблицах** (структура, размер, количество строк, комментарии)
- **Материализованных представлениях** (запросы, движки)
- **VIEW представлениях** (SQL-определения)

И генерирует красивую документацию с профессиональным дизайном.

## 📋 Требования

- Python 3.8+
- ClickHouse сервер (локальный или удаленный)
- Доступ к системным таблицам ClickHouse

## 🚀 Установка

1. Клонируйте репозиторий:
```bash
git clone <repo-url>
cd click_house_gen_doc
```

2. Установите зависимости:
```bash
pip install -r req.txt
```

## ⚙️ Конфигурация

### Через файл `.env`

Создайте файл `.env` в корне проекта:

```env
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=your_password
CLICKHOUSE_DATABASE=your_database
DOC_FORMAT=md
DOC_OUTPUT_DIR=docs
```

## 📖 Использование

### Генерирование документации в Markdown (по умолчанию)

```bash
python main.py
# или явно
python main.py md
```

Результат: `docs/database_schema.md`

### Генерирование документации в HTML

```bash
python main.py html
```

Результат: `docs/database_schema.html`

### Приоритет настроек

1. **Аргумент командной строки**: `md` или `html`
2. **Переменная окружения**: `DOC_FORMAT`
3. **По умолчанию**: `md`

## 📦 Зависимости

| Пакет | Версия | Назначение |
|-------|--------|-----------|
| `clickhouse-connect` | `>=0.5.0` | Подключение к ClickHouse |
| `jinja2` | `>=3.0` | Генерирование документации из шаблонов |

## 📁 Структура проекта

```
click_house_gen_doc/
├── main.py              # Основной скрипт
├── req.txt              # Зависимости
├── README.md            # Этот файл
├── .env                 # Конфигурация (не отслеживается в git)
├── docs/                # Выходные документы
│   ├── database_schema.md
│   └── database_schema.html
└── temp/                # Временные файлы
```

## 🔧 Настройка подключения к ClickHouse

### Локальный сервер

```env
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=
CLICKHOUSE_DATABASE=default
```

### Удаленный сервер

```env
CLICKHOUSE_HOST=clickhouse.example.com
CLICKHOUSE_PORT=8123
CLICKHOUSE_USER=myuser
CLICKHOUSE_PASSWORD=mypassword
CLICKHOUSE_DATABASE=mydb
```

### Docker контейнер

```env
CLICKHOUSE_HOST=clickhouse
CLICKHOUSE_PORT=8123
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=
CLICKHOUSE_DATABASE=default
```

## 📊 Пример выходных данных

Документация включает:

### Таблицы
- Структура полей (имя, тип, значение по умолчанию, комментарий)
- Параметры таблицы (движок, количество строк, размер, дата изменения)

### Материализованные представления
- SQL-запросы
- Движок
- Комментарии

### VIEW представления
- SQL-определения
- Комментарии

## 🎨 Форматы вывода

### Markdown (`database_schema.md`)
- Чистый текст с таблицами и кодовыми блоками
- Оптимален для Version Control (Git)
- Легко редактировать в текстовых редакторах

### HTML (`database_schema.html`)
- Профессиональный дизайн с темой (светлая/темная)
- Навигация по содержанию
- Адаптивный (мобильный-friendly)
- Готов к печати

## 🐛 Устранение неполадок

### Ошибка подключения
```
Cannot connect to ClickHouse server
```
- Проверьте переменные окружения
- Убедитесь, что ClickHouse сервер запущен
- Проверьте хост, порт и учетные данные

### Файл `.env` не загружается
- Убедитесь, что файл находится в корне проекта
- Проверьте кодировку файла (UTF-8)

### Нет таблиц в документации
- Проверьте доступ к системным таблицам `system.tables` и `system.columns`
- Убедитесь, что базы данных не являются системными (`system`, `INFORMATION_SCHEMA`)

## 📝 Лицензия

MIT

## 👤 Автор

Проект для автоматизации документирования ClickHouse схем.

---

**Последнее обновление**: 2026-08-22

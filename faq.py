"""Генератор FAQ-страницы.

Читает faq.txt (вопросы и ответы) и генерирует faq.html —
интерактивную страницу с аккордеоном и поиском.

Формат faq.txt:
    Q: <вопрос>
    A: <ответ>          (ответ может быть многострочным)

Каждая пара начинается со строки 'Q: ...'. Всё, что идёт после неё
и до следующего 'Q:', считается ответом (необязательный ведущий 'A:'
срезается). Пустые строки внутри ответа сохраняются как переносы.
"""

import os
import re
from pathlib import Path

import markdown
from pygments.formatters import HtmlFormatter

FAQ_TXT = Path("faq.txt")

OUTPUT_DIR = Path(os.getenv("DOC_OUTPUT_DIR", "docs"))
FAQ_HTML = OUTPUT_DIR / "faq.html"


def parse_faq(text):
    """Разбирает faq.txt в список кортежей [(вопрос, ответ), ...]."""
    items = []
    current_q = None
    lines = []

    for raw in text.splitlines():
        line = raw.rstrip()
        # строка 'Q: ...' начинает новый вопрос
        m = re.match(r"^\s*Q\s*:\s*(.*)$", line, re.IGNORECASE)
        if m:
            if current_q is not None:
                items.append((current_q, clean_answer(lines)))
            current_q = m.group(1).strip()
            lines = []
            continue
        if current_q is None:
            # текст до первого 'Q:' игнорируем
            continue
        lines.append(line)

    if current_q is not None:
        items.append((current_q, clean_answer(lines)))

    return items


def clean_answer(lines):
    """Собирает ответ из строк, срезая необязательный ведущий 'A:'."""
    text = "\n".join(lines).strip()
    text = re.sub(r"^\s*A\s*:\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def render_markdown(text):
    """Преобразует Markdown в HTML (код-блоки, таблицы, списки и т.д.)."""
    return markdown.markdown(
        text,
        extensions=["fenced_code", "codehilite", "tables", "sane_lists"],
        output_format="html5",
    )


# CSS для подсветки синтаксиса (Pygments, тема monokai)
PYGMENTS_CSS = HtmlFormatter(style="monokai").get_style_defs(".codehilite")


def render_inline(text):
    """Markdown без обёртки <p> — для отображения вопроса внутри кнопки."""
    return re.sub(r"</?p>", "", render_markdown(text))


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FAQ</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family: Arial, sans-serif; background:#f4f5f7; color:#1e1e2e; padding:24px; max-width:820px; margin:0 auto; }
  h1 { margin-bottom:16px; font-size:26px; }
  .toolbar { display:flex; gap:8px; margin-bottom:18px; }
  #search { flex:1; padding:11px 14px; font-size:15px; border:1px solid #cfd4dc; border-radius:8px; outline:none; background:#fff; }
  #search:focus { border-color:#4a9eff; }
  #toggle-all { padding:11px 14px; font-size:14px; border:1px solid #cfd4dc; border-radius:8px; background:#fff; cursor:pointer; }
  #toggle-all:hover { background:#f0f4ff; }
  #clear-search { padding:11px 12px; font-size:14px; border:1px solid #cfd4dc; border-radius:8px; background:#fff; cursor:pointer; }
  #clear-search:hover { background:#f0f4ff; }
  .faq-item { background:#fff; border:1px solid #e3e6eb; border-radius:8px; margin-bottom:10px; overflow:hidden; }
  .faq-question { width:100%; text-align:left; padding:14px 16px; font-size:16px; font-weight:600; background:none; border:none; cursor:pointer; display:flex; justify-content:space-between; align-items:center; gap:12px; color:#1e1e2e; }
  .faq-question:hover { background:#f0f4ff; }
  .faq-question .arrow { flex-shrink:0; color:#8890a0; transition:transform .2s; transform:rotate(-90deg); }
  .faq-item.open .faq-question .arrow { transform:rotate(0deg); }
  .faq-answer { display:none; padding:0 16px 14px; color:#3d4450; line-height:1.6; }
  .faq-item.open .faq-answer { display:block; }
  .faq-answer p { margin:8px 0; }
  .faq-answer ul, .faq-answer ol { margin:8px 0; padding-left:24px; }
  .faq-answer li { margin:4px 0; }
  .faq-answer a { color:#4a9eff; }
  .faq-answer code { background:#eef0f3; padding:2px 5px; border-radius:4px; font-family:Consolas,Menlo,monospace; font-size:0.9em; color:#c7254e; }
  .faq-answer pre { background:#1e1e2e; color:#e6e6e6; padding:12px 14px; border-radius:8px; overflow-x:auto; margin:10px 0; line-height:1.5; }
  .faq-answer pre code { background:none; padding:0; color:inherit; font-size:0.88em; }
  .faq-answer .codehilite { border-radius:8px; overflow-x:auto; margin:10px 0; }
  .faq-answer .codehilite pre { background:transparent; padding:12px 14px; margin:0; line-height:1.5; }
  .faq-answer h1, .faq-answer h2, .faq-answer h3, .faq-answer h4 { margin:12px 0 6px; }
  .faq-answer table { border-collapse:collapse; margin:10px 0; }
  .faq-answer th, .faq-answer td { border:1px solid #dfe3e8; padding:6px 10px; text-align:left; }
  .faq-question code { background:#eef0f3; padding:1px 5px; border-radius:4px; font-family:Consolas,Menlo,monospace; font-size:0.9em; }
  .no-results { display:none; text-align:center; color:#8890a0; padding:24px; }
  .pagination { display:flex; align-items:center; gap:10px; margin-top:16px; }
  .pagination button { padding:8px 14px; font-size:14px; border:1px solid #cfd4dc; border-radius:8px; background:#fff; cursor:pointer; }
  .pagination button:disabled { opacity:0.4; cursor:not-allowed; }
  .pagination button:not(:disabled):hover { background:#f0f4ff; }
  #page-info { font-size:14px; color:#5a6070; }
__PYGMENTS_CSS__
</style>
</head>
<body>
<h1>❓ FAQ — часто задаваемые вопросы</h1>
<div class="toolbar">
  <input id="search" type="text" placeholder="Поиск по вопросам и ответам...">
  <button id="clear-search" title="Очистить поиск">✕</button>
  <button id="toggle-all">Развернуть все</button>
</div>
<div id="faq">
__ITEMS__
</div>
<div id="no-results" class="no-results">Ничего не найдено</div>
<div class="pagination">
  <button id="prev-page">← Назад</button>
  <span id="page-info">Страница 1 из 1</span>
  <button id="next-page">Вперёд →</button>
</div>
<script>
  // Аккордеон
  document.querySelectorAll('.faq-question').forEach(function (btn) {
    btn.addEventListener('click', function () {
      btn.parentElement.classList.toggle('open');
    });
  });

  // Развернуть / свернуть все
  var toggleAll = document.getElementById('toggle-all');
  toggleAll.addEventListener('click', function () {
    var items = document.querySelectorAll('.faq-item');
    var allOpen = true;
    items.forEach(function (it) { if (!it.classList.contains('open')) allOpen = false; });
    items.forEach(function (it) {
      if (allOpen) it.classList.remove('open');
      else it.classList.add('open');
    });
    toggleAll.textContent = allOpen ? 'Развернуть все' : 'Свернуть все';
  });

  // Поиск + пагинация
  var PAGE_SIZE = 10; // вопросов на странице
  var currentPage = 1;

  var search = document.getElementById('search');
  var noResults = document.getElementById('no-results');
  var pageInfo = document.getElementById('page-info');
  var prevBtn = document.getElementById('prev-page');
  var nextBtn = document.getElementById('next-page');
  var clearBtn = document.getElementById('clear-search');

  function getMatched() {
    var q = search.value.trim().toLowerCase();
    return Array.prototype.filter.call(
      document.querySelectorAll('.faq-item'),
      function (it) { return !q || it.textContent.toLowerCase().indexOf(q) >= 0; }
    );
  }

  function render() {
    var matched = getMatched();
    var totalPages = Math.max(1, Math.ceil(matched.length / PAGE_SIZE));
    if (currentPage > totalPages) currentPage = totalPages;
    if (currentPage < 1) currentPage = 1;

    var start = (currentPage - 1) * PAGE_SIZE;
    var end = Math.min(start + PAGE_SIZE, matched.length);
    var pageSet = new Set(matched.slice(start, end));

    document.querySelectorAll('.faq-item').forEach(function (it) {
      it.style.display = pageSet.has(it) ? '' : 'none';
    });

    pageInfo.textContent = 'Страница ' + currentPage + ' из ' + totalPages + ' · вопросов: ' + matched.length;
    prevBtn.disabled = currentPage <= 1;
    nextBtn.disabled = currentPage >= totalPages;
    noResults.style.display = matched.length === 0 ? 'block' : 'none';
  }

  search.addEventListener('input', function () {
    currentPage = 1;
    render();
  });
  clearBtn.addEventListener('click', function () {
    search.value = '';
    currentPage = 1;
    render();
  });
  prevBtn.addEventListener('click', function () {
    currentPage--;
    render();
  });
  nextBtn.addEventListener('click', function () {
    currentPage++;
    render();
  });

  render();
</script>
</body>
</html>
"""


def build_items_html(items):
    """Формирует HTML для всех пар вопрос-ответ."""
    parts = []
    for q, a in items:
        parts.append(
            '<div class="faq-item">\n'
            f'  <button class="faq-question">{render_inline(q)}<span class="arrow">▾</span></button>\n'
            f'  <div class="faq-answer">{render_markdown(a)}</div>\n'
            '</div>'
        )
    return "\n".join(parts)


def main():
    if not FAQ_TXT.exists():
        raise SystemExit(f"Файл {FAQ_TXT} не найден. Создайте его в формате 'Q: ...' / 'A: ...'.")

    text = FAQ_TXT.read_text(encoding="utf-8")
    items = parse_faq(text)

    if not items:
        raise SystemExit(f"В файле {FAQ_TXT} не найдено ни одного вопроса (ищите строки 'Q: ...').")

    content = (HTML_TEMPLATE
               .replace("__ITEMS__", build_items_html(items))
               .replace("__PYGMENTS_CSS__", PYGMENTS_CSS))
    FAQ_HTML.parent.mkdir(parents=True, exist_ok=True)
    FAQ_HTML.write_text(content, encoding="utf-8")

    print(f"✅ FAQ сгенерирован: {FAQ_HTML} (вопросов: {len(items)})")


if __name__ == "__main__":
    main()

"""Генератор ER-диаграммы для ClickHouse.

Подключается к БД, собирает таблицы и колонки, выводит связи между таблицами
на основе имён FK-колонок (*_id / *_uuid) и генерирует Mermaid-диаграмму
в отдельный файл docs/er_diagram.md.

Важно: в ClickHouse нет внешних ключей, поэтому связи восстанавливаются
эвристически по именам колонок и могут быть неточными/неполными.
"""

import html
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ------------------------------------------------------------
# Загрузка .env
# ------------------------------------------------------------
for line in Path(".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import clickhouse_connect

DB = os.environ["CLICKHOUSE_DATABASE"]
OUTPUT_DIR = Path(os.getenv("DOC_OUTPUT_DIR", "docs"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

client = clickhouse_connect.get_client(
    host=os.environ["CLICKHOUSE_HOST"],
    port=int(os.environ["CLICKHOUSE_PORT"]),
    username=os.environ["CLICKHOUSE_USER"],
    password=os.environ["CLICKHOUSE_PASSWORD"],
    database=DB,
)

# ------------------------------------------------------------
# Таблицы
# ------------------------------------------------------------
tables = client.query(
    "SELECT name, engine FROM system.tables "
    "WHERE database = %(db)s AND engine NOT IN ('View','MaterializedView','Dictionary') "
    "ORDER BY name",
    parameters={"db": DB},
).result_rows

table_names = [t[0] for t in tables]

# ------------------------------------------------------------
# Колонки (только верхнего уровня, без вложенных под-колонок Nested)
# ------------------------------------------------------------
cols = client.query(
    "SELECT table, name, type FROM system.columns "
    "WHERE database = %(db)s "
    "AND table IN (SELECT name FROM system.tables WHERE database = %(db)s "
    "              AND engine NOT IN ('View','MaterializedView','Dictionary')) "
    "AND position(name, '.') = 0 "
    "ORDER BY table, position",
    parameters={"db": DB},
).result_rows

by_table = defaultdict(list)
for table, name, type_ in cols:
    by_table[table].append((name, type_))

# ------------------------------------------------------------
# Нормализация и распознавание связей
# ------------------------------------------------------------
def normalize(s):
    """Нижний регистр, удаление всех не-алфавитно-цифровых символов."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def strip_fk_suffix(name):
    """Возвращает имя сущности без FK-суффикса, либо None."""
    name = name.lower()
    for suf in ("_uuid", "_ids", "_id"):
        if name.endswith(suf):
            return name[: -len(suf)]
    return None


# Сопоставление нормализованного имени сущности -> имя таблицы.
# Покрывает сокращения и разные стили именования.
ALIASES = {
    "area": "areas",
    "areatype": "area_types",
    "userareatype": "area_types",
    "brand": "brands",
    "constructiontype": "construction_types",
    "constrtype": "construction_types",
    "constructionsubtype": "construction_sub_types",
    "constrsubtype": "construction_sub_types",
    "constructionkind": "construction_kinds",
    "displaytype": "display_types",
    "imagetype": "image_types",
    "owner": "owners",
    "place": "places",
    "pricecategory": "price_categories",
    "prohibit": "prohibits",
    "requirement": "tech_requirements",
    "tag": "tags",
    "tagtype": "tag_types",
    "taxtype": "tax_types",
    "techactivity": "tech_activities",
    "activity": "tech_activities",
    "techactivitytype": "tech_activity_types",
    "saleunit": "sale_units",
    "unit": "sale_units",
    "side": "side_letters",
    "sideletter": "side_letters",
    "saledirection": "sale_directions",
    "viewdirection": "view_directions",
    "category": "client_categories",
    "state": "management_states",
    "attribute": "external_attributes",
}

# Неоднозначные колонки, разрешаемые по контексту (таблица, колонка).
CONTEXT_FK = {
    ("clients", "type_id"): "client_types",
    ("tags", "type_id"): "tag_types",
    ("sale_unit_tech_activities", "type_id"): "tech_activity_types",
    ("tech_requirement_links", "item_id"): "tech_requirement_items",
}

normalized_table_names = {normalize(n): n for n in table_names}


def resolve_fk(table, column):
    """Возвращает имя целевой таблицы для FK-колонки или None."""
    if column.lower() == "parent_id":
        return table  # само-ссылка (иерархия)

    ctx = CONTEXT_FK.get((table, column.lower()))
    if ctx is not None:
        return ctx

    entity = strip_fk_suffix(column)
    if entity is None:
        return None

    norm = normalize(entity)

    if norm in ALIASES:
        return ALIASES[norm]

    # прямое / множественное совпадение
    if norm in normalized_table_names:
        return normalized_table_names[norm]
    if norm + "s" in normalized_table_names:
        return normalized_table_names[norm + "s"]
    if norm.endswith("y") and norm[:-1] + "ies" in normalized_table_names:
        return normalized_table_names[norm[:-1] + "ies"]

    return None


# ------------------------------------------------------------
# Собираем связи
# ------------------------------------------------------------
edges = []  # (source_table, target_table, fk_column)
for table in table_names:
    for col_name, _ in by_table[table]:
        target = resolve_fk(table, col_name)
        if target is not None:
            edges.append((table, target, col_name))

edges = sorted(set(edges))

# ------------------------------------------------------------
# Генерация Mermaid erDiagram
# ------------------------------------------------------------
def sanitize_type(t):
    """Приводит тип ClickHouse к безопасному для Mermaid виду."""
    t = t.strip()
    t = re.sub(r"Nullable\(|LowCardinality\(|SimpleAggregateFunction\([^,)]*,?\s*", "", t)
    if "(" in t:
        t = t[: t.index("(")]
    t = t.replace(")", "")
    t = t.strip()
    return t or "String"


def mermaid_name(name):
    """Безопасное имя сущности в Mermaid."""
    return name


# ------------------------------------------------------------
# HTML-шаблон интерактивного просмотра (зум/панорама)
# ------------------------------------------------------------
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ER-диаграмма — __DB__ · Сгенерировано __GENERATED_AT__</title>
<script src="js/mermaid.min.js"></script>
<script src="js/svg-pan-zoom.min.js"></script>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  html, body { width:100%; height:100%; overflow:hidden; background:#1e1e2e; font-family:Arial,sans-serif; }
  #toolbar { position:fixed; top:12px; left:12px; z-index:1000; display:flex; gap:6px; align-items:center; background:rgba(30,30,46,.92); padding:8px 10px; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,.45); }
  #toolbar .ttl { color:#cdd6f4; font-size:13px; margin-right:6px; }
  #toolbar button { background:#45475a; color:#cdd6f4; border:none; border-radius:6px; padding:6px 12px; font-size:14px; cursor:pointer; }
  #toolbar button:hover { background:#585b70; }
  #container { position:fixed; top:0; left:0; right:0; bottom:0; overflow:hidden; }
  .mermaid { width:100%; height:100%; }
  .mermaid svg { max-width:none !important; }
  #toolbar input { background:#313244; color:#cdd6f4; border:1px solid #585b70; border-radius:6px; padding:6px 10px; font-size:13px; outline:none; width:160px; }
  #toolbar input:focus { border-color:#89b4fa; }
  .hint { position:fixed; bottom:10px; left:12px; z-index:1000; color:#7f849c; font-size:12px; background:rgba(30,30,46,.8); padding:4px 10px; border-radius:6px; }
  .meta { position:fixed; bottom:10px; right:12px; z-index:1000; color:#7f849c; font-size:12px; background:rgba(30,30,46,.8); padding:4px 10px; border-radius:6px; }
  g[id^="entity-"] { cursor:pointer; transition:opacity .18s; }
  g[id^="entity-"].dim { opacity:0.12; }
  g[id^="entity-"].hl .entityBox { stroke:#00d0ff !important; stroke-width:2px; filter:drop-shadow(0 0 5px rgba(0,208,255,.6)); }
  path.relationshipLine { cursor:pointer; transition:opacity .18s; }
  path.relationshipLine.dim { opacity:0.08; }
  path.relationshipLine.hl { stroke:#00d0ff !important; stroke-width:3px !important; filter:drop-shadow(0 0 4px rgba(0,208,255,.7)); }
  text.relationshipLabel.dim, rect.relationshipLabelBox.dim { opacity:0.08; }
  text.relationshipLabel.hl { fill:#00d0ff !important; font-weight:bold; }
</style>
</head>
<body>
<div id="toolbar">
  <span class="ttl">ER-диаграмма</span>
  <input id="search" type="text" placeholder="Поиск таблицы…" oninput="searchTable(this.value)">
  <button onclick="clearHighlight()" title="Сбросить подсветку">✕</button>
  <button onclick="pz.zoomIn()" title="Приблизить">+</button>
  <button onclick="pz.zoomOut()" title="Отдалить">-</button>
  <button onclick="pz.reset()" title="Сбросить масштаб">Сброс</button>
  <button onclick="toggleFullscreen()" title="Во весь экран">⛶</button>
</div>
<div class="hint">Клик по таблице — показать её связи · Клик по линии — две таблицы · Пустое место — сброс</div>
<div class="meta">Сгенерировано: __GENERATED_AT__</div>
<div id="container">
  <pre class="mermaid">__MERMAID_SOURCE__</pre>
</div>
<script>
  var pz = null;
  mermaid.initialize({ startOnLoad: false, securityLevel: 'loose', theme: 'dark' });
  mermaid.run({ querySelector: '.mermaid' }).then(function () {
    var svg = document.querySelector('.mermaid svg');
    if (svg) {
      // Нормализуем размеры SVG: mermaid задаёт width="100%" и inline max-width,
      // из-за чего svg-pan-zoom вычисляет неверный масштаб. Задаём явные размеры из viewBox.
      svg.style.maxWidth = 'none';
      svg.style.width = '';
      svg.style.height = '';
      svg.removeAttribute('width');
      svg.removeAttribute('height');
      var vb = svg.viewBox && svg.viewBox.baseVal;
      if (vb && vb.width && vb.height) {
        svg.setAttribute('width', vb.width);
        svg.setAttribute('height', vb.height);
      }
      pz = svgPanZoom(svg, {
        zoomEnabled: true,
        controlIconsEnabled: false,
        fit: true,
        center: true,
        minZoom: 0.05,
        maxZoom: 50,
        dblClickZoomEnabled: true,
        mouseWheelZoomEnabled: true
      });
      pz.fit();
      pz.center();
      buildInteractive();
    }
  });
  window.addEventListener('resize', function () {
    if (pz) { pz.resize(); pz.fit(); pz.center(); }
  });

  // --- Интерактив: подсветка таблиц и связей ---
  var edges = __EDGES_JSON__;
  var nameToEl = {};
  var neighbors = {};

  function buildInteractive() {
    document.querySelectorAll('g[id^="entity-"]').forEach(function (g) {
      var t = g.querySelector('text.entityLabel');
      if (!t) return;
      var name = t.textContent.trim();
      nameToEl[name] = g;
      g.addEventListener('click', function (ev) {
        ev.stopPropagation();
        focusTable(name);
      });
    });
    edges.forEach(function (e) {
      (neighbors[e[0]] = neighbors[e[0]] || []).push(e[1]);
      (neighbors[e[1]] = neighbors[e[1]] || []).push(e[0]);
    });
    document.querySelectorAll('path.relationshipLine').forEach(function (line, i) {
      line.addEventListener('click', function (ev) {
        ev.stopPropagation();
        var e = edges[i];
        if (e) focusPair(e[0], e[1]);
      });
    });
    document.getElementById('container').addEventListener('click', clearHighlight);
  }

  function clearHighlight() {
    document.querySelectorAll('.hl, .dim').forEach(function (el) {
      el.classList.remove('hl', 'dim');
    });
  }

  function applyFocus(focus) {
    Object.keys(nameToEl).forEach(function (n) {
      nameToEl[n].classList.toggle('hl', !!focus[n]);
      nameToEl[n].classList.toggle('dim', !focus[n]);
    });
    document.querySelectorAll('path.relationshipLine').forEach(function (line, i) {
      var e = edges[i];
      var on = e && focus[e[0]] && focus[e[1]];
      line.classList.toggle('hl', on);
      line.classList.toggle('dim', !on);
    });
    document.querySelectorAll('text.relationshipLabel').forEach(function (t, i) {
      var e = edges[i];
      var on = e && focus[e[0]] && focus[e[1]];
      t.classList.toggle('hl', on);
      t.classList.toggle('dim', !on);
    });
    document.querySelectorAll('rect.relationshipLabelBox').forEach(function (r, i) {
      var e = edges[i];
      var on = e && focus[e[0]] && focus[e[1]];
      r.classList.toggle('hl', on);
      r.classList.toggle('dim', !on);
    });
  }

  function focusTable(name) {
    var focus = {};
    focus[name] = true;
    (neighbors[name] || []).forEach(function (n) { focus[n] = true; });
    applyFocus(focus);
  }

  function focusPair(a, b) {
    var focus = {};
    focus[a] = true;
    focus[b] = true;
    applyFocus(focus);
  }

  function searchTable(q) {
    clearHighlight();
    q = q.trim().toLowerCase();
    if (!q) return;
    Object.keys(nameToEl).forEach(function (n) {
      if (n.toLowerCase().indexOf(q) >= 0) {
        nameToEl[n].classList.add('hl');
      } else {
        nameToEl[n].classList.add('dim');
      }
    });
  }

  function toggleFullscreen() {
    if (!document.fullscreenElement) { document.documentElement.requestFullscreen(); }
    else { document.exitFullscreen(); }
  }
</script>
</body>
</html>"""


# ------------------------------------------------------------
# Сборка тела диаграммы (без markdown-оглавления и ограждений)
# ------------------------------------------------------------
body = ["erDiagram"]
for name in table_names:
    body.append(f"    {mermaid_name(name)} {{")
    for col_name, col_type in by_table[name]:
        body.append(f"        {sanitize_type(col_type)} {col_name}")
    body.append("    }")
body.append("")
for source, target, col in edges:
    body.append(f'    {mermaid_name(source)} }}o--|| {mermaid_name(target)} : "{col}"')

mermaid_source = "\n".join(body)

edges_json = json.dumps(edges, ensure_ascii=False)

generated_at = datetime.now().strftime("%d-%m-%Y")

# ------------------------------------------------------------
# Markdown
# ------------------------------------------------------------
md_content = "\n".join([
    "# 🕸️ ER-диаграмма базы данных `%s`" % DB,
    "",
    "**Сгенерировано:** %s" % generated_at,
    "",
    "> Связи восстановлены эвристически по именам колонок (`*_id`, `*_uuid`).",
    "> В ClickHouse нет внешних ключей, поэтому диаграмма может быть неполной.",
    "",
    "```mermaid",
    mermaid_source,
    "```",
    "",
    "## Важные оговорки",
    "",
    "- В ClickHouse **нет внешних ключей**, поэтому связи — эвристические, по именам колонок. Возможны пропуски (колонки `city_id`, `region_id`, `district_id`, `file_id` и т.п. ссылаются на словари/внешние системы, которых нет среди таблиц) и редкие неточности.",
    "- Типы колонок упрощены до «чистых» названий (`Nullable(UUID)` → `UUID`, `Decimal(6,1)` → `Decimal`), чтобы не ломать синтаксис Mermaid.",
    "- Вложенные колонки `Nested` (с точкой в имени, например `packages.digital_rule_id`) исключены.",
]) + "\n"

out_md = OUTPUT_DIR / "er_diagram.md"
out_md.write_text(md_content, encoding="utf-8")

# ------------------------------------------------------------
# HTML (интерактивный просмотр: зум и панорамирование)
# ------------------------------------------------------------
html_content = HTML_TEMPLATE.replace("__DB__", DB).replace(
    "__MERMAID_SOURCE__", html.escape(mermaid_source)
).replace("__EDGES_JSON__", edges_json).replace("__GENERATED_AT__", generated_at)
out_html = OUTPUT_DIR / "er_diagram.html"
out_html.write_text(html_content, encoding="utf-8")

print("✅ ER-диаграмма сгенерирована:")
print(f"   Markdown: {out_md}")
print(f"   HTML:     {out_html}")
print(f"   таблиц: {len(table_names)}, связей: {len(edges)}")



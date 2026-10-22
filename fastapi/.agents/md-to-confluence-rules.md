# Markdown → Confluence Wiki — правила и подводные камни

> Документ-памятка по конвертации Markdown-документов в формат Confluence Wiki Markup (он же Jira format) с помощью `pandoc` + post-processing.
>
> Контекст: проект где много `.md` файлов (документация, ADR, онбординги), которые нужно импортировать в Confluence через Markup macro. Пройдено опытным путём — каждый pattern в таблице ниже реально ломал импорт минимум одной страницы.
>
> Применимо к Confluence Data Center / Server (legacy editor с Markup macro). В Confluence Cloud Markup macro **deprecated с апреля 2026** — там лучше использовать `/markdown` slash-команду напрямую с оригинальным `.md`.

## Содержание

- [Общая схема pipeline](#общая-схема-pipeline)
- [Pandoc-jira команда](#pandoc-jira-команда)
- [Главное правило: что Confluence парсит внутри inline-кода](#главное-правило-что-confluence-парсит-внутри-inline-кода)
- [Таблица замен — pair-маркеры](#таблица-замен--pair-маркеры)
- [Таблица замен — макро-символы и HTML](#таблица-замен--макро-символы-и-html)
- [Анти-паттерны в исходных .md](#анти-паттерны-в-исходных-md)
- [Mermaid-диаграммы](#mermaid-диаграммы)
- [Полный pipeline скрипта](#полный-pipeline-скрипта)
- [Анти-паттерны (не делать так)](#анти-паттерны-не-делать-так)
- [Чек-лист готовности .md к импорту](#чек-лист-готовности-md-к-импорту)

## Общая схема pipeline

```
.md  →  preprocess (mermaid → text)  →  pandoc -t jira  →  sed (theme)  →  clean-escapes.py  →  .txt
        │                                │                  │              │
        │                                │                  │              ├── внутри {{...}}: pair-marker Unicode replacement
        │                                │                  │              ├── внутри {{...}}: { } → entities
        │                                │                  │              ├── внутри {{...}}: < > → ⟨ ⟩
        │                                │                  │              ├── внутри {code}: снять \\X
        │                                │                  │              └── снаружи: убрать лишние \\X
        │                                │                  │
        │                                │                  └── задать тему подсветки (Eclipse / Confluence)
        │                                │
        │                                └── markdown → Jira wiki markup
        │
        └── ```mermaid → ```text (чтобы pandoc не пытался парсить как Java)
```

## Pandoc-jira команда

Базовый вызов:

```bash
pandoc input.md -t jira --wrap=none
```

**Ключевой флаг `--wrap=none`** — без него pandoc вставляет переносы каждые 72 символа, и Jira рендерит их как настоящие `<br/>`. Текст ломается.

Дополнительные шаги — pre-process и post-process. Post-process критичен (см. таблицы ниже).

## Главное правило: что Confluence парсит внутри inline-кода

В Markdown ``одинарный backtick`` превращается pandoc в `{{...}}` (Jira inline code).

**Распространённое заблуждение:** «внутри inline-кода Confluence ничего не парсит».

**Правда:** Confluence wiki-парсер **продолжает искать pair-маркеры** разметки даже внутри `{{...}}` — `*bold*`, `_italic_`, `-strikethrough-`, и так далее. И эти pair'ы могут **пересекать границы** разных `{{...}}` блоков!

Пример битого case:

```
* Геттеры с {{get_*}}, сеттеры с {{set_*}}.
```

Парсер видит первое `*` в `{{get_*}}` как открытие bold → текст между ними → второе `*` в `{{set_*}}` как закрытие bold. Pair `*...*` сложилась через границы `{{...}}` блоков. Рендер ломается.

В Markdown тройные backticks (` ``` ` блок) превращаются в `{code:...}{code}` — там Confluence **действительно** ничего не парсит. Содержимое выводится буквально. Поэтому Python-код с `<`, `*`, `_` внутри тройных backtick'ов **работает** без проблем.

**Вывод:** все pre-processing правила применяются **только внутри `{{...}}`**, не внутри `{code}` блоков.

## Таблица замен — pair-маркеры

Эти символы Confluence Wiki интерпретирует как парную разметку. Внутри `{{...}}` заменяй на Unicode-эквиваленты — выглядят почти идентично, но парсер их не интерпретирует.

| Wiki-символ | Что значит в Confluence | Unicode-замена | Кодпоинт |
|---|---|---|---|
| `*bold*` | жирный | `∗` | U+2217 ASTERISK OPERATOR |
| `_italic_` | курсив | (переписать pattern в `.md`) | — |
| `-strikethrough-` | зачёркнутый | `−` | U+2212 MINUS SIGN |
| `+underline+` | подчёркнутый | `＋` | U+FF0B FULLWIDTH PLUS SIGN |
| `~subscript~` | нижний индекс | `∼` | U+223C TILDE OPERATOR |
| `^superscript^` | верхний индекс | `ˆ` | U+02C6 MODIFIER LETTER CIRCUMFLEX |

### Почему `_italic_` нельзя автоматически заменить

Подчёркивание используется внутри identifier'ов (`snake_case`, `crawl_tasks`, `user_id`). Если заменить все `_` на Unicode — copy-paste из документации не будет работать как Python-код.

**Решение:** руками переписать опасные pattern'ы в исходных `.md`:

- ❌ `<a>_<b>_links` (inline backtick) — `_⟨b⟩_` создаёт italic-пару
- ✅ `tableA_tableB_links` — camelCase placeholder, без подчёркиваний между placeholder'ами

Это касается только **placeholder'ов вида `<X>_<Y>`** внутри одинарных backtick. Реальные Python-identifier'ы (`crawl_tasks`) безопасны — нет pair'а вокруг короткого слова.

## Таблица замен — макро-символы и HTML

Эти символы Confluence интерпретирует как макросы или HTML-теги — даже **внутри inline-кода `{{...}}`**.

| Символ | Что значит в Confluence | Замена внутри `{{...}}` | Почему |
|---|---|---|---|
| `<X>` | HTML-тег (`<a>`, `<b>`, `<i>` и т. д.) | `⟨X⟩` (Unicode U+27E8 / U+27E9) | Confluence нормализует `&lt;X&gt;` HTML entities **обратно** в `<X>` перед парсингом — поэтому entities не помогают. Только Unicode |
| `{Y}` | macro-вызов | `&#123;Y&#125;` (HTML entities) | Для фигурных скобок entities **не нормализуются** обратно — этот трюк работает |
| `\` (backslash) перед обычным символом | избыточный escape от pandoc | убрать backslash | pandoc-jira эскейпит `\\(`, `\\)`, `\\-`, `\\!` и т. д. на всякий случай — Confluence на этом давится |

### Pandoc-escape patterns которые ОБЯЗАТЕЛЬНО снять

Pandoc-jira добавляет backslash перед:

- `\\(` `\\)` — круглые скобки (не реактивны в Confluence wiki) → снять
- `\\-` — дефис → снять
- `\\+` — плюс → снять
- `\\&` — амперсанд → снять
- `\\.` — точка → снять

### Named HTML entities которые pandoc генерит для special chars

Pandoc-jira преобразует **literal backslash** (когда в `.md` есть `\\` чтобы получить один `\`) в HTML entity `&bsol;`. Это валидное HTML5-entity. **Confluence его интерпретирует обратно**, что обычно OK для одного, но **два подряд `&bsol;&bsol;`** ломают парсер (часто бывает в regex pattern'ах с `\\.`, `\\d`, `\\s`).

| Что pandoc генерит | На что заменяем | Кодпоинт | Когда возникает |
|---|---|---|---|
| `&bsol;` | `⧵` Unicode | U+29F5 REVERSE SOLIDUS OPERATOR | regex pattern'ы (`\\.`, `\\d`, `\\w`), Python f-strings, любой literal `\` |
| `&sol;` | `/` literal | — | редко, slash escape |
| `&num;` | `#` literal | — | редко, hash escape |

### Pandoc-escape patterns которые НЕЛЬЗЯ снимать (нужны снаружи code)

- `\\_` — подчёркивание (чтобы не сделалось italic)
- `\\[` `\\]` — квадратные скобки (чтобы не сделалось link)
- `\\{` `\\}` — фигурные скобки (чтобы не сделалось macro)
- `\\*` — звёздочка (чтобы не сделалось bold)
- `\\!` — восклицательный (чтобы не сделалось image)
- `\\|` — pipe (чтобы не разбило таблицу)
- `\\^` `\\~` — для superscript/subscript

### Внутри `{{...}}` и `{code}` снимать ВСЕ backslash escapes

Внутри monospace-блоков escape-ы не нужны (парсер по идее не должен интерпретировать разметку, но он всё равно интерпретирует pair-маркеры — см. выше). Все `\\X` → `X`.

## Анти-паттерны в исходных .md

В исходниках `.md` сразу избегай этих pattern'ов — это избавит от части ручных правок после конверсии.

### 1. Pattern `<X>_<Y>_...` внутри одинарных backtick

❌ Плохо:

```markdown
Шаблон: `<a>_<b>_links`
```

После pandoc: `{{<a>_<b>_links}}`. После замены `<>` на Unicode: `{{⟨a⟩_⟨b⟩_links}}`. Между Unicode-скобками и буквой `b` снаружи `_..._` — Confluence делает italic-пару из `_⟨b⟩_`.

✅ Хорошо:

```markdown
Шаблон: `tableA_tableB_links`
```

Или вообще:

```markdown
Шаблон:

```
<a>_<b>_links
```
```

В тройных backtick всё literal — там можно держать любые placeholder'ы.

### 2. F-string с `{...}` внутри одинарного backtick

❌ Может сломаться:

```markdown
Получаем сообщение: `f"got: {message}"`
```

После замены: `{{f"got: &#123;message&#125;"}}` — обычно работает, но в edge cases (длинные блоки, много вложенностей) парсер может запутаться.

✅ Хорошо — multi-line code block:

````markdown
```python
f"got: {message}"
```
````

### 3. Regex с двойным backslash `\\.\\d\\s` в inline

❌ Опасно (pandoc превращает каждый `\\` в HTML entity `&bsol;`, два подряд ломают Confluence):

```markdown
Регулярка для алёрта: `rabbitmq_queue_messages_ready{queue=~".*\\.dlx"} > 0`
```

После pandoc + clean будет `&bsol;&bsol;.dlx` — два HTML entity подряд, парсер ломается.

✅ Решение: либо обновлённый `clean-jira-escapes.py` (он автоматически заменяет `&bsol;` → `⧵`), либо вынести regex в тройные backtick:

````markdown
Регулярка для алёрта:

```promql
rabbitmq_queue_messages_ready{queue=~".*\\.dlx"} > 0
```
````

### 4. Pattern `->`, `=>` в inline

`->` после конвертации становится `-⟩` (минус + Unicode стрелка вправо). Минус внутри может создать strikethrough pair с другим `-` в соседнем `{{...}}`.

❌ Может ломать:

```markdown
Если функция возвращает `None` — `-> None`. Если ничего — тоже `-> None`.
```

✅ Хорошо:

````markdown
Если функция возвращает `None`:

```python
def f() -> None:
    ...
```
````

Или используй Unicode-стрелку прямо в `.md`:

```markdown
Если функция возвращает `None` — `→ None`. Если ничего — тоже `→ None`.
```

`→` (U+2192) Confluence не интерпретирует.

### 5. HTML-теги-имена в inline (`<a>`, `<b>`, `<i>`, `<span>`, `<div>`)

Эти буквы — distinct HTML-теги для парсера. После замены на `⟨a⟩` визуально похоже, но семантика сохраняется.

❌ Опасно: `<a>`, `<b>`, `<i>`, `<span>`, `<table>`, `<form>` в одинарных backtick.

✅ Безопасно: использовать другие placeholder-имена (`first`, `second`, `T1`, `T2`, `varA`, `varB`).

## Mermaid-диаграммы

Pandoc-jira не умеет рендерить Mermaid. Опции:

### Вариант А — вставить как изображения

1. Конвертировать каждый Mermaid-блок в PNG через `mmdc` (mermaid-cli).
2. В Confluence вставить `+ → Image`.

Скрипт автоматизации:

```bash
#!/usr/bin/env bash
# Извлекает все ```mermaid``` блоки из .md, рендерит в PNG
mmdc -i diagram.mmd -o diagram.png -w 2000
```

### Вариант Б — Mermaid macro в Confluence

Если у вас стоит Confluence Mermaid plugin (Stiltsoft / etc):

1. Удалить блок `{code:...}java\n...\n{code}` со страницы.
2. На месте `/mermaid` slash-команда → вставить содержимое исходного `\`\`\`mermaid` блока.

### Подводный камень — `mmdc` требует Chrome

`mermaid-cli` использует puppeteer, которому нужен Chrome/Chromium. На macOS:

- `brew install --cask google-chrome`
- В puppeteer-config указать путь: `{"executablePath": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "args": ["--no-sandbox"]}`

Это решает проблему `Could not find Chrome (ver. X.Y.Z)` при первом запуске.

### Mermaid синтаксис — что ломает рендер

- Круглые скобки `(...)` внутри labels — нужны кавычки: `["text (with parens)"]`
- Subgraph titles со скобками — нужны кавычки: `subgraph X ["title (note)"]`

## Полный pipeline скрипта

### convert-md-to-confluence.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-.}"
CODE_THEME="${2:-Eclipse}"   # Confluence | Eclipse | Solarized | FadeToGrey | Emacs | Midnight

# 1. pre-process: ```mermaid → ```text (чтобы pandoc не парсил Gantt-двоеточия как разметку)
# 2. pandoc -t jira --wrap=none
# 3. sed: подменить тему code-блоков
# 4. python3 clean-jira-escapes.py — pair-marker замены

find "$TARGET" -type f -name "*.md" -not -path "*/mermaid-rendered/*" | while read MDFILE; do
    TXTFILE="${MDFILE%.md}.txt"

    PREPROC=$(mktemp)
    sed 's/^```mermaid$/```text/' "$MDFILE" > "$PREPROC"

    pandoc "$PREPROC" -t jira --wrap=none \
        | sed "s/{code:/{code:theme=${CODE_THEME}|/g" \
        | python3 "$SCRIPT_DIR/clean-jira-escapes.py" \
        > "$TXTFILE"

    rm -f "$PREPROC"
done
```

### clean-jira-escapes.py

```python
#!/usr/bin/env python3
"""Post-process pandoc-jira output для Confluence Wiki."""

import re
import sys


CHARS_NEVER_ESCAPE = "()-+&."  # эти эскейпы pandoc лишние


def fix_inline_code(match: re.Match) -> str:
    """Внутри {{...}}: снять backslash + заменить pair-маркеры на Unicode."""
    inner = match.group(0)

    # 1. Снять все backslash-эскейпы
    inner = re.sub(r"\\(.)", r"\1", inner)

    open_, close_ = "{{", "}}"
    if not (inner.startswith(open_) and inner.endswith(close_)):
        return inner

    body = inner[len(open_) : -len(close_)]

    # 2. { } → HTML entities (Confluence НЕ нормализует обратно)
    body = body.replace("{", "&#123;").replace("}", "&#125;")

    # 3. < > → Unicode angles (Confluence нормализует &lt; &gt; обратно — поэтому Unicode)
    body = body.replace("<", "⟨").replace(">", "⟩")
    body = body.replace("&lt;", "⟨").replace("&gt;", "⟩")  # миграция

    # 4. Pair-маркеры разметки → Unicode-аналоги
    body = body.replace("*", "∗")  # bold → asterisk operator
    body = body.replace("-", "−")  # strikethrough → minus sign
    body = body.replace("+", "＋")  # underline → fullwidth plus
    body = body.replace("~", "∼")  # subscript → tilde operator
    body = body.replace("^", "ˆ")  # superscript → modifier circumflex

    # 5. Named HTML entities — pandoc генерит их для literal backslash и т. д.
    body = body.replace("&bsol;", "⧵")  # backslash → REVERSE SOLIDUS OPERATOR (U+29F5)
    body = body.replace("&sol;", "/")  # forward slash → literal
    body = body.replace("&num;", "#")  # number sign → literal

    return open_ + body + close_


def fix_code_block(match: re.Match) -> str:
    """Внутри {code:...}{code}: только снять backslash. Pair-маркеры не трогаем — там парсер не интерпретирует."""
    return re.sub(r"\\(.)", r"\1", match.group(0))


def main() -> None:
    content = sys.stdin.read()

    # Внутри {{...}}
    inline_pat = re.compile(r"{{.*?}}(?!})", re.DOTALL)
    for _ in range(5):
        new = inline_pat.sub(fix_inline_code, content)
        if new == content:
            break
        content = new

    # Внутри {code:...}{code}
    content = re.sub(
        r"{code[^}]*}.*?{code}",
        fix_code_block,
        content,
        flags=re.DOTALL,
    )

    # Снаружи — убрать заведомо лишние эскейпы
    for ch in CHARS_NEVER_ESCAPE:
        content = content.replace("\\" + ch, ch)

    sys.stdout.write(content)


if __name__ == "__main__":
    main()
```

## Анти-паттерны (не делать так)

### 1. Не заменять `_` на Unicode внутри `{{...}}`

Сломает copy-paste Python-кода. Решать через переписывание pattern в `.md`.

### 2. Не использовать HTML entities для `<` `>`

Confluence Cloud / DC **нормализует HTML entities обратно** перед парсингом wiki-разметки. То есть `&lt;a&gt;` снова станет `<a>` и Confluence воспримет как HTML-тег.

Исключение: фигурные скобки. Для них entities **работают** — `&#123;` и `&#125;` не нормализуются обратно.

### 3. Не оставлять Mermaid-блоки как code

Это будет код-блок с текстом Mermaid-исходника, а не диаграмма. Конвертировать в PNG или использовать Mermaid macro.

### 4. Не рисовать двунаправленную стрелку там, где связь односторонняя

Двунаправленная dotted-стрелка `<-.->` — валидный синтаксис Mermaid (проверено на 11.16.0), запрета на неё нет. Но ставить её «на всякий случай» не надо: она скрывает реальное направление потока. Если связь односторонняя — рисуй `-.->`.

### 5. Не использовать `(...)` в labels Mermaid без кавычек

`[node (note)]` → должно быть `["node (note)"]`.

## Чек-лист готовности .md к импорту

Перед конверсией .md → .txt:

- [ ] Удалены или переписаны pattern'ы `<X>_<Y>` в одинарных backtick (использовать camelCase или multi-line block)
- [ ] Mermaid-блоки в тройных backtick (` ```mermaid `), не в одинарных
- [ ] Mermaid: направление стрелок соответствует реальному потоку (двунаправленные — только там, где связь действительно двусторонняя)
- [ ] Mermaid: скобки в labels обёрнуты в кавычки (`["text (note)"]`)
- [ ] Pandoc 2.0+ установлен (`pandoc --version`)
- [ ] `clean-jira-escapes.py` в той же папке что и скрипт конверсии

После конверсии — проверить:

- [ ] Все `<X>` placeholder'ы в одинарных backtick → стали `⟨X⟩` Unicode (внутри `{{...}}`)
- [ ] Все `*`, `-`, `+`, `~`, `^` внутри `{{...}}` → стали Unicode-аналоги
- [ ] Нет `\\(`, `\\)`, `\\-` снаружи code (убраны)
- [ ] Mermaid-блоки помечены ⚠ в логе скрипта (нужно отдельно вставить через `/mermaid` macro или как PNG)

## Связанные документы

- [Confluence Wiki Markup spec (Data Center)](https://confluence.atlassian.com/doc/confluence-wiki-markup-251003035.html) — официальная документация по синтаксису
- [Pandoc `jira` writer](https://pandoc.org/MANUAL.html#jira) — официальная документация по writer'у
- [mermaid-cli](https://github.com/mermaid-js/mermaid-cli) — рендеринг Mermaid в PNG/SVG

## Лицензия и использование

Этот документ — результат опытного выяснения проблем при конверсии большой документационной базы (45+ Markdown-файлов) в Confluence Wiki. Все pattern'ы в таблицах протестированы на реальных кейсах. Если найдёшь дополнительный pattern, который ломает импорт — добавь в таблицу.

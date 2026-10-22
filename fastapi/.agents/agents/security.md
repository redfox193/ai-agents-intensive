# Политика безопасности

## Секреты

- `AGENTPLATFORM_API_KEY`, токены БД, пароли — **только в `~/.zshenv` или `.env`** (который в `.gitignore`).
- В код, конфиги, тесты, документацию ключ **не попадает** — везде `os.environ["AGENTPLATFORM_API_KEY"]` или подстановка через `${AGENTPLATFORM_API_KEY}` в шаблонах.
- В Continue ключ задаётся через секрет-плейсхолдер `${{ secrets.AGENTPLATFORM_API_KEY }}`, а не вписывается напрямую.
- Если ключ утёк (попал в git history, в Slack, в скриншот) — немедленно **disable** его в AgentPlatform Settings → Keys и создай новый.
- На каждый ключ — отдельный credit limit (минимум, ровно под задачу). На дефолтный воркшоп-ключ — $5.

## Bandit

- `bandit` запускается на каждом коммите через pre-commit (см. Шаг 5.2).
- Если bandit нашёл проблему в чужом коде (не из текущего diff) — **отдельный коммит** `[manual] fix(security): <описание на русском>`, потом штатный коммит фичи (тэг английский, описание — на русском).
- Никаких `# nosec` без комментария с пояснением **почему** именно эта конструкция безопасна в этом контексте.

## pip-audit

- `pip-audit` запускается на каждом коммите через pre-commit (см. Шаг 5.2).
- На каждое CVE в зависимости — отдельный коммит `[manual] chore(deps): обновить <package> до X.Y.Z для CVE-XXXX-XXXXX` (тэг английский, описание — на русском).
- Не смешивать security-fix с фичей в одном коммите.

## Pre-commit хуки — никаких обходов

Список **запрещённых** способов обойти pre-commit-проверки. Все они дают одно и то же — коммит с непроверенным кодом. Применять их нельзя ни при каких обстоятельствах:

- `git commit --no-verify` — пропускает все хуки полностью.
- `PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit ...` — пропускает хуки, если конфига нет. Если ты видишь эту переменную в команде — значит конфиг **потерян** (например, лежит untracked и попал в `git stash -u`). Реакция — **восстановить конфиг**, не обходить.
- `SKIP=hook1,hook2 git commit ...` — пропускает указанные хуки. Никогда: падающий хук чинят, а не выключают.
- `pre-commit uninstall` с целью «временно отключить» — снимает хук вообще. Возврат через `pre-commit install` после починки.

Если хук падает на чужом коде, который не относится к твоей задаче — **отдельный security-коммит** перед твоей фичей (политика «по CVE отдельным коммитом» выше). Никогда — обход.

Если `.pre-commit-config.yaml` физически отсутствует в проекте — **остановиться**, восстановить файл из git-истории (`git show HEAD:.pre-commit-config.yaml > .pre-commit-config.yaml`) или из стэша, и только после этого продолжать.

## Опасные конструкции — не использовать

- `eval` / `exec` от пользовательского ввода.
- `subprocess.run(..., shell=True)` — только списком аргументов без shell.
- `yaml.load(...)` без `Loader=yaml.SafeLoader` — только `yaml.safe_load`.
- Захардкоженные пароли / API-ключи / connection strings.
- `pickle.loads` от недоверенного источника.

***

## Security-паттерны Python — расширенный набор

Это **прикладные** паттерны: что чаще всего ломается в Python-сервисах и как этого избежать. bandit ловит часть из них, но не все — поэтому правила записаны явно, агент ссылается на них в code review.

### 1. SSRF (Server-Side Request Forgery)

Когда сервис делает исходящий HTTP по URL, который **частично или полностью контролирует пользователь** (preview ссылки, webhook URL, импорт RSS, OAuth callback, image proxy), это потенциальный SSRF.

**Атака:** пользователь даёт URL вида `http://169.254.169.254/latest/meta-data/...` (AWS metadata), `http://10.0.0.5:6379/` (internal Redis), `http://localhost:9090/` (внутренний админ-эндпоинт).

**Правила:**

- Allow-list схем (`http`, `https`) — никаких `file://`, `gopher://`, `ftp://`.
- **DNS resolve → проверка по IP**, не по hostname (защита от DNS rebinding). Отвергай `ip.is_private / is_loopback / is_link_local / is_multicast / is_reserved`.
- Запрети редиректы (`follow_redirects=False`) или валидируй каждый промежуточный URL по тем же правилам.
- Жёсткий `httpx.Timeout(connect, read, write, pool)`, ограничение `max_bytes` на ответ (стримом, не в память целиком).

~~~python
import ipaddress
import socket

import httpx

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_MAX_BYTES = 10 * 1024 * 1024


def _is_public_ip(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def fetch_preview(url: str) -> bytes:
    parsed = httpx.URL(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError("scheme not allowed")
    infos = socket.getaddrinfo(parsed.host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    ips = {info[4][0] for info in infos}
    if not all(_is_public_ip(ip) for ip in ips):
        raise ValueError("resolved to non-public ip")
    timeout = httpx.Timeout(connect=2.0, read=5.0, write=5.0, pool=2.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        async with client.stream("GET", url) as r:
            r.raise_for_status()
            buf = bytearray()
            async for chunk in r.aiter_bytes():
                buf.extend(chunk)
                if len(buf) > _MAX_BYTES:
                    raise ValueError("response too large")
            return bytes(buf)
~~~

### 2. Path traversal

Когда путь к файлу формируется из пользовательского ввода (upload, download by name, read template by id) — атакующий передаёт `../../../../etc/passwd`.

**Правила:**

- Резолви и проверяй принадлежность к root-каталогу: `Path.resolve()` + `is_relative_to(root)` (Python 3.9+).
- Allow-list символов в имени, если можно (`^[a-zA-Z0-9._-]+$`).
- Никаких `..` и абсолютных путей в имени — отвергай сразу.

~~~python
from pathlib import Path

_UPLOADS = Path("/var/uploads").resolve()


def read_user_file(name: str) -> str:
    candidate = (_UPLOADS / name).resolve()
    if not candidate.is_relative_to(_UPLOADS):
        raise ValueError("path traversal attempt")
    if not candidate.is_file():
        raise FileNotFoundError(name)
    return candidate.read_text(encoding="utf-8")
~~~

### 3. Unsafe deserialization

`pickle`, `yaml.load` без `SafeLoader`, `xml.etree` с внешними entities, `jsonpickle` — **исполняют код** на untrusted input.

| Формат | Untrusted input | Trusted input |
|---|---|---|
| `pickle` / `marshal` / `shelve` / `dill` | **Никогда** | Только для собственных контролируемых данных |
| `yaml.load()` | **Никогда** | `yaml.safe_load()` всегда |
| `xml.etree.ElementTree` / `lxml` без `resolve_entities=False` | **Никогда** (XXE) | `defusedxml` или explicit disable external entities |
| `jsonpickle` | **Никогда** | `pydantic` или `dataclasses_json` |
| `eval` / `exec` на user input | **Никогда** | `ast.literal_eval()` для безопасного подмножества |

### 4. File upload — hardening

При приёме файла от пользователя:

- **Проверяй MIME по содержимому**, не по заголовку `Content-Type` (он от клиента — untrusted). Через `python-magic` / `magic.from_buffer(raw, mime=True)`.
- Ограничивай размер **до** того, как файл попадёт в память — стриминговое чтение с early reject.
- Имя файла санитайзируй или **генерируй заново** (UUID). Никогда не используй raw имя для пути на диске.
- Храни **вне webroot**, отдавай через контроллер с авторизацией.
- Для картинок — передекодируй через Pillow (`Image.verify()` + повторное открытие + `convert("RGB")` + `save`). Это снимает payload'ы, зашитые в exif / metadata / polyglot-форматы.

### 5. TLS verification — никогда не отключать

~~~python
# ❌ MITM-vulnerable
httpx.get(url, verify=False)
requests.get(url, verify=False)
~~~

**Допустимо** отключать только: (1) в тестах с локальным mock-сервером (явный `# noqa` + комментарий), (2) для internal CA — `verify="/path/to/internal-ca.pem"`, **не** `False`.

### 6. Request timeouts — всегда

`requests.get(url)` без `timeout=` — анти-паттерн. Запрос может висеть бесконечно, GIL-поток зависает, в async — таска не отпускает event loop.

~~~python
# ✅ requests
r = requests.get(url, timeout=(2.0, 10.0))  # (connect, read)

# ✅ httpx
timeout = httpx.Timeout(connect=2.0, read=10.0, write=10.0, pool=2.0)
async with httpx.AsyncClient(timeout=timeout) as client:
    r = await client.get(url)
~~~

### 7. JWT / OAuth

**JWT:**

- **Никогда не доверяй `alg: none`** — explicit reject.
- При `decode` указывай **ожидаемый** алгоритм: `algorithms=["RS256"]`, не wildcard.
- Verify `exp` / `nbf` / `iat` / `aud` / `iss` — особенно в multi-tenant.
- Ключи в KMS / vault, не в `.env` для prod.
- В payload — **только идентификаторы** (sub, aud, iss). Никаких секретов: payload base64, не зашифрован.

~~~python
import jwt
from jwt.exceptions import InvalidTokenError

try:
    payload = jwt.decode(
        token,
        public_key,
        algorithms=["RS256"],
        audience="my-service",
        issuer="https://auth.example.com/",
        options={"require": ["exp", "iat", "sub", "aud", "iss"]},
    )
except InvalidTokenError as e:
    raise AuthError("invalid token") from e
~~~

**OAuth:**

- **PKCE** обязательно для public-клиентов (mobile, SPA).
- **`state`** обязательно (CSRF-защита authorization request).
- `redirect_uri` — точное совпадение с allow-list (не префикс, не подстрока).
- `nonce` в OIDC `id_token`.
- `refresh_token` — **никогда** в браузер. Public-клиенты: PKCE + short-lived access_token.

### 8. Subprocess sandboxing

- **`shell=False`** всегда. `subprocess.run([prog, arg1, arg2], ...)`, не строка.
- **Никогда не интерполируй user input в команду строкой** — только в args list.
- Абсолютный путь к бинарнику или `which` — не доверяй PATH.
- Жёсткий `timeout=`.
- Ограничь environment: `env={"PATH": "/usr/bin"}`, не передавай весь `os.environ`.

~~~python
# ❌ injection
subprocess.run(f"convert {user_file} out.jpg", shell=True)

# ✅
CONVERT = "/usr/bin/convert"
subprocess.run(
    [CONVERT, str(user_file), str(out)],
    check=True,
    timeout=30,
    capture_output=True,
    env={"PATH": "/usr/bin"},
)
~~~

### 9. Secure temp files

- `tempfile.NamedTemporaryFile` / `TemporaryDirectory()` — context manager, авто-cleanup.
- **Никогда `tempfile.mktemp()`** — race condition (имя возвращается до создания файла).
- Никаких `/tmp/work_{os.getpid()}.txt` — predictable path = race condition + permission tricks.

### 10. Криптография

- **Никогда** не пиши свою crypto. `cryptography` (стандартный API), `hazmat` — только с code review.
- **Никогда `hashlib.md5` / `sha1` для security** (passwords, tokens, signatures). Они для checksum, не для безопасности.
- Пароли: `passlib.hash.bcrypt` или `argon2-cffi`.
- HMAC / сравнение секретов: `hmac.compare_digest(a, b)` (constant-time), **не** `a == b` (timing attack).
- Random для security: `secrets.token_urlsafe(32)` / `secrets.SystemRandom`, **не** `random` (predictable).

~~~python
import hmac
import secrets


def make_token() -> str:
    return secrets.token_urlsafe(32)


def verify_token(provided: str, expected: str) -> bool:
    return hmac.compare_digest(provided.encode(), expected.encode())
~~~

***

## Что этот файл НЕ покрывает

- **Авторизация / authentication на уровне дизайна** (RBAC vs ABAC, multi-tenant boundaries) — это уровень ADR (`.agents/agents/docs.md`), не code style.
- **Threat modeling, pentest playbook** — отдельная дисциплина, выходит за рамки воркшопа.
- **IaC security** (S3 Block Public Access, IAM wildcards, security groups) — за рамками проекта.

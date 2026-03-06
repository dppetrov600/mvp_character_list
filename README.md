# Генератор персонажа D&D 5e (SRD-only) с локальной LLM и UI

FastAPI-сервис, CLI и веб-UI для генерации листа персонажа D&D 5e по уровню и краткому описанию.
Механика строится **только на SRD-данных** через `https://www.dnd5eapi.co/` (без PHB и платных источников).

---

## Ключевые гарантии

- **SRD-only**: никаких попыток получать/воссоздавать PHB или другой коммерческий контент
- **Детерминированная механика**:
  - point buy (27), выбор навыков из разрешённых `proficiency_choices`
  - применение ASI на нужных уровнях (cap 20)
  - HP по фиксированному среднему (hit die + CON_mod)
  - AC по броне/щиту из экипировки (с резервным сценарием)
  - стартовое снаряжение: фиксированное + опции выбора, с возможностью ручного выбора в UI
- **LLM используется только как UX-слой**, а не “движок правил”:
  - извлечение предпочтений из `description` (роль, приоритет статов, желаемые навыки)
  - генерация короткой предыстории
  - при сбое LLM сервис продолжает работать (fallback эвристики)

---

## Возможности

- Генерация персонажа 1–20 уровня по классу SRD и описанию
- Оптимизация характеристик и ASI под класс/роль/предпочтения
- Выбор навыков из легальных вариантов (с учётом предпочтений и сильных статов)
- Стартовое снаряжение:
  - автоподбор по скорингу
  - **ручной выбор опций** через UI
- Локальная LLM без дообучения:
  - Ollama (рекомендуется для ноутбука/CPU)
  - OpenAI-compatible API (подходит llama.cpp server / vLLM)
- Веб-UI для удобного просмотра результата + сырой JSON

---

## Технологии и стек

**Backend / API**
- Python 3.11+
- FastAPI, Uvicorn
- httpx (async), timeouts/retries
- Pydantic (схемы + валидация контрактов)
- SQLite-кэш (DND API + кэш LLM-ответов)
- Статический UI (HTML/CSS/vanilla JS)

**LLM**
- Ollama backend
- OpenAI-compatible backend (llama.cpp server / vLLM)

**Качество**
- pytest (юнит-тесты и API-тесты)
- ruff + black (линт/формат)
- отсутствие внешних HTTP вызовов в тестах (моки)

---

## Структура проекта

- `app/api/main.py` - инициализация FastAPI и lifespan
- `app/api/routes.py` - `/`, `/health`, `/reference/*`, `/generate`
- `app/core/models.py` - контракты запроса/ответа (CharacterSpec/CharacterSheet)
- `app/core/optimizer.py` - генерация персонажа (point-buy, ASI, навыки, экип, derived)
- `app/core/equipment.py` - подготовка вариантов стартового снаряжения для API/UI
- `app/core/rules.py` - расчёт HP/AC/бонуса мастерства
- `app/data/dnd_client.py` - клиент dnd5eapi + кэш
- `app/data/mappers.py` - разбор SRD структур (skills/equipment options)
- `app/llm/providers.py` - адаптеры Ollama и OpenAI-compatible API
- `app/llm/service.py` - оркестрация LLM, кэш, fallback эвристики
- `app/web/index.html` - UI
- `app/web/styles.css` - стили UI
- `app/web/app.js` - логика UI

---

## Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

> Если extras `dev` не настроены, установите вручную: `pip install fastapi uvicorn httpx pydantic pytest ruff black`.

---

## Запуск API и UI

```bash
uvicorn app.api.main:app --reload
```

Открыть UI: `http://127.0.0.1:8000/`

Проверка health:

```bash
curl localhost:8000/health
```

---

## UI

UI позволяет:
- выбрать уровень, класс, роль и описание
- включить/выключить LLM
- задать LLM-настройки на запрос:
  - `backend`: `ollama` или `openai-compatible`
  - `base_url`
  - `model`
  - `timeout_seconds`
- увидеть фиксированное стартовое снаряжение и **вручную выбрать** варианты в блоках «выберите N»
- посмотреть backstory, decisions и сырой JSON

UI работает поверх того же SRD-only эндпоинта `/generate`.

---

## Эндпоинты справочников

- `GET /reference/classes` - список классов SRD
- `GET /reference/class/{class_index}/equipment-options` - стартовое снаряжение и варианты выбора в формате, удобном для UI

---

## Генерация персонажа (API)

Пример запроса:

```bash
curl -X POST localhost:8000/generate   -H 'Content-Type: application/json'   -d '{
    "level": 5,
    "class_index": "rogue",
    "role": "skills",
    "description": "Скрытный разведчик и взломщик с тяжёлым прошлым",
    "generation_method": "point_buy",
    "seed": 42
  }'
```

### Опциональные поля `CharacterSpec`

- `llm_config`:
  - `enabled`
  - `backend` (`ollama` / `openai` / `openai-compatible`)
  - `base_url`
  - `model`
  - `timeout_seconds`
- `selected_equipment_choices`: список `option_id` выбранных вариантов снаряжения

Старые клиенты (которые отправляют только `level/class_index/description/role`) полностью совместимы.

---

## Настройка LLM через переменные окружения

- `LLM_ENABLED=0|1`
- `LLM_BACKEND=ollama|openai|openai-compatible`
- `LLM_BASE_URL` (по умолчанию для ollama: `http://localhost:11434`)
- `LLM_MODEL` (обязателен при `LLM_ENABLED=1`)
- `LLM_TIMEOUT_SECONDS` (по умолчанию `30`)

Поведение `use_llm`:
- `true` - принудительно включить LLM для запроса
- `false` - принудительно отключить LLM для запроса
- `null`/не передано - брать из настроек сервиса

---

## Ollama (рекомендуется для ноутбука/CPU)

Пример:

```bash
ollama serve
ollama pull llama3.1:8b-instruct-q4_K_M

export LLM_ENABLED=1
export LLM_BACKEND=ollama
export LLM_BASE_URL=http://localhost:11434
export LLM_MODEL=llama3.1:8b-instruct-q4_K_M
```

> Практично для ноутбука: 7B/8B instruct-модель в Q4 обычно помещается в 8–12 ГБ RAM под веса + запас на контекст.

---

## OpenAI-compatible (llama.cpp server / vLLM)

```bash
export LLM_ENABLED=1
export LLM_BACKEND=openai-compatible
export LLM_BASE_URL=http://localhost:8001
export LLM_MODEL=your-model-name
```

---

## CLI

```bash
python -m app.cli --level 5 --class-index rogue --role skills --description "скрытный разведчик" --seed 42
```

С LLM:

```bash
python -m app.cli --level 5 --class-index rogue --description "скрытный разведчик" --use-llm
```

---

## Тесты

```bash
pytest
```

Покрытие включает:
- корректность point-buy
- выбор навыков с учётом предпочтений
- разбор вариантов снаряжения
- применение ASI и ограничение 20
- формулу HP
- расчёт AC с бронёй/щитом и резервным сценарием
- извлечение предпочтений LLM + кэш
- fallback при ошибках LLM без падения `/generate`
- UI/справочники/валидацию ручного выбора снаряжения

---

## Кэш

- Кэш DND API: `.cache/dnd_api.sqlite3`
- Кэш LLM: `.cache/llm_cache.sqlite3`

Тесты не выполняют внешние HTTP-запросы.

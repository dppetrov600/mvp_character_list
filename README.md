# Генератор персонажа D&D 5e (SRD-only, MVP+)

FastAPI-сервис и CLI для генерации листа персонажа D&D 5e на основе **только SRD-данных** через `https://www.dnd5eapi.co/`.

## Гарантии

- Только SRD-контент (без PHB и платных источников)
- Детерминированная механика: point-buy, ASI, HP, AC, навыки и стартовое снаряжение
- LLM используется только для:
  - извлечения предпочтений из `description`
  - генерации короткой предыстории

## Технологии

- Python 3.11+
- FastAPI + Uvicorn
- httpx (async)
- pydantic
- sqlite-кэш
- pytest, ruff, black

## Структура проекта

- `app/api/main.py` — инициализация FastAPI и lifespan
- `app/api/routes.py` — `/`, `/health`, `/reference/*`, `/generate`
- `app/core/models.py` — контракты запроса/ответа
- `app/core/optimizer.py` — основная генерация (ASI/навыки/снаряжение/derived)
- `app/core/equipment.py` — подготовка вариантов стартового снаряжения для API/UI
- `app/core/rules.py` — расчёт HP/AC/бонуса мастерства
- `app/data/dnd_client.py` — клиент dnd5eapi + кэш
- `app/data/mappers.py` — разбор структур SRD по навыкам/экипировке
- `app/llm/providers.py` — адаптеры Ollama и OpenAI-compatible API
- `app/llm/service.py` — оркестрация LLM, кэш, резервная эвристика
- `app/web/index.html` — UI
- `app/web/styles.css` — стили UI
- `app/web/app.js` — логика UI

## Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Запуск API и UI

```bash
uvicorn app.api.main:app --reload
```

Открыть UI:

```bash
http://127.0.0.1:8000/
```

Проверка health:

```bash
curl localhost:8000/health
```

## UI

UI позволяет:

- выбрать уровень, класс, роль и описание
- включить/выключить LLM
- задать LLM-настройки в запросе:
  - `backend`: `ollama` или `openai-compatible`
  - `base_url`
  - `model`
  - `timeout_seconds`
- увидеть фиксированное стартовое снаряжение и вручную выбрать варианты в блоках «выберите N»

UI работает поверх того же SRD-only эндпоинта `/generate`.

## Эндпоинты справочников

- `GET /reference/classes` — список классов SRD
- `GET /reference/class/{class_index}/equipment-options` — стартовое снаряжение и варианты выбора в виде, удобном для UI

## Генерация персонажа (API)

Пример:

```bash
curl -X POST localhost:8000/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "level": 5,
    "class_index": "rogue",
    "role": "skills",
    "description": "Скрытный разведчик и взломщик с тяжёлым прошлым",
    "generation_method": "point_buy",
    "seed": 42
  }'
```

### Новые опциональные поля в `CharacterSpec`

- `llm_config`:
  - `enabled`
  - `backend` (`ollama` / `openai` / `openai-compatible`)
  - `base_url`
  - `model`
  - `timeout_seconds`
- `selected_equipment_choices`: список `option_id` выбранных вариантов снаряжения

Старые клиенты (которые отправляют только `level/class_index/description/role`) полностью совместимы.

## Настройка LLM через переменные окружения

- `LLM_ENABLED=0|1`
- `LLM_BACKEND=ollama|openai`
- `LLM_BASE_URL` (по умолчанию для ollama: `http://localhost:11434`)
- `LLM_MODEL` (обязателен при `LLM_ENABLED=1`)
- `LLM_TIMEOUT_SECONDS` (по умолчанию `30`)

Поведение `use_llm`:

- `true` — принудительно включить LLM для запроса
- `false` — принудительно отключить LLM для запроса
- `null`/не передано — брать из настроек сервиса

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

## OpenAI-compatible (llama.cpp server / vLLM)

```bash
export LLM_ENABLED=1
export LLM_BACKEND=openai
export LLM_BASE_URL=http://localhost:8001
export LLM_MODEL=your-model-name
```

## CLI

```bash
python -m app.cli --level 5 --class-index rogue --role skills --description "скрытный разведчик" --seed 42
```

С LLM:

```bash
python -m app.cli --level 5 --class-index rogue --description "скрытный разведчик" --use-llm
```

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
- резервная эвристика при ошибках LLM без падения `/generate`
- UI/справочники/валидацию ручного выбора снаряжения

## Примечания

- Кэш DND API: `.cache/dnd_api.sqlite3`
- Кэш LLM: `.cache/llm_cache.sqlite3`
- Тесты не должны выполнять внешние HTTP-запросы

# mlops-practice

<a target="_blank" href="https://cookiecutter-data-science.drivendata.org/">
    <img src="https://img.shields.io/badge/CCDS-Project%20template-328F97?logo=cookiecutter" />
</a>

MLOps course practice project.

## Установка и запуск

Требования: Linux или macOS (на Windows — WSL), `make`, `curl`, `git`.
Python и uv ставить заранее не нужно: `make setup` установит [uv](https://docs.astral.sh/uv/),
если его нет, а uv сам скачает нужную версию Python (зафиксирована в `.python-version`).

```bash
git clone https://github.com/2made1ra/mlops-practice.git
cd mlops-practice
make setup   # поднять окружение с нуля
make check   # прогнать все проверки
```

Доступные команды:

| Команда        | Что делает                                                                          |
|----------------|-------------------------------------------------------------------------------------|
| `make setup`   | Ставит uv (если нет), Python и все зависимости из `uv.lock` в `.venv`, устанавливает git-хуки pre-commit |
| `make check`   | Проверяет стиль (`ruff check`, `ruff format --check`) и типы (`mypy`). Ничего не исправляет: код возврата 0 — ошибок нет, иначе — есть |
| `make format`  | Автоматически исправляет стиль (изменяет файлы)                                     |
| `make clean`   | Удаляет `__pycache__` и кеши инструментов                                            |
| `make s3-up`   | Поднимает локальное S3 (RustFS) и создаёт бакет; если нет `.env`, копирует его из `.env.example` |
| `make ingest`  | Скачивает архив CIFAR-10 и кладёт его в S3 `raw/` как есть (повторно ничего не делает) |
| `make data`    | Собирает обработанный датасет из `raw/` и выгружает его в S3 новой версией           |
| `make s3-down` | Останавливает хранилище; данные остаются в volume                                    |
| `make help`    | Список команд                                                                       |

Окружение и зависимости:

- зависимости описаны в `pyproject.toml`, точные версии зафиксированы в `uv.lock` (он закоммичен);
- инструменты разработки (ruff, mypy, pre-commit) вынесены в группу `dev`;
- добавить зависимость: `uv add <пакет>`, dev-зависимость: `uv add --dev <пакет>`;
- запустить команду в окружении: `uv run <команда>`.

Проверки кода:

- **ruff** — линтер и форматтер (длина строки 99, сверх правил по умолчанию включены `E501`,
  `B`, `I`, `SIM`, `UP`); **mypy** — типы в строгом режиме. Настройки — в `pyproject.toml`;
- **pre-commit** (`.pre-commit-config.yaml`) на каждом коммите запускает ruff и mypy и
  вычищает вывод ячеек ноутбуков (`nbstripout`). Коммит с ошибками блокируется.
  Прогнать хуки вручную по всем файлам: `uv run pre-commit run --all-files`;
- отладочный скрипт для проверки инструментов: `uv run python scripts/debug_tools.py 1 2 3 10`.

## Данные

Сырые данные лежат в локальном S3-совместимом хранилище без изменений. Обработанный датасет
собирается из них одной командой и выкладывается обратно в S3 с версией. Нужен Docker с
Compose v2.

### Хранилище

```bash
make s3-up     # RustFS в docker compose + автоматическое создание бакета
make s3-down   # остановить; данные сохраняются в именованном volume s3-data
```

- Адрес, логин, пароль и имя бакета берутся из `.env`. Пример значений лежит в `.env.example`;
  если `.env` нет, `make s3-up` создаст его из примера. Сам `.env` в git не попадает.
- S3 API: <http://localhost:9000>. Веб-консоль RustFS: <http://localhost:9001>, логин и пароль —
  `S3_ACCESS_KEY` и `S3_SECRET_KEY` из `.env`.
- Из терминала, например, через AWS CLI:
  `aws --endpoint-url http://localhost:9000 s3 ls s3://mlops/ --recursive --summarize`
  (ключи — через `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`).

### Порядок команд

```bash
make setup
make s3-up
make ingest    # архив -> s3://mlops/raw/cifar-10-python.tar.gz
make data      # конвейер -> s3://mlops/processed/cifar10/v1/
```

`make ingest` идемпотентен: если архив уже в S3, он ничего не скачивает и не загружает. Перед
загрузкой проверяется MD5 с сайта CIFAR. Существующий объект в `raw/` не перезаписывается.

`make data` запускает шаги по очереди. Каждый шаг — отдельный модуль, его можно запустить
отдельно (`uv run python -m mlops_practice.<шаг> --help`):

| Шаг | Модуль | Что делает |
|---|---|---|
| — | `publish --check` | Сразу падает, если такая версия уже есть в S3 |
| 3.1 | `download` | `raw/` из S3 → `data/raw/`; если архив уже на месте и MD5 совпадает, пропускает |
| 3.2 | `convert` | Проверяет MD5 (pickle открываем только из проверенного архива), распаковывает в `data/interim/`, пишет PNG в `data/processed/cifar10/images/`, `test.json` и полный train в `data/interim/cifar10/train.json` |
| 3.3 | `split` | Стратифицированно делит полный train на `annotations/train.json` и `val.json` |
| 3.4 | `stats` | Mean / std по каналам RGB только по train → `stats.json` |
| 3.5 | `publish` | Выгружает всё в S3 параллельно, `manifest.json` — последним |

Параметры задаются без правки кода:

```bash
make data VERSION=v2 SEED=7 VAL_SIZE=10000
```

Версии неизменяемы: если `processed/cifar10/<VERSION>/` уже существует, `make data` завершается с
ошибкой `... already exists; pass a new version` и ничего не перезаписывает.

### Что лежит в S3

```
s3://mlops/
├── raw/
│   └── cifar-10-python.tar.gz      # оригинальный архив, без изменений
└── processed/cifar10/v1/
    ├── images/                     # 60 000 PNG: train_00000.png … train_49999.png, test_00000.png … test_09999.png
    ├── annotations/
    │   ├── train.json              # 45 000
    │   ├── val.json                # 5 000
    │   └── test.json               # 10 000
    ├── stats.json                  # mean / std по каналам, шкала [0, 1], только train
    └── manifest.json
```

Запись в разметке: `image_id`, `file_name` (относительно корня версии), `label`, `label_name`,
`sha256` байтов PNG. `manifest.json` содержит число изображений в каждой выборке, размеры и
`sha256` файлов разметки и `stats.json`, параметры разбиения (`val_size`, `seed`), git-коммит и
флаг `git_dirty` (были ли незакоммиченные изменения в отслеживаемых файлах).

### Карточка датасета

- **Источник:** [CIFAR-10](https://www.cs.toronto.edu/~kriz/cifar.html), версия для Python
  (`cifar-10-python.tar.gz`, MD5 `c58f30108f718f92721af3b95e74349a`). Авторы — A. Krizhevsky,
  V. Nair, G. Hinton; описание — техотчёт *Learning Multiple Layers of Features from Tiny
  Images* (2009). Изображения отобраны из коллекции 80 Million Tiny Images.
- **Размеры:** 60 000 цветных изображений 32×32 RGB; исходно 50 000 train и 10 000 test.
- **Классы (10):** airplane, automobile, bird, cat, deer, dog, frog, horse, ship, truck. Классы
  сбалансированы: по 6 000 изображений, из них 5 000 в train и 1 000 в test.
- **Наше разбиение (v1):** из исходного train выделена валидация, стратифицированно по классам,
  seed 42: train 45 000 (по 4 500 на класс), val 5 000 (по 500 на класс). Test не меняется.
  Изображения не переименовываются: картинки из val сохраняют `image_id` вида `train_…`.
- **Статистики нормализации (v1, train, шкала [0, 1]):** mean ≈ (0.4913, 0.4820, 0.4463),
  std ≈ (0.2471, 0.2434, 0.2616).
- **Известные проблемы:**
  - очень низкое разрешение: мелкие детали неразличимы, часть изображений трудно отнести к
    классу даже человеку;
  - около 3% изображений test имеют почти-дубликаты в train (Barz & Denzler, 2020, «Do we
    train on test data?»), поэтому оценка на test может быть немного завышена;
  - в разметке есть небольшая доля ошибок (Northcutt et al., 2021, «Pervasive Label Errors in
    Test Sets»);
  - automobile и truck не пересекаются: пикапы не входят ни в один из этих классов, что
    отличается от бытового понимания;
  - исходный формат — pickle: загрузка может выполнить произвольный код, поэтому архив
    открывается только после проверки MD5;
  - родительская коллекция 80 Million Tiny Images отозвана авторами в 2020 году из-за
    оскорбительных меток и изображений. CIFAR-10 вручную размечен и отозван не был, но
    происхождение данных стоит учитывать.

## Project Organization

```
├── Makefile           <- Commands: `make setup`, `make check`, `make data`, ...
├── docker-compose.yml <- Local S3 storage (RustFS) and bucket creation
├── .env.example       <- Example S3 settings; copy to .env (not committed)
├── README.md          <- The top-level README for developers using this project.
├── data
│   ├── external       <- Data from third party sources.
│   ├── interim        <- Intermediate data that has been transformed.
│   ├── processed      <- The final, canonical data sets for modeling.
│   └── raw            <- The original, immutable data dump.
│
├── docs               <- Project documentation.
│
├── models             <- Trained and serialized models, model predictions, or model summaries
│
├── notebooks          <- Jupyter notebooks. Naming convention is a number (for ordering),
│                         the creator's initials, and a short `-` delimited description, e.g.
│                         `1.0-jqp-initial-data-exploration`.
│
├── pyproject.toml     <- Project metadata, dependencies and tool configuration (ruff, mypy)
├── uv.lock            <- Locked dependency versions (committed)
├── .python-version    <- Pinned Python version used by uv
│
├── .pre-commit-config.yaml <- Git hooks: ruff, mypy, nbstripout
│
├── references         <- Data dictionaries, manuals, and all other explanatory materials.
│
├── reports            <- Generated analysis as HTML, PDF, LaTeX, etc.
│   └── figures        <- Generated graphics and figures to be used in reporting
│
├── scripts
│   └── debug_tools.py <- Debug script for trying out the linter and type checker
│
└── mlops_practice     <- Source code for use in this project.
    ├── __init__.py    <- Makes mlops_practice a Python module
    ├── py.typed       <- Marks the package as typed (PEP 561)
    ├── s3.py          <- S3 client and helpers (existence checks, parallel upload)
    ├── ingest.py      <- Block 2: CIFAR-10 archive -> S3 raw/
    ├── download.py    <- 3.1: S3 raw/ -> data/raw/
    ├── convert.py     <- 3.2: pickle -> PNG images + JSON annotations
    ├── split.py       <- 3.3: stratified train/val split
    ├── stats.py       <- 3.4: per-channel normalization stats
    ├── publish.py     <- 3.5: versioned upload to S3 with manifest
    ├── metrics.py     <- Descriptive statistics
    └── preprocessing.py <- Feature scaling helpers
```

--------

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

## Project Organization

```
├── Makefile           <- Commands: `make setup`, `make check`, ...
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
    ├── metrics.py     <- Descriptive statistics
    └── preprocessing.py <- Feature scaling helpers
```

--------

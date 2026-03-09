# CI/CD и защита ветки main

## Branch protection (main)

Чтобы merge в `main` был возможен только при зелёном CI:

1. GitHub: **Settings** → **Branches** → **Add branch protection rule**.
2. Branch name pattern: `main`.
3. Включить **Require status checks to pass before merging** и выбрать статус **lint-and-test** (job из [.github/workflows/ci.yml](../../.github/workflows/ci.yml)).
4. По желанию: **Require pull request before merging**, **Do not allow bypassing**.

После этого PR в `main` можно смержить только при успешном прохождении линтеров и тестов.

## Релиз

Релиз — вручную: создаётся тег (например `v0.1.0`), при необходимости — GitHub Release с заметками. Версию в `pyproject.toml` держать в актуальном состоянии с тегом.

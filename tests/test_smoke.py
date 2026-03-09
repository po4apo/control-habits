"""Минимальный smoke-тест: импорт приложения и конфига."""


def test_import_config() -> None:
    """Проверка импорта настроек."""
    from control_habits.config import Settings

    assert Settings.model_fields["database_url"] is not None


def test_import_app() -> None:
    """Проверка импорта FastAPI-приложения."""
    from control_habits.api.app import app

    assert app.title == "Control Habits API"

import structlog


def _last_processor():
    cfg = structlog.get_config()
    processors = cfg.get("processors") or []
    assert processors, "structlog processors not configured"
    return processors[-1]


def test_configure_logging_uses_json_renderer_for_production_values():
    from app.config import Settings
    from app.main import _configure_logging

    for value in ["production", "prod", " Production ", "PROD"]:
        settings = Settings(environment=value)
        structlog.reset_defaults()
        _configure_logging(is_production=settings.is_production)
        assert isinstance(_last_processor(), structlog.processors.JSONRenderer)

    structlog.reset_defaults()


def test_configure_logging_uses_console_renderer_for_non_production_values():
    from app.config import Settings
    from app.main import _configure_logging

    for value in ["dev", "staging", "local", ""]:
        settings = Settings(environment=value)
        structlog.reset_defaults()
        _configure_logging(is_production=settings.is_production)
        assert isinstance(_last_processor(), structlog.dev.ConsoleRenderer)

    structlog.reset_defaults()

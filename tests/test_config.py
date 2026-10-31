"""Review fix #6: the app must not start with the built-in development secret outside development."""

import pytest

from app.config import DEV_JWT_SECRET, Settings


def settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)  # ignore the developer's .env so the test is predictable


def test_the_development_secret_is_fine_in_development():
    assert settings(app_env="dev").jwt_secret == DEV_JWT_SECRET


@pytest.mark.parametrize("env", ["production", "staging", "anything-but-dev"])
def test_the_development_secret_is_refused_everywhere_else(env):
    with pytest.raises(ValueError, match="JWT_SECRET"):
        settings(app_env=env)


def test_a_real_secret_is_accepted_in_production():
    assert settings(app_env="production", jwt_secret="k" * 40).app_env == "production"


def test_a_short_secret_is_refused_even_in_development():
    with pytest.raises(ValueError, match="32"):
        settings(app_env="dev", jwt_secret="too-short")


def test_message_text_is_logged_in_development_and_not_elsewhere_unless_asked():
    assert settings(app_env="dev").log_user_text is True
    assert settings(app_env="production", jwt_secret="k" * 40).log_user_text is False
    assert settings(app_env="production", jwt_secret="k" * 40, log_user_text=True).log_user_text is True
    assert settings(app_env="dev", log_user_text=False).log_user_text is False


# ---- deferred item #12: the DB pool size is a setting, so the load test can record the value it used ----

def test_the_db_pool_defaults_are_the_ones_measured_so_far():
    s = settings()
    assert (s.db_pool_size, s.db_max_overflow) == (10, 10)


def test_the_db_pool_can_be_changed_and_must_be_positive():
    assert settings(db_pool_size=25, db_max_overflow=0).db_pool_size == 25
    with pytest.raises(ValueError):
        settings(db_pool_size=0)
    with pytest.raises(ValueError):
        settings(db_max_overflow=-1)


# ---- review: the scripted fake model must never be reachable in a real deployment ----

def test_the_fake_model_is_allowed_in_development():
    assert settings(app_env="dev", llm_provider="fake").llm_provider == "fake"


def test_the_fake_model_is_refused_outside_development():
    with pytest.raises(ValueError, match="fake"):
        settings(app_env="production", llm_provider="fake", jwt_secret="k" * 40)


@pytest.mark.parametrize("typo", ["Claude", "claud", "openai", ""])
def test_an_unknown_provider_fails_at_startup_not_at_the_first_request(typo):
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        settings(llm_provider=typo)


def test_the_fake_model_delay_cannot_be_negative():
    assert settings(fake_llm_delay=0.5).fake_llm_delay == 0.5
    with pytest.raises(ValueError):
        settings(fake_llm_delay=-1)


def test_the_database_engine_uses_the_pool_settings():
    from app.config import settings as live
    from app.db.session import engine

    assert engine.pool.size() == live.db_pool_size
    assert engine.sync_engine.pool._max_overflow == live.db_max_overflow  # no public getter for this one

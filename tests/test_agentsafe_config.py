from pathlib import Path

from agentsafe import env as agentsafe_env

from oci_object_storage_mcp import agentsafe_config


def test_load_agentsafe_environment_decrypts_project_env(monkeypatch, tmp_path: Path) -> None:
    encrypted_env = tmp_path / ".env"
    encrypted_env.write_text('TOKEN="agentsafe:v1:encrypted"\n', encoding="utf-8")
    config_path = tmp_path / ".agentsafe" / "config"
    calls: list[tuple[Path, Path]] = []

    def fake_load(*, path: Path, config_path: Path) -> None:
        calls.append((path, config_path))

    monkeypatch.setattr(agentsafe_config, "ENV_PATH", encrypted_env)
    monkeypatch.setattr(agentsafe_config, "CONFIG_PATH", config_path)
    monkeypatch.setattr(agentsafe_env, "load", fake_load)

    agentsafe_config.load_agentsafe_environment()

    assert calls == [(encrypted_env, config_path)]

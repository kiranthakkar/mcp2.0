"""Load this application's encrypted AgentSafe environment."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
CONFIG_PATH = PROJECT_ROOT / ".agentsafe" / "config"


def load_agentsafe_environment() -> None:
    """Decrypt the project ``.env`` into ``os.environ`` for this process.

    AgentSafe keeps ciphertext in ``.env`` and its non-secret KMS routing
    configuration in ``.agentsafe/config``.  It only exposes plaintext in the
    current process environment; neither file is rewritten at runtime.
    """
    if not ENV_PATH.is_file():
        raise RuntimeError(
            f"AgentSafe environment file not found: {ENV_PATH}. "
            "Run 'agentsafe init' and 'agentsafe env encrypt' first."
        )

    try:
        from agentsafe import AgentSafeError
        from agentsafe import env as agentsafe_env
    except ImportError as exc:
        raise RuntimeError(
            "AgentSafe is required. Install project dependencies, including "
            "'agentconfigsafe[oci]'."
        ) from exc

    try:
        agentsafe_env.load(path=ENV_PATH, config_path=CONFIG_PATH)
    except AgentSafeError as exc:
        raise RuntimeError(f"Could not decrypt AgentSafe environment: {exc}") from exc

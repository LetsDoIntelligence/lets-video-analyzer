from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables prefixed `LETS_`."""

    model_config = SettingsConfigDict(env_prefix="LETS_", env_file=".env", extra="ignore")

    env: str = "development"
    # Origins allowed to call the API from a browser (the Next.js dev server by default).
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    data_dir: Path = API_ROOT / "data"
    database_url: str = f"sqlite:///{(API_ROOT / 'data' / 'lets.db').as_posix()}"
    max_upload_bytes: int = 2 * 1024**3  # 2 GB, matches the UI copy
    # Simulated latency for the stub analyzer (set to 0 in tests).
    analyze_think_ms: int = 700
    analyze_token_ms: int = 30
    # Placeholder indexing job: N progress steps, this long each (replaced in Phase 3).
    stub_job_steps: int = 10
    stub_job_step_ms: int = 300
    # Detection (Phase 3). Weights are fetched by `python ml/tools/check_gpu.py`.
    detect_weights: Path = API_ROOT.parent.parent / "ml" / "weights" / "yolo11s.pt"
    detect_device: str = "auto"  # "auto" = GPU when available, else "cpu"
    detect_fps: float = 5.0  # frames per second sampled for detection
    detect_batch_size: int = 8
    detect_conf: float = 0.25  # minimum detection confidence


@lru_cache
def get_settings() -> Settings:
    return Settings()

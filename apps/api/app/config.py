from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
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
    # Placeholder indexing job (indexing="stub"): N progress steps, this long each.
    stub_job_steps: int = 10
    stub_job_step_ms: int = 300
    # "yolo" = real detection + tracking; "stub" = fake progress only (no GPU/model needed).
    indexing: Literal["yolo", "stub"] = "yolo"
    auto_index: bool = True  # start indexing right after a video is uploaded
    # Detection (Phase 3). Weights are fetched by `python ml/tools/check_gpu.py`.
    detect_weights: Path = API_ROOT.parent.parent / "ml" / "weights" / "yolo11s.pt"
    detect_device: str = "auto"  # "auto" = GPU when available, else "cpu"
    detect_fps: float = 5.0  # frames per second sampled for detection
    detect_batch_size: int = 8
    detect_conf: float = 0.25  # minimum detection confidence
    # Open-vocabulary search for things the fixed detector can't see (trees, signs...).
    search_weights: Path = API_ROOT.parent.parent / "ml" / "weights" / "yolov8s-worldv2.pt"
    search_fps: float = 2.0  # sampled frames per second (these things mostly don't move)
    search_conf: float = 0.15  # minimum confidence; open-vocabulary scores run lower
    extract_color: bool = True  # name each vehicle's color while indexing (local, cheap)
    # Helmet check on people via OpenAI vision. Off unless a key is set (in apps/api/.env
    # as OPENAI_API_KEY, which is gitignored). Costs a little per video; `max_calls` caps it.
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("OPENAI_API_KEY", "LETS_OPENAI_API_KEY"),
        repr=False,
    )
    vision_model: str = "gpt-4o-mini"
    helmet_max_calls: int = 150
    # How questions are understood: "auto" = AI planner when a key is set, else (or if it
    # fails) simple rules; "llm" = AI only; "rules" = simple rules only (no API calls).
    planner: Literal["auto", "rules", "llm"] = "auto"
    planner_model: str = "gpt-4o-mini"
    planner_timeout: float = 15.0


@lru_cache
def get_settings() -> Settings:
    return Settings()

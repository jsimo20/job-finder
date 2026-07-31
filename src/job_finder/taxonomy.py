"""Domain and company-stage taxonomy, loaded from config/pipeline.toml.
Single source of truth for extract.py and score.py."""
from .settings import pipeline_config

_cfg = pipeline_config()

DOMAIN_WEIGHTS: dict[str, int] = {
    name: spec["weight"] for name, spec in _cfg["domains"].items()
}
DOMAIN_DEFINITIONS: dict[str, str] = {
    name: spec["definition"] for name, spec in _cfg["domains"].items()
}

STAGE_WEIGHTS: dict[str, int] = {
    name: spec["weight"] for name, spec in _cfg["stages"].items()
}
STAGE_DEFINITIONS: dict[str, str] = {
    name: spec["definition"] for name, spec in _cfg["stages"].items()
}

COMP_FLOOR_USD: int = _cfg["filters"]["comp_floor_usd"]

COMP_SCORE_THRESHOLDS: list[int] = sorted(_cfg["filters"]["comp_score_thresholds"])

YOE_MAIN_QUEUE_MAX: int = _cfg["filters"]["yoe_main_queue_max"]

STALE_DAYS: int = _cfg["filters"]["stale_days"]

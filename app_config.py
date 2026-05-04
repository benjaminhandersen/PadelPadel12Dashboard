import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config():
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def extract_team_id_from_url(url: str) -> int | None:
    try:
        return int(url.rstrip("/").split("/")[-1])
    except Exception:
        return None


def extract_pool_id_from_url(url: str) -> int | None:
    try:
        import urllib.parse as up
        parsed = up.urlparse(url)
        query = up.parse_qs(parsed.query)
        return int(query.get("poolId", [None])[0])
    except Exception:
        return None

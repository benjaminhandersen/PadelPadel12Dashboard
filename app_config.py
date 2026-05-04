import json
import re
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).parent / "config.json"

DEFAULT_CONFIG = {
    "active_season": "2026-foraar-serie-3b-vest",
    "seasons": {
        "2026-foraar-serie-3b-vest": {
            "label": "Lunar Ligaen Forår 2026 · Serie 3-B Vest",
            "team_url": "https://www.rankedin.com/en/team/homepage/2701885",
            "pool_url": "https://api.rankedin.com/v1/teamleague/GetTeamStandingsAsync?poolId=11353&language=en",
            "team_id": 2701885,
            "pool_id": 11353,
        }
    },
}


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # Backwards compatibility for old single-season config.json format.
    if "seasons" not in cfg:
        season_key = make_season_key(cfg.get("season_name", "season"))
        cfg = {
            "active_season": season_key,
            "seasons": {
                season_key: {
                    "label": cfg.get("season_name", "Padel Liga"),
                    "team_url": cfg.get("team_url", ""),
                    "pool_url": cfg.get("pool_url", ""),
                    "team_id": cfg.get("team_id"),
                    "pool_id": cfg.get("pool_id"),
                }
            },
        }
        save_config(cfg)

    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def make_season_key(label: str) -> str:
    key = label.lower().strip()
    key = key.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    key = re.sub(r"[^a-z0-9]+", "-", key)
    key = re.sub(r"-+", "-", key).strip("-")
    return key or "season"


def get_active_season(cfg: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    seasons = cfg.get("seasons", {})
    active_key = cfg.get("active_season")
    if active_key not in seasons and seasons:
        active_key = next(iter(seasons))
        cfg["active_season"] = active_key
        save_config(cfg)
    return active_key, seasons.get(active_key, {})


def set_active_season(season_key: str) -> dict[str, Any]:
    cfg = load_config()
    if season_key in cfg.get("seasons", {}):
        cfg["active_season"] = season_key
        save_config(cfg)
    return cfg


def upsert_season(
    label: str,
    team_url: str,
    pool_url: str = "",
    team_id: int | None = None,
    pool_id: int | None = None,
    season_key: str | None = None,
) -> dict[str, Any]:
    cfg = load_config()
    seasons = cfg.setdefault("seasons", {})
    key = season_key or make_season_key(label)

    final_team_id = team_id or extract_team_id_from_url(team_url)
    final_pool_id = pool_id or extract_pool_id_from_url(pool_url)

    seasons[key] = {
        "label": label,
        "team_url": team_url,
        "pool_url": pool_url,
        "team_id": final_team_id,
        "pool_id": final_pool_id,
    }
    cfg["active_season"] = key
    save_config(cfg)
    return cfg


def extract_team_id_from_url(url: str) -> int | None:
    if not url:
        return None
    try:
        return int(url.rstrip("/").split("/")[-1])
    except Exception:
        return None


def extract_pool_id_from_url(url: str) -> int | None:
    if not url:
        return None
    try:
        import urllib.parse as up
        parsed = up.urlparse(url)
        query = up.parse_qs(parsed.query)
        value = query.get("poolId", [None])[0]
        return int(value) if value is not None else None
    except Exception:
        return None

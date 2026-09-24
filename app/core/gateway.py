"""
Gateway route configuration loader and matcher.
Reads gateway.yml and matches incoming requests to upstream services.
"""


import fnmatch
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.config import get_settings

settings = get_settings()


@dataclass
class GatewayRoute:
    path: str
    upstream: str
    require_auth: bool = True
    permissions: list[str] = field(default_factory=list)
    rate_limit: int = 100  # requests/min


def load_gateway_config(config_path: str | None = None) -> list[GatewayRoute]:
    """Load and parse the gateway route configuration from YAML."""
    path = Path(config_path or settings.GATEWAY_CONFIG_PATH)
    if not path.exists():
        return []

    with open(path) as f:
        data = yaml.safe_load(f)

    routes: list[GatewayRoute] = []
    for entry in data.get("routes", []):
        routes.append(
            GatewayRoute(
                path=entry["path"],
                upstream=entry["upstream"],
                require_auth=entry.get("require_auth", True),
                permissions=entry.get("permissions", []),
                rate_limit=entry.get("rate_limit", 100),
            )
        )
    return routes


def match_route(request_path: str, routes: list[GatewayRoute]) -> GatewayRoute | None:
    """Find the first matching gateway route for a request path."""
    for route in routes:
        pattern = route.path.replace("/**", "/*")
        if fnmatch.fnmatch(request_path, pattern):
            return route
    return None

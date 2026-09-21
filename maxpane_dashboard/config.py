"""Persistent configuration stored in ~/.maxpane/config.toml."""

from __future__ import annotations

import os
from pathlib import Path

_CONFIG_DIR = Path.home() / ".maxpane"
_CONFIG_FILE = _CONFIG_DIR / "config.toml"


def _read_config() -> dict:
    """Read the config file and return as a dict."""
    if not _CONFIG_FILE.exists():
        return {}
    try:
        import tomllib
    except ModuleNotFoundError:
        # Python 3.10 fallback
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError:
            return {}
    try:
        return tomllib.loads(_CONFIG_FILE.read_text())
    except Exception:
        return {}


def _write_config(config: dict) -> None:
    """Write config dict back to TOML file (simple key=value only)."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for section, values in config.items():
        if isinstance(values, dict):
            lines.append(f"[{section}]")
            for k, v in values.items():
                if isinstance(v, str):
                    lines.append(f'{k} = "{v}"')
                elif isinstance(v, bool):
                    lines.append(f"{k} = {'true' if v else 'false'}")
                elif isinstance(v, (int, float)):
                    lines.append(f"{k} = {v}")
            lines.append("")
    _CONFIG_FILE.write_text("\n".join(lines) + "\n")


def _section(config: dict, name: str) -> dict:
    """``config[name]`` when it is a table, else ``{}``.

    The file is hand-editable: a top-level ``seat = 5`` instead of a
    ``[seat]`` table is third-party input, not a reason to crash start-up.
    """
    value = config.get(name)
    return value if isinstance(value, dict) else {}


def get_wallet() -> str:
    """Return saved wallet address, or empty string if not configured."""
    # Environment variable takes precedence
    env_wallet = os.environ.get("MAXPANE_WALLET", "")
    if env_wallet:
        return env_wallet
    return _section(_read_config(), "wallet").get("address", "")


def save_wallet(address: str) -> None:
    """Save wallet address to config file."""
    config = _read_config()
    config["wallet"] = {**_section(config, "wallet"), "address": address}
    _write_config(config)


def get_seat() -> int | None:
    """Return the saved Identity.md (IDMD) seat -- its NFT token id -- or ``None``.

    Read from the file only; there is no environment override. The file is
    hand-editable, so it is third-party input: anything but a non-negative
    integer is "no seat saved", never a guess.
    """
    value = _section(_read_config(), "seat").get("token_id")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def save_seat(token_id: int) -> None:
    """Save the IDMD seat's token id to the config file."""
    config = _read_config()
    config["seat"] = {**_section(config, "seat"), "token_id": token_id}
    _write_config(config)

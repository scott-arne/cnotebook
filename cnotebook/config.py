"""Configuration defaults for cnotebook: TOML file, environment, and ``configure()``."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cnotebook.core.context import CNotebookContext, cnotebook_context
from cnotebook.core.errors import warn
from cnotebook.core.vocabulary import IMAGE_FORMATS

UNSET: Any = object()
"""Sentinel default for constructor parameters that resolve through :func:`resolve`."""

_THEMES = ("auto", "light", "dark")
_DISPLAY_MODES = ("widget", "static")

# Writable render options with type validators
_RENDER_OPTIONS: dict[str, Any] = {
    "image_format": lambda v: v in IMAGE_FORMATS,
    "width": lambda v: isinstance(v, int) and not isinstance(v, bool) and v > 0,
    "height": lambda v: isinstance(v, int) and not isinstance(v, bool) and v > 0,
    "device_pixel_ratio": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0,
    "atom_stereo_style": lambda v: True,  # Accepts any value, validated by context setter
    "bond_stereo_style": lambda v: True,
    "depiction_style": lambda v: True,
    "resolution": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0,
    "callback": lambda v: callable(v) or v is None,
}

# section -> key -> (default, validator returning True when acceptable)
DEFAULTS: dict[str, dict[str, tuple[Any, Any]]] = {
    "display": {"mode": ("widget", lambda v: v in _DISPLAY_MODES)},
    "c3d": {
        "width": (800, lambda v: isinstance(v, int) and not isinstance(v, bool) and v > 0),
        "height": (None, lambda v: v is None or (isinstance(v, int) and not isinstance(v, bool) and v > 0)),
        "theme": ("auto", lambda v: v in _THEMES),
    },
    "molgrid": {
        "n_items_per_page": (24, lambda v: isinstance(v, int) and not isinstance(v, bool) and v > 0),
        "image_format": ("svg", lambda v: v in IMAGE_FORMATS),
        "theme": ("auto", lambda v: v in _THEMES),
        "width": (260, lambda v: isinstance(v, int) and not isinstance(v, bool) and v > 0),
        "height": (240, lambda v: isinstance(v, int) and not isinstance(v, bool) and v > 0),
    },
}


@dataclass
class Config:
    """Effective configuration.

    :param render: ``CNotebookContext`` options applied to the global context.
    :param display_mode: ``"widget"`` or ``"static"``.
    :param c3d: C3D constructor defaults.
    :param molgrid: MolGrid constructor defaults.
    """

    render: dict[str, Any] = field(default_factory=dict)
    display_mode: str = "widget"
    c3d: dict[str, Any] = field(default_factory=dict)
    molgrid: dict[str, Any] = field(default_factory=dict)


_CONFIG: Config | None = None


def _config_path() -> Path | None:
    explicit = os.environ.get("CNOTEBOOK_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".config"
    candidate = root / "cnotebook" / "config.toml"
    return candidate if candidate.exists() else None


def _section(raw: Any, name: str, source: str) -> dict[str, Any]:
    """Validate one section against ``DEFAULTS`` and return accepted values."""
    if not isinstance(raw, dict):
        warn(f"{source}: section '{name}' must be a mapping, not {type(raw).__name__}")
        return {}
    accepted: dict[str, Any] = {}
    for key, value in raw.items():
        spec = DEFAULTS[name].get(key)
        if spec is None:
            warn(f"{source}: unknown key '{name}.{key}' ignored")
            continue
        default, valid = spec
        if not valid(value):
            warn(f"{source}: invalid value {value!r} for '{name}.{key}', using {default!r}")
            continue
        accepted[key] = value
    return accepted


def _render_section(raw: Any, source: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        warn(f"{source}: section 'render' must be a mapping, not {type(raw).__name__}")
        return {}
    accepted: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in _RENDER_OPTIONS:
            warn(f"{source}: unknown key 'render.{key}' ignored")
            continue
        validator = _RENDER_OPTIONS[key]
        if not validator(value):
            warn(f"{source}: invalid value {value!r} for 'render.{key}'")
            continue
        # Try setting on a probe context to catch any remaining validation errors
        probe = CNotebookContext()
        try:
            setattr(probe, key, value)
            accepted[key] = value
        except (ValueError, TypeError, AttributeError) as exc:
            warn(f"{source}: cannot set 'render.{key}' to {value!r}: {exc}")
    return accepted


def load_config(path: Path | None = None) -> Config:
    """Load configuration from *path*, the discovered file, and the environment.

    :param path: Explicit TOML file; discovery applies when ``None``.
    :returns: The loaded :class:`Config`, also stored as the effective configuration.
    """
    global _CONFIG
    cfg = Config(
        display_mode=DEFAULTS["display"]["mode"][0],
        c3d={k: v[0] for k, v in DEFAULTS["c3d"].items()},
        molgrid={k: v[0] for k, v in DEFAULTS["molgrid"].items()},
    )
    target = path if path is not None else _config_path()
    if target is not None:
        source = str(target)
        try:
            raw = tomllib.loads(target.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            warn(f"Could not read cnotebook config {source}: {exc}")
            raw = {}
        for name in raw:
            if name not in ("display", "render", "c3d", "molgrid"):
                warn(f"{source}: unknown section '{name}' ignored")
        display = _section(raw.get("display", {}), "display", source)
        if "mode" in display:
            cfg.display_mode = display["mode"]
        cfg.c3d.update(_section(raw.get("c3d", {}), "c3d", source))
        cfg.molgrid.update(_section(raw.get("molgrid", {}), "molgrid", source))
        cfg.render = _render_section(raw.get("render", {}), source)
    env_mode = os.environ.get("CNOTEBOOK_DISPLAY_MODE")
    if env_mode:
        if env_mode in _DISPLAY_MODES:
            cfg.display_mode = env_mode
        else:
            warn(f"CNOTEBOOK_DISPLAY_MODE={env_mode!r} is not one of {_DISPLAY_MODES}; using 'widget'")
            cfg.display_mode = "widget"
    _CONFIG = cfg
    return cfg


def get_config() -> Config:
    """Return the effective configuration, loading it on first use."""
    if _CONFIG is None:
        return load_config()
    return _CONFIG


def apply_render_defaults(cfg: Config | None = None) -> None:
    """Apply ``cfg.render`` to the global context (called once at import)."""
    cfg = cfg or get_config()
    ctx = cnotebook_context.get()
    for key, value in cfg.render.items():
        setattr(ctx, key, value)


def configure(
    *,
    display_mode: str | None = None,
    c3d: dict[str, Any] | None = None,
    molgrid: dict[str, Any] | None = None,
    **render_options: Any,
) -> None:
    """Change defaults at runtime; affects objects created afterwards.

    :param display_mode: ``"widget"`` or ``"static"``.
    :param c3d: C3D defaults (``width``, ``height``, ``theme``).
    :param molgrid: MolGrid defaults (``n_items_per_page``, ``image_format``, ``theme``, ``width``, ``height``).
    :param render_options: Global context options applied immediately.
    :raises ValueError: If a value is not acceptable.
    :raises KeyError: If a key is unknown.
    """
    # Validate everything first before applying any changes (atomicity)
    if display_mode is not None and display_mode not in _DISPLAY_MODES:
        raise ValueError(f"display_mode must be one of {_DISPLAY_MODES} (got {display_mode!r})")

    # Validate c3d and molgrid options
    validated_updates: dict[str, dict[str, Any]] = {}
    for name, values in (("c3d", c3d), ("molgrid", molgrid)):
        validated_updates[name] = {}
        for key, value in (values or {}).items():
            if key not in DEFAULTS[name]:
                raise KeyError(f"Unknown {name} option {key!r}")
            if not DEFAULTS[name][key][1](value):
                raise ValueError(f"Invalid value {value!r} for {name}.{key}")
            validated_updates[name][key] = value

    # Validate render options
    validated_render: dict[str, Any] = {}
    probe = CNotebookContext()
    for key, value in render_options.items():
        if key not in _RENDER_OPTIONS:
            raise KeyError(f"Unknown render option {key!r}")
        if not _RENDER_OPTIONS[key](value):
            raise ValueError(f"Invalid value {value!r} for render option {key!r}")
        # Try setting on probe to catch any remaining issues
        try:
            setattr(probe, key, value)
            validated_render[key] = value
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError(f"Cannot set render option {key!r} to {value!r}: {exc}") from exc

    # All validation passed; now apply changes atomically
    cfg = get_config()
    if display_mode is not None:
        cfg.display_mode = display_mode
    for name in ("c3d", "molgrid"):
        getattr(cfg, name).update(validated_updates[name])
    ctx = cnotebook_context.get()
    for key, value in validated_render.items():
        setattr(ctx, key, value)
        cfg.render[key] = value


def resolve(section: str, key: str, explicit: Any) -> Any:
    """Resolve a constructor parameter: explicit value, else configured value, else default.

    :param section: ``"c3d"``, ``"molgrid"`` or ``"display"``.
    :param key: Option name within the section.
    :param explicit: The constructor argument; :data:`UNSET` means not given.
    :returns: The resolved value.
    :raises KeyError: If the key is unknown.
    """
    if key not in DEFAULTS[section]:
        raise KeyError(f"Unknown {section} option {key!r}")
    if explicit is not UNSET:
        return explicit
    cfg = get_config()
    if section == "display":
        return cfg.display_mode
    return getattr(cfg, section).get(key, DEFAULTS[section][key][0])

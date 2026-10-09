"""Publishing targets."""

from __future__ import annotations

from ..config import Config, ConfigError, TargetConfig
from .base import PublishResult, ReleaseBundle, StatusResult, Target
from .gitea import GiteaTarget
from .github import GitHubTarget
from .s3 import ArvanTarget, LiaraTarget, S3Target

REGISTRY: dict[str, type[Target]] = {
    "github": GitHubTarget,
    "s3": S3Target,
    "arvan": ArvanTarget,
    "liara": LiaraTarget,
    "gitea": GiteaTarget,
}


def make_target(tcfg: TargetConfig, config: Config) -> Target:
    try:
        cls = REGISTRY[tcfg.type]
    except KeyError as e:
        raise ConfigError(f"unknown target type '{tcfg.type}'") from e
    return cls(tcfg, config)


def make_targets(config: Config, only: list[str] | None = None) -> list[Target]:
    selected = [t for t in config.targets if not only or t.name in only]
    if only:
        missing = set(only) - {t.name for t in selected}
        if missing:
            raise ConfigError(f"unknown target(s): {', '.join(sorted(missing))}")
    return [make_target(t, config) for t in selected]


__all__ = [
    "REGISTRY",
    "ArvanTarget",
    "GiteaTarget",
    "GitHubTarget",
    "LiaraTarget",
    "PublishResult",
    "ReleaseBundle",
    "S3Target",
    "StatusResult",
    "Target",
    "make_target",
    "make_targets",
]

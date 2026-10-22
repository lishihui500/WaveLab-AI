"""Explicit, traceable physical mapping; parser never guesses phase/arm roles."""
from typing import Literal

from .models import DatasetManifest


def map_group(manifest: DatasetManifest, group_name: str,
              template: Literal["ABC", "six_arms", "numbered"], *,
              confirmation_source: str, unit: str | None = None) -> DatasetManifest:
    if not confirmation_source.strip():
        raise ValueError("Mapping requires a nonempty confirmation source")
    group = next((g for g in manifest.groups if g.group_name == group_name), None)
    if group is None:
        raise KeyError(group_name)
    if template == "ABC":
        roles = ("A相", "B相", "C相")
    elif template == "six_arms":
        roles = ("A相上桥臂", "A相下桥臂", "B相上桥臂", "B相下桥臂", "C相上桥臂", "C相下桥臂")
    elif template == "numbered":
        roles = tuple(None for _ in group.channel_ids)
    else:
        raise ValueError(f"Unknown mapping template: {template}")
    if len(roles) != len(group.channel_ids):
        raise ValueError("Template channel count differs from selected group")
    updates = {}
    for cid, role in zip(group.channel_ids, roles):
        channel = next(c for c in manifest.channels if c.channel_id == cid)
        data = channel.model_dump()
        data.update(physical_role=role, confirmation_source=confirmation_source,
                    display_name=role or f"{group_name}[{channel.group_index+1}]")
        if unit is not None:
            data["unit"] = unit
        updates[cid] = type(channel).model_validate(data)
    data = manifest.model_dump()
    data["channels"] = [updates.get(c.channel_id, c) for c in manifest.channels]
    return DatasetManifest.model_validate(data)


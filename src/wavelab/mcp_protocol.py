"""Wire compatibility, separate from the application release version."""
import hashlib
import json
from functools import lru_cache


@lru_cache(maxsize=1)
def action_schema():
    from wavelab.commands.plot import Plan, ALLOWED, TARGETS, tool_definitions
    from wavelab.ai.manual import protocol
    return dict(schema=Plan.model_json_schema(),
                change_fields={k: sorted(v) for k, v in ALLOWED.items()},
                patch_schema_by_action=protocol()["patch_schema_by_action"],
                rules=tool_definitions()["rules"],
                targets={k: sorted(v) for k, v in TARGETS.items()})


@lru_cache(maxsize=1)
def identity():
    raw = json.dumps(action_schema(), sort_keys=True, separators=(",", ":")).encode()
    return dict(protocol_version="2", schema_hash=hashlib.sha256(raw).hexdigest())

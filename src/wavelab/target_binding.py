"""Local GUI consent, separate from heartbeat leases and editable project state."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4


def project_identity(w):
    """A saved location plus immutable source identities, never a display name.

    Hashes stay local; a copied project at a different location is a new target.
    Revisions, styling and metadata edits do not change this identity.
    """
    if w.spec is None or w.project_path is None or not w.project_path.is_file():
        return None
    location = os.path.normcase(str(w.project_path.resolve()))
    sources = sorted((m.dataset_id, m.source_sha256) for m in w.spec.datasets)
    digest = lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()
    return dict(location=digest(location), sources=digest(json.dumps(sources)))


class TargetStore:
    def __init__(self, path):
        self.path = Path(path)

    def read(self):
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
            if (record.get("version") != 2 or not isinstance(record["persistent"], bool)
                    or not all(isinstance(record[k], str) and record[k] for k in ("endpoint_id", "binding_id"))
                    or not all(isinstance(record["target"][k], str) and record["target"][k]
                               for k in ("session_id", "project_epoch"))):
                return None
            if record["persistent"] and (not isinstance(record.get("project_identity"), dict)
                    or set(record["project_identity"]) != {"location", "sources"}
                    or not all(isinstance(v, str) and len(v) == 64 for v in record["project_identity"].values())):
                return None
            return record
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None

    @contextmanager
    def locked(self):
        # Serialize selection/revocation/recovery across GUI processes as well
        # as threads. Never hold this lock while probing another endpoint.
        with self.path.with_suffix(".lock").open("a+b") as stream:
            if stream.tell() == 0:
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    def replace(self, record, *, expected=...):
        """Atomic compare-and-swap prevents old pages reviving revoked consent."""
        with self.locked():
            if expected is not ... and self.read() != expected:
                return False
            if record is None:
                self.path.unlink(missing_ok=True)
                return True
            temporary = self.path.with_name(uuid4().hex + ".tmp")
            try:
                with temporary.open("x", encoding="utf-8") as stream:
                    json.dump(record, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            finally:
                temporary.unlink(missing_ok=True)
            return True

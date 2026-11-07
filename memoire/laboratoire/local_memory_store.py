"""Journal immuable et projection de souvenirs dans SQLite."""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import threading
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

def user_data(user_id):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", user_id):
        raise ValueError("Identite memoire invalide")
    return (Path(__file__).resolve().parents[2] / 'laboratoire') / "data" / "memory" / user_id

SCHEMA_VERSION = 1
ROLES = frozenset({"user", "assistant", "system"})
CHANNELS = frozenset({"voice", "text", "twitch", "thought"})


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.casefold())
    bare = "".join(char for char in folded if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", bare))


def _search_tokens(text: str) -> frozenset[str]:
    aliases = {
        "prefere": "aime",
        "preference": "aime",
        "adore": "aime",
        "appelle": "nom",
        "prenom": "nom",
        "habite": "lieu",
        "ville": "lieu",
        "domicile": "lieu",
        "commune": "lieu",
        "reside": "lieu",
        "residence": "lieu",
    }
    ignored = {
        "a",
        "au",
        "aux",
        "de",
        "des",
        "du",
        "et",
        "est",
        "la",
        "le",
        "les",
        "ma",
        "mon",
        "que",
        "quel",
        "quelle",
        "qui",
        "un",
        "une",
        "je",
        "j",
        "tu",
        "te",
        "toi",
        "moi",
        "me",
        "m",
        "t",
        "s",
        "il",
        "elle",
        "on",
        "nous",
        "vous",
        "ils",
        "elles",
        "ce",
        "c",
        "ca",
        "se",
        "ses",
        "son",
        "sa",
        "mes",
        "tes",
        "ton",
        "ta",
        "dans",
        "pour",
        "avec",
        "ne",
        "n",
        "pas",
        "personne",
    }
    tokens = set(normalize(text).split()) - ignored
    tokens.update(aliases[token] for token in tuple(tokens) if token in aliases)
    return frozenset(tokens)


def is_literal_profile_request(query: str) -> bool:
    """Chemin rapide historique; les autres formulations sont routees au cerveau."""
    return bool(
        re.fullmatch(
            r"(?:alice )?(?:que sais tu (?:de|sur) moi|"
            r"qu est ce que tu sais (?:de|sur) moi|"
            r"(?:tu te souviens|te souviens tu) de moi|"
            r"que (?:retiens|connais) tu (?:de|sur) moi)"
            r"(?: alice)?",
            normalize(query),
        )
    )


@dataclass(frozen=True)
class Event:
    id: int
    request_id: str
    role: str
    channel: str
    content: str
    created_at: str


@dataclass(frozen=True)
class Memory:
    id: str
    key: str | None
    statement: str
    kind: str
    confidence: float
    times_seen: int
    created_at: str
    updated_at: str


class MemoryStore:
    """Une base par personne, avec ecritures atomiques et rejouables."""

    def __init__(self, user_id: str, database: Path | None = None) -> None:
        self.user_id = user_id
        self.database = (
            Path(database)
            if database is not None
            else user_data(user_id) / "memory.sqlite3"
        )
        self._protect_tests()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.database,
            timeout=30,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA busy_timeout=30000")
        self._create_schema()

    def _protect_tests(self) -> None:
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            return
        if not self.user_id.startswith("validation_"):
            raise RuntimeError(
                "un test ne peut ouvrir que la memoire d'un utilisateur de validation"
            )
        if self.database.resolve().is_relative_to(user_data(self.user_id).resolve()):
            raise RuntimeError("un test doit utiliser une base temporaire explicite")

    def _create_schema(self) -> None:
        schema = """
        BEGIN IMMEDIATE;
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
            channel TEXT NOT NULL CHECK(channel IN ('voice','text','twitch','thought')),
            content TEXT NOT NULL CHECK(length(content) BETWEEN 1 AND 20000),
            content_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS events_created_idx ON events(created_at, id);
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            memory_key TEXT,
            statement TEXT NOT NULL CHECK(length(statement) BETWEEN 2 AND 1000),
            normalized TEXT NOT NULL,
            kind TEXT NOT NULL,
            confidence REAL NOT NULL CHECK(confidence BETWEEN 0.0 AND 1.0),
            status TEXT NOT NULL CHECK(status IN ('active','superseded','rejected')),
            times_seen INTEGER NOT NULL CHECK(times_seen >= 1),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS memories_active_key
            ON memories(memory_key) WHERE memory_key IS NOT NULL AND status='active';
        CREATE INDEX IF NOT EXISTS memories_active_idx ON memories(status, updated_at);
        CREATE TABLE IF NOT EXISTS evidence (
            memory_id TEXT NOT NULL REFERENCES memories(id),
            event_id INTEGER NOT NULL REFERENCES events(id),
            quote TEXT NOT NULL CHECK(length(quote) BETWEEN 1 AND 1000),
            created_at TEXT NOT NULL,
            PRIMARY KEY(memory_id, event_id, quote)
        );
        CREATE TABLE IF NOT EXISTS mood (
            singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
            valence REAL NOT NULL CHECK(valence BETWEEN -1.0 AND 1.0),
            arousal REAL NOT NULL CHECK(arousal BETWEEN 0.0 AND 1.0),
            label TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT OR IGNORE INTO mood(singleton,valence,arousal,label,updated_at)
            VALUES(1,0.0,0.25,'calme',CURRENT_TIMESTAMP);
        INSERT OR IGNORE INTO metadata(key,value) VALUES('schema_version','1');
        COMMIT;
        """
        with self._lock:
            self._connection.executescript(schema)
            found = self._connection.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()
            if found is None or int(found["value"]) != SCHEMA_VERSION:
                raise RuntimeError("version de base memoire incompatible")

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def _transaction(self):
        return _Transaction(self)

    def record_event(
        self,
        *,
        request_id: str,
        role: str,
        channel: str,
        content: str,
        created_at: str | None = None,
    ) -> tuple[Event, bool]:
        request_id = request_id.strip()
        content = content.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}", request_id):
            raise ValueError("identifiant de requete invalide")
        if role not in ROLES:
            raise ValueError("role invalide")
        if channel not in CHANNELS:
            raise ValueError("canal invalide")
        if not 1 <= len(content) <= 20000:
            raise ValueError("taille d'evenement invalide")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        timestamp = created_at or _now()
        with self._lock, self._transaction():
            existing = self._connection.execute(
                "SELECT * FROM events WHERE request_id=?", (request_id,)
            ).fetchone()
            if existing is not None:
                if (
                    existing["role"] != role
                    or existing["channel"] != channel
                    or existing["content_sha256"] != digest
                ):
                    raise ValueError("cet identifiant designe deja un autre evenement")
                return self._event(existing), False
            cursor = self._connection.execute(
                """INSERT INTO events(request_id,role,channel,content,content_sha256,created_at)
                   VALUES(?,?,?,?,?,?)""",
                (request_id, role, channel, content, digest, timestamp),
            )
            row = self._connection.execute(
                "SELECT * FROM events WHERE id=?", (cursor.lastrowid,)
            ).fetchone()
            return self._event(row), True

    @staticmethod
    def _event(row: sqlite3.Row) -> Event:
        return Event(
            id=row["id"],
            request_id=row["request_id"],
            role=row["role"],
            channel=row["channel"],
            content=row["content"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _memory(row: sqlite3.Row) -> Memory:
        return Memory(
            id=row["id"],
            key=row["memory_key"],
            statement=row["statement"],
            kind=row["kind"],
            confidence=row["confidence"],
            times_seen=row["times_seen"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def remember(
        self,
        *,
        statement: str,
        kind: str,
        confidence: float,
        event_id: int,
        evidence_quote: str,
        key: str | None = None,
    ) -> Memory:
        statement = " ".join(statement.strip().split())
        evidence_quote = " ".join(evidence_quote.strip().split())
        normalized = normalize(statement)
        if not 2 <= len(statement) <= 1000 or not normalized:
            raise ValueError("souvenir vide ou trop long")
        if not re.fullmatch(r"[a-z][a-z0-9_.:-]{1,127}", kind):
            raise ValueError("type de souvenir invalide")
        if key is not None and not re.fullmatch(r"[a-z][a-z0-9_.:-]{1,191}", key):
            raise ValueError("cle de souvenir invalide")
        if isinstance(confidence, bool) or not 0.0 <= float(confidence) <= 1.0:
            raise ValueError("confiance invalide")
        if not 1 <= len(evidence_quote) <= 1000:
            raise ValueError("preuve invalide")
        timestamp = _now()
        with self._lock, self._transaction():
            event = self._connection.execute(
                "SELECT content FROM events WHERE id=?", (event_id,)
            ).fetchone()
            if event is None:
                raise ValueError("evenement source introuvable")
            if normalize(evidence_quote) not in normalize(event["content"]):
                raise ValueError("la preuve n'apparait pas dans l'evenement source")

            existing = None
            if key is not None:
                existing = self._connection.execute(
                    "SELECT * FROM memories WHERE memory_key=? AND status='active'",
                    (key,),
                ).fetchone()
            if existing is None:
                existing = self._connection.execute(
                    "SELECT * FROM memories WHERE normalized=? AND status='active'",
                    (normalized,),
                ).fetchone()

            if existing is not None and existing["normalized"] == normalized:
                memory_id = existing["id"]
                duplicate_evidence = self._connection.execute(
                    """SELECT 1 FROM evidence
                       WHERE memory_id=? AND event_id=? AND quote=?""",
                    (memory_id, event_id, evidence_quote),
                ).fetchone()
                if duplicate_evidence is not None:
                    return self._memory(existing)
                self._connection.execute(
                    """UPDATE memories
                       SET confidence=max(confidence,?), times_seen=times_seen+1, updated_at=?
                       WHERE id=?""",
                    (float(confidence), timestamp, memory_id),
                )
            else:
                if existing is not None and key is not None:
                    self._connection.execute(
                        "UPDATE memories SET status='superseded',updated_at=? WHERE id=?",
                        (timestamp, existing["id"]),
                    )
                memory_id = uuid.uuid4().hex
                self._connection.execute(
                    """INSERT INTO memories(
                           id,memory_key,statement,normalized,kind,confidence,status,
                           times_seen,created_at,updated_at
                       ) VALUES(?,?,?,?,?,?,'active',1,?,?)""",
                    (
                        memory_id,
                        key,
                        statement,
                        normalized,
                        kind,
                        float(confidence),
                        timestamp,
                        timestamp,
                    ),
                )
            self._connection.execute(
                """INSERT OR IGNORE INTO evidence(memory_id,event_id,quote,created_at)
                   VALUES(?,?,?,?)""",
                (memory_id, event_id, evidence_quote, timestamp),
            )
            row = self._connection.execute(
                "SELECT * FROM memories WHERE id=?", (memory_id,)
            ).fetchone()
            return self._memory(row)

    def recent_events(self, limit: int = 24) -> list[Event]:
        if not 1 <= limit <= 500:
            raise ValueError("limite d'evenements invalide")
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._event(row) for row in reversed(rows)]

    def event_by_request(self, request_id: str) -> Event | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM events WHERE request_id=?", (request_id,)
            ).fetchone()
        return self._event(row) if row is not None else None

    def search(
        self, query: str, limit: int = 12, *, profile_request: bool | None = None
    ) -> list[Memory]:
        if not 1 <= limit <= 100:
            raise ValueError("limite de souvenirs invalide")
        if profile_request is not None and type(profile_request) is not bool:
            raise TypeError("intention de rappel invalide")
        query_tokens = _search_tokens(query)
        query_normalized = normalize(query)
        # The brain may supply a semantic scope decision, never a memory/user ID.
        # Standalone/offline callers retain the previous lexical behavior.
        profile_request = (
            is_literal_profile_request(query)
            if profile_request is None
            else profile_request
        )
        if query_normalized and not query_tokens and not profile_request:
            return []
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM memories WHERE status='active' ORDER BY updated_at DESC LIMIT 2000"
            ).fetchall()
        ranked: list[tuple[float, int, sqlite3.Row]] = []
        for recency, row in enumerate(rows):
            tokens = _search_tokens(row["statement"])
            overlap = len(query_tokens & tokens)
            if (
                query_tokens
                and not profile_request
                and not overlap
                and query_normalized not in row["normalized"]
            ):
                continue
            coverage = overlap / max(len(query_tokens), 1)
            score = (
                coverage * 4.0
                + overlap
                + float(row["confidence"])
                + 1.0 / (recency + 2)
            )
            ranked.append((score, -recency, row))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        if not query_tokens or profile_request:
            ranked = [
                (1.0 / (index + 1), -index, row) for index, row in enumerate(rows)
            ]
        return [self._memory(row) for _, _, row in ranked[:limit]]

    def all_active(self, limit: int = 1000) -> list[Memory]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM memories WHERE status='active' ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._memory(row) for row in rows]

    def integrity(self) -> dict[str, int | str]:
        with self._lock:
            check = self._connection.execute("PRAGMA quick_check").fetchone()[0]
            events = self._connection.execute("SELECT count(*) FROM events").fetchone()[
                0
            ]
            memories = self._connection.execute(
                "SELECT count(*) FROM memories WHERE status='active'"
            ).fetchone()[0]
            evidence = self._connection.execute(
                "SELECT count(*) FROM evidence"
            ).fetchone()[0]
        return {
            "status": check,
            "events": events,
            "memories": memories,
            "evidence": evidence,
        }

    def mood(self) -> tuple[float, float, str, str]:
        with self._lock:
            row = self._connection.execute(
                "SELECT valence,arousal,label,updated_at FROM mood WHERE singleton=1"
            ).fetchone()
        return (
            float(row["valence"]),
            float(row["arousal"]),
            row["label"],
            row["updated_at"],
        )

    def set_mood(self, *, valence: float, arousal: float, label: str) -> None:
        if not -1.0 <= float(valence) <= 1.0:
            raise ValueError("valence invalide")
        if not 0.0 <= float(arousal) <= 1.0:
            raise ValueError("activation invalide")
        if not re.fullmatch(r"[a-z][a-z_-]{1,31}", label):
            raise ValueError("etiquette d'humeur invalide")
        with self._lock, self._transaction():
            self._connection.execute(
                """UPDATE mood SET valence=?,arousal=?,label=?,updated_at=?
                   WHERE singleton=1""",
                (float(valence), float(arousal), label, _now()),
            )


class _Transaction:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def __enter__(self):
        self.store._connection.execute("BEGIN IMMEDIATE")
        return self

    def __exit__(self, exc_type, _exc, _traceback) -> bool:
        self.store._connection.execute("ROLLBACK" if exc_type else "COMMIT")
        return False

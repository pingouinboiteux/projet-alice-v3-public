"""Recherche locale bornee dans des archives Kiwix."""

from __future__ import annotations

import html
import json
import re
import socket
import subprocess
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import ClassVar

class _SilentLog:
    def write(self, *args, **kwargs): pass

LOG = _SilentLog()

RESEARCH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["search", "query", "subject", "sources"],
    "properties": {
        "search": {"type": "boolean"},
        "query": {"type": "string", "maxLength": 180},
        "subject": {"type": "string", "maxLength": 180},
        "sources": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "string",
                "enum": [
                    "wikipedia",
                    "wiktionary",
                    "wikivoyage",
                    "gutenberg",
                    "french",
                ],
            },
        },
    },
}


@dataclass(frozen=True)
class ResearchMaterial:
    query: str
    text: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class ResearchRequest:
    query: str
    collections: tuple[str, ...]
    subject: str = ""


class _ReadableText(HTMLParser):
    ignored: ClassVar[set[str]] = {"script", "style", "svg", "nav", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, _attrs) -> None:
        if tag.casefold() in self.ignored:
            self.depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in self.ignored and self.depth:
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.depth:
            clean = " ".join(data.split())
            if clean:
                self.parts.append(clean)


def readable_html(value: str, maximum: int) -> str:
    parser = _ReadableText()
    parser.feed(value)
    text = " ".join(parser.parts)
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text[:maximum].rsplit(" ", 1)[0] if len(text) > maximum else text


def _normalized(value: str) -> str:
    return " ".join(
        re.findall(
            r"[a-z0-9]+",
            "".join(
                c
                for c in unicodedata.normalize("NFKD", value.casefold())
                if not unicodedata.combining(c)
            ),
        )
    )


def article_excerpt(
    value: str, query: str, subject: str = "", maximum: int = 3600
) -> str:
    """Keep the introduction and query-relevant passages, including late evidence."""
    text = readable_html(value, 2_000_000)
    if len(text) <= maximum:
        return text
    excluded = set(_normalized(subject).split()) | {
        "dans",
        "avec",
        "pour",
        "quelle",
        "quelles",
        "quels",
        "quel",
        "comment",
        "quand",
        "est",
        "les",
        "des",
        "une",
        "qui",
        "que",
        "sur",
        "date",
    }
    terms = {
        word[:5]
        for word in _normalized(query).split()
        if len(word) > 2 and word not in excluded
    }
    # Windows overlap so a fact near a boundary is not discarded. The original
    # words and order are retained; no model invents or paraphrases evidence here.
    head = min(1800, maximum // 2)
    head = text.rfind(" ", 0, head)
    width = max(64, (maximum - head - 14) // 2)
    spans = [(0, head)]
    ranked = []
    for start in range(head + 1, len(text), width // 2):
        start = text.rfind(" ", 0, start) + 1
        end = min(len(text), start + width)
        if end < len(text):
            end = text.rfind(" ", start, end)
        words = {word[:5] for word in _normalized(text[start:end]).split()}
        score = len(terms & words)
        if score:
            ranked.append((score, start, end))
    for _score, start, end in sorted(ranked, key=lambda item: (-item[0], item[1])):
        if all(end <= a or start >= b for a, b in spans):
            spans.append((start, end))
        if len(spans) == 3:
            break
    if len(spans) == 1:
        return text[:maximum].rsplit(" ", 1)[0]
    return " [...] ".join(text[a:b] for a, b in sorted(spans))[:maximum]


class LocalKnowledge:
    """Lance Kiwix sur localhost et ne laisse sortir aucune requete d'Alice."""

    RANDOMLY_EXCLUDED = re.compile(
        r"\b(?:pornograph|sexuel|sexualit|p[ée]nis|vagin|masturb|hentai|"
        r"prostitution|[ée]rotique)\w*\b",
        re.IGNORECASE,
    )

    def __init__(self, settings: Settings) -> None:
        section = settings.section("knowledge")
        self.enabled = section.get("enabled") is True
        self.host = "127.0.0.1"
        self.port = int(section["kiwix_port"])
        self.timeout = float(section["timeout_seconds"])
        self.maximum_sources = int(section["maximum_sources"])
        self.maximum_characters = int(section["maximum_characters"])
        self.archive_date = str(section["archive_date"])
        self.source_books = {
            str(name): str(book) for name, book in section["source_books"].items()
        }
        self.random_book = str(section["random_book"])
        self.executable = settings.path("kiwix_server")
        self.archives = tuple(settings.path(key) for key in section["archive_keys"])
        self.process: subprocess.Popen | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> bool:
        if not self.enabled:
            return False
        if not self.executable.is_file() or not all(
            path.is_file() for path in self.archives
        ):
            return False
        command = [
            str(self.executable),
            "--address=127.0.0.1",
            f"--port={self.port}",
            "--blockexternal",
            "--threads=2",
            "--searchLimit=4",
            *(str(path) for path in self.archives),
        ]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            command,
            cwd=str(self.executable.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        self.own_process(self.process)
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.close()
                return False
            try:
                with socket.create_connection((self.host, self.port), timeout=0.2):
                    return True
            except OSError:
                time.sleep(0.1)
        self.close()
        return False

    def close(self) -> None:
        process, self.process = self.process, None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def _open(self, path: str, *, maximum: int) -> tuple[bytes, str]:
        if not path.startswith('/') or path.startswith('//'):
            raise ValueError('Chemin de bibliotheque non local')
        # Kiwix suggestions can contain raw spaces or Unicode in article paths.
        # Preserve already escaped characters and query separators.
        path = urllib.parse.quote(path, safe="/?&=:%+;,@!$'()*~-._")
        request = urllib.request.Request(
            self.base_url + path,
            headers={"User-Agent": "Alice-local-knowledge/1"},
        )
        with self.opener.open(request, timeout=self.timeout) as response:
            data = response.read(maximum + 1)
            if len(data) > maximum:
                raise ValueError("reponse Kiwix trop grande")
            return data, response.geturl()

    @staticmethod
    def _entry_value(entry: ET.Element, suffix: str) -> str:
        for child in entry.iter():
            if child.tag.rsplit("}", 1)[-1] == suffix and child.text:
                return " ".join(child.text.split())
        return ""

    def _suggestions(self, collection: str, query: str) -> list[tuple[str, str, str]]:
        parameters = urllib.parse.urlencode(
            {"content": self.source_books[collection], "term": query}
        )
        try:
            raw, _url = self._open(f"/suggest?{parameters}", maximum=256_000)
            values = json.loads(raw)
        except (OSError, ValueError, json.JSONDecodeError):
            return []
        if not isinstance(values, list):
            return []
        results: list[tuple[str, str, str]] = []
        for item in values[: self.maximum_sources]:
            if not isinstance(item, dict):
                continue
            title, path = item.get("value"), item.get("path")
            if isinstance(title, str) and isinstance(path, str):
                href = f"/content/{self.source_books[collection]}/{path.lstrip('/')}"
                results.append((title, href, ""))
        return results

    def search(
        self,
        query: str,
        collections: tuple[str, ...] = ("wikipedia",),
        *,
        subject: str = "",
    ) -> ResearchMaterial | None:
        clean_query = " ".join(query.split())[:180]
        if len(clean_query) < 2 or self.process is None:
            return None
        started = time.perf_counter()
        extracts: list[str] = []
        sources: list[str] = []
        selected = tuple(dict.fromkeys(collections))[:3]
        selected = tuple(name for name in selected if name in self.source_books)
        if not selected:
            selected = ("wikipedia",)
        for collection in selected:
            # Full-text ranking can prefer a statue of a scientist to the scientist.
            # An exact title match identifies the requested subject before excerpts.
            title_query = " ".join((subject or clean_query).split())[:180]
            exact = [
                item
                for item in self._suggestions(collection, title_query)
                if _normalized(item[0]) == _normalized(title_query)
            ]
            exact.sort(key=lambda item: item[0].casefold() != title_query.casefold())
            exact = exact[:1]
            parameters = urllib.parse.urlencode(
                {
                    "pattern": clean_query,
                    "books.name": self.source_books[collection],
                    "pageLength": self.maximum_sources,
                    "format": "xml",
                }
            )
            try:
                raw, _url = self._open(f"/search?{parameters}", maximum=512_000)
                root = ET.fromstring(raw)
            except (OSError, ValueError, ET.ParseError):
                results = self._suggestions(collection, clean_query)
            else:
                entries = [
                    node
                    for node in root.iter()
                    if node.tag.rsplit("}", 1)[-1] in {"entry", "item"}
                ]
                results = []
                for entry in entries:
                    title = self._entry_value(entry, "title")
                    href = ""
                    for child in entry.iter():
                        if child.tag.rsplit("}", 1)[-1] == "link":
                            href = (
                                child.attrib.get("href") or (child.text or "").strip()
                            )
                            if "/content/" in href or "/raw/" in href:
                                break
                    results.append(
                        (title, href, self._entry_value(entry, "description"))
                    )
            if exact:
                results = exact
            elif not results:
                results = self._suggestions(collection, clean_query)
            for title, href, description in results:
                if len(extracts) >= self.maximum_sources:
                    break
                if not title or not href:
                    continue
                header = f"SOURCE {len(extracts) + 1} [{collection}] — {title}\n"
                remaining = (
                    self.maximum_characters
                    - sum(len(part) + 2 for part in extracts)
                    - len(header)
                )
                if remaining < 150:
                    break
                snippet = readable_html(description, 900)
                final_url = ""
                try:
                    parsed = urllib.parse.urlparse(href)
                    local_path = parsed.path + (
                        ("?" + parsed.query) if parsed.query else ""
                    )
                    article, final_url = self._open(local_path, maximum=2_000_000)
                    text = article_excerpt(
                        article.decode("utf-8", errors="replace"),
                        clean_query,
                        subject,
                        maximum=min(3600 if exact else 1800, remaining),
                    )
                except (OSError, ValueError):
                    text = snippet
                if len(text) < 80:
                    continue
                extracts.append(header + text[:remaining])
                sources.append(final_url or href)
            if len(extracts) >= self.maximum_sources:
                break
        if not extracts:
            LOG.write(
                "search_complete",
                sources=0,
                elapsed_seconds=round(time.perf_counter() - started, 3),
            )
            return None
        joined = "\n\n".join(extracts)[: self.maximum_characters]
        LOG.write(
            "search_complete",
            sources=len(sources),
            elapsed_seconds=round(time.perf_counter() - started, 3),
        )
        return ResearchMaterial(clean_query, joined, tuple(sources))

    def random_topic(self) -> ResearchMaterial | None:
        if self.process is None:
            return None
        for _attempt in range(5):
            try:
                raw, final_url = self._open(
                    "/random?content=" + urllib.parse.quote(self.random_book),
                    maximum=2_000_000,
                )
                text = readable_html(raw.decode("utf-8", errors="replace"), 1800)
                title = urllib.parse.unquote(
                    urllib.parse.urlparse(final_url).path.rsplit("/", 1)[-1]
                )
            except (OSError, ValueError):
                continue
            if len(text) < 120 or self.RANDOMLY_EXCLUDED.search(
                title + " " + text[:500]
            ):
                continue
            payload = f"SUJET LOCAL — {title}\n{text}"
            return ResearchMaterial(
                title, payload[: self.maximum_characters], (final_url,)
            )
        return None


def research_decision(raw: str) -> ResearchRequest | None:
    """Retourne une demande bornee depuis le JSON du modele de controle."""
    match = re.search(r"\{.*?\}", raw, flags=re.DOTALL)
    if match is None:
        return None
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict) or value.get("search") is not True:
        return None
    query = value.get("query")
    if not isinstance(query, str):
        return None
    clean_query = " ".join(query.split())[:180]
    allowed = {"wikipedia", "wiktionary", "wikivoyage", "gutenberg", "french"}
    raw_sources = value.get("sources", ["wikipedia"])
    if not isinstance(raw_sources, list):
        raw_sources = ["wikipedia"]
    sources = tuple(
        dict.fromkeys(
            item for item in raw_sources if isinstance(item, str) and item in allowed
        )
    )[:3]
    if not clean_query:
        return None
    subject = value.get("subject", "")
    subject = " ".join(subject.split())[:180] if isinstance(subject, str) else ""
    return ResearchRequest(clean_query, sources or ("wikipedia",), subject)

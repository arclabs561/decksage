#!/usr/bin/env python3
"""Non-learned substitute-scoring baselines for ``compare_recommendations.py``.

The owner's bar is "ML has to beat heuristics". This module supplies the
heuristics, so the bar has something to be measured against. Nothing here is
fitted on annotations: every weight and constant is fixed a priori and recorded
in the docstring of its scorer. Tuning any of them on
``data/test_sets/annotated_*_v2.json`` would turn the baseline into a learned
model and destroy the comparison.

Three baselines, increasing strength:

B1 ``LexicalIndex``     -- BM25 over ``oracle_text``.
B2 ``StructuredIndex``  -- B1 plus type / mana value / colour / keyword matching.
B3 ``RoleIndex``        -- design only (see the report), Adamic-Adar over
                           co-occurrence neighbours fused with B2.

Each index duck-types the harness's ``SourceIndex``: ``name``, ``path``, ``keys``,
``positions``, ``dim``, ``__contains__`` and ``cosines(query, candidates)``. That
means ``build_arm`` can wrap one in the existing ``Scorer`` without changing the
scoring path, the candidate-set assertion or the metrics.

Scores are cosine-like and live in roughly [0, 1], so an arm's ``describe()``
output stays comparable with an embedding arm's. They are *not* calibrated
probabilities and must never be thresholded as such.
"""

from __future__ import annotations

import csv
import math
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from scipy import sparse

from ml.utils.paths import PATHS


sys.path.insert(0, str(Path(__file__).resolve().parent))

#: A spec of the form ``b1``, ``b2`` or ``heuristic:b1`` names a heuristic arm.
HEURISTIC_PREFIX = "heuristic:"
HEURISTIC_NAMES = ("b1", "b2")
METADATA_PATTERN = str(PATHS.processed / "card_attributes_{game}_enriched.csv")

#: Supertype words that say nothing about which slot a card fills.
SUPERTYPES = frozenset({"basic", "legendary", "snow", "world", "ongoing", "host", "elite", "token"})

#: Closed-class English words with no rules meaning in oracle text. Everything
#: else is left to inverse document frequency, which already down-weights the
#: ubiquitous words ("you", "target", "control") without hand-listing them.
STOPWORDS = frozenset(
    """
    a an the of to in on at for with from by and or nor not is are be been being
    as it its this that these those if then than when whenever while each other
    into onto up down out over under own same so such both either neither do does
    did has have had will would can could may might must shall should you your
    """.split()
)

COLOUR_BITS = {"W": 1, "U": 2, "B": 4, "R": 8, "G": 16}
POPCOUNT = np.array([bin(value).count("1") for value in range(32)], dtype=np.float64)

_MANA_SYMBOL = re.compile(r"\{[^}]*\}")
_REMINDER = re.compile(r"\([^()]*\)")
_PT_COUNTER = re.compile(r"[+-]\d+\s*/\s*[+-]\d+")
_WORD = re.compile(r"[a-z][a-z']*")

#: B2's fixed weights. Relative; see ``StructuredIndex`` for the rule.
B2_WEIGHTS = {
    "type": 0.30,
    "mana_value": 0.20,
    "colour": 0.15,
    "keyword": 0.10,
    "text": 0.25,
}


class HeuristicError(RuntimeError):
    """A heuristic arm cannot be built or scored as asked."""


def is_heuristic_spec(spec: str) -> bool:
    """Whether ``spec`` names a heuristic rather than an embedding artefact."""
    name = spec.strip().lower()
    if name.startswith(HEURISTIC_PREFIX):
        name = name[len(HEURISTIC_PREFIX) :]
    return name in HEURISTIC_NAMES


def metadata_path_for(game: str, override: Path | None = None) -> Path:
    """The enriched attribute table for ``game``, or an explicit override."""
    if override is not None:
        if not override.exists():
            raise HeuristicError(f"metadata table not found: {override}")
        return override
    path = Path(METADATA_PATTERN.format(game=game))
    if not path.exists():
        raise HeuristicError(f"no heuristic metadata for {game!r}; tried {path}")
    return path


# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------


def tokenize(text: str) -> list[str]:
    """Tokens for BM25 over oracle text, deterministically.

    Four decisions, each of which changes the ranking:

    1. Reminder text is stripped. Parenthesised spans restate evergreen rules
       ("(This creature can't be blocked except by ...)") and are copied across
       thousands of cards, so leaving them in inflates similarity between cards
       that share only a keyword's boilerplate. Cost: rules clarifications that
       genuinely narrow a card's function are lost too.
    2. Mana symbols are removed entirely. ``{2}{G}`` is a structured feature and
       is scored by B2's mana-value component; leaving the symbols in the text
       would double-count cost.
    3. Numeric literals and +N/+N counters collapse to single placeholders.
       "draw two cards" and "draw three cards" are the same role; the exact
       quantity is a magnitude, not a function. Damage and life totals lose the
       same resolution, deliberately.
    4. A closed-class stopword list is dropped; everything else relies on IDF.
    """
    normalised = unicodedata.normalize("NFKC", text or "").lower()
    normalised = _MANA_SYMBOL.sub(" ", normalised)
    previous = None
    while previous != normalised:  # innermost-out; MTG reminder text does not nest
        previous = normalised
        normalised = _REMINDER.sub(" ", normalised)
    normalised = _PT_COUNTER.sub(" ptcounter ", normalised)
    normalised = re.sub(r"\d+", " num ", normalised)
    tokens = []
    for raw in _WORD.findall(normalised):
        token = raw.strip("'")
        if token in STOPWORDS:
            continue
        if len(token) < 2 and token != "x":
            continue
        tokens.append(token)
    return tokens


# ---------------------------------------------------------------------------
# Card metadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CardAttributes:
    """The fields a non-learned scorer can read, per card."""

    name: str
    type_line: str
    oracle_text: str
    mana_cost: str
    mana_value: float
    colour_mask: int
    rarity: str
    keywords: tuple[str, ...]
    type_words: tuple[str, ...]
    primary_type: str


def _colour_mask(colour_identity: str) -> int:
    mask = 0
    for letter in (colour_identity or "").strip().upper():
        mask |= COLOUR_BITS.get(letter, 0)
    return mask


def _split_list(raw: str) -> tuple[str, ...]:
    if not raw or not raw.strip():
        return ()
    parts = re.split(r"[;,]", raw)
    return tuple(dict.fromkeys(part.strip().lower() for part in parts if part.strip()))


def _type_words(type_line: str) -> tuple[tuple[str, ...], str]:
    """Type and subtype words with supertypes removed, and the primary type."""
    left, _, right = (type_line or "").partition("—")
    left = left.split("//")[0]
    words = [word for word in re.split(r"[^a-z]+", left.lower()) if word and word not in SUPERTYPES]
    subtypes = [word for word in re.split(r"[^a-z]+", right.lower()) if word]
    primary = words[0] if words else ""
    return tuple(dict.fromkeys([*words, *subtypes])), primary


@lru_cache(maxsize=4)
def load_attributes(path_str: str) -> tuple[dict[str, CardAttributes], tuple[str, ...]]:
    """Read the enriched CSV once, keyed by card name, in file order."""
    path = Path(path_str)
    attributes: dict[str, CardAttributes] = {}
    order: list[str] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("name") or "").strip()
            if not name or name in attributes:
                continue
            type_line = row.get("type") or ""
            type_words, primary = _type_words(type_line)
            try:
                mana_value = float(row.get("cmc") or 0.0)
            except ValueError:
                mana_value = 0.0
            attributes[name] = CardAttributes(
                name=name,
                type_line=type_line,
                oracle_text=row.get("oracle_text") or "",
                mana_cost=row.get("mana_cost") or "",
                mana_value=mana_value,
                colour_mask=_colour_mask(row.get("color_identity_str") or ""),
                rarity=(row.get("rarity") or "").strip().lower(),
                keywords=_split_list(row.get("keyword_abilities") or row.get("keywords") or ""),
                type_words=type_words,
                primary_type=primary,
            )
            order.append(name)
    if not attributes:
        raise HeuristicError(f"metadata table is empty: {path}")
    return attributes, tuple(order)


# ---------------------------------------------------------------------------
# B1: BM25 over oracle text
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LexicalIndex:
    """B1: BM25-weighted cosine over oracle text.

    Assumes substitution is "does the same job", and that the job is stated in
    the rules text. The assumption fails for cards whose text is empty or purely
    numeric (vanilla creatures, lands), which get no text signal at all.

    Parameters are the standard defaults: ``k1=1.2`` saturates repeated terms,
    ``b=0.75`` normalises document length. IDF is the positive Lucene variant,
    ``ln(1 + (N - df + 0.5) / (df + 0.5))``, so a term in every document scores
    near zero instead of negative. Query terms are a binary indicator (BM25's
    standard qtf=1 form) and both sides are L2-normalised, so the result is a
    cosine in [0, 1] and stays comparable with an embedding arm.
    """

    name: str
    path: Path
    keys: tuple[str, ...]
    positions: Mapping[str, int]
    texts: tuple[str, ...]
    vocabulary: Mapping[str, int]
    rows: Any  # scipy.sparse.csr_matrix; untyped to keep the frozen dataclass simple
    k1: float = 1.2
    b: float = 0.75

    @property
    def dim(self) -> int:
        """No embedding dimension; 0 is how the harness recognises a heuristic."""
        return 0

    def __contains__(self, key: str) -> bool:
        return key in self.positions

    def _query_vector(self, query: str) -> Any:
        tokens = sorted(set(tokenize(self.texts[self.positions[query]])))
        term_ids = [self.vocabulary[token] for token in tokens if token in self.vocabulary]
        if not term_ids:
            return None
        term_ids = sorted(set(term_ids))
        return sparse.csr_matrix(
            (np.ones(len(term_ids)), (np.zeros(len(term_ids), dtype=np.int64), term_ids)),
            shape=(1, len(self.vocabulary)),
        )

    def cosines(self, query: str, candidates: Sequence[str]) -> np.ndarray:
        """Score exactly ``candidates``, in the order given."""
        if query not in self.positions:
            raise HeuristicError(f"{query!r} is not in source {self.name!r}")
        if not candidates:
            return np.zeros(0, dtype=np.float64)
        missing = [candidate for candidate in candidates if candidate not in self.positions]
        if missing:
            raise HeuristicError(
                f"source {self.name!r} lacks candidates {missing[:3]}"
                f"{'' if len(missing) <= 3 else f' (+{len(missing) - 3} more)'}"
            )
        row_ids = np.fromiter(
            (self.positions[candidate] for candidate in candidates),
            dtype=np.int64,
            count=len(candidates),
        )
        query_vector = self._query_vector(query)
        if query_vector is None:
            return np.zeros(len(candidates), dtype=np.float64)
        norm = math.sqrt(float(query_vector.multiply(query_vector).sum()))
        if norm == 0.0:
            return np.zeros(len(candidates), dtype=np.float64)
        scored = self.rows[row_ids] @ query_vector.T
        return np.asarray(scored.todense(), dtype=np.float64).ravel() / norm


def _bm25_rows(
    documents: Sequence[Sequence[str]], vocabulary: Mapping[str, int], k1: float, b: float
) -> Any:
    """CSR matrix of L2-normalised BM25 term weights, one row per document."""
    n_docs = len(documents)
    document_frequency: Counter[str] = Counter()
    lengths = np.zeros(n_docs, dtype=np.float64)
    term_counts: list[Counter[str]] = []
    for position, tokens in enumerate(documents):
        counts = Counter(tokens)
        term_counts.append(counts)
        lengths[position] = len(tokens)
        document_frequency.update(counts)
    average = float(lengths.mean()) if n_docs and lengths.mean() > 0 else 1.0
    idf = {
        term: math.log(1.0 + (n_docs - count + 0.5) / (count + 0.5))
        for term, count in document_frequency.items()
    }
    indptr = np.zeros(n_docs + 1, dtype=np.int64)
    indices: list[int] = []
    data: list[float] = []
    for position, counts in enumerate(term_counts):
        row_norm = k1 * (1.0 - b + b * lengths[position] / average)
        row_terms: list[tuple[int, float]] = []
        for term in sorted(counts):
            frequency = float(counts[term])
            weight = idf[term] * frequency * (k1 + 1.0) / (frequency + row_norm)
            row_terms.append((vocabulary[term], weight))
        magnitude = math.sqrt(sum(weight * weight for _, weight in row_terms)) or 1.0
        for term_id, weight in row_terms:
            indices.append(term_id)
            data.append(weight / magnitude)
        indptr[position + 1] = len(indices)
    return sparse.csr_matrix(
        (np.asarray(data, dtype=np.float64), np.asarray(indices, dtype=np.int64), indptr),
        shape=(n_docs, len(vocabulary)),
    )


def build_lexical(game: str, metadata: Path | None = None) -> LexicalIndex:
    """B1 arm: one BM25 row per card in the enriched table."""
    path = metadata_path_for(game, metadata)
    attributes, order = load_attributes(str(path))
    texts = tuple(attributes[name].oracle_text for name in order)
    documents = [tokenize(text) for text in texts]
    vocabulary: dict[str, int] = {}
    for tokens in documents:
        for token in sorted(set(tokens)):
            vocabulary.setdefault(token, len(vocabulary))
    return LexicalIndex(
        name=f"heuristic:b1:{game}",
        path=path,
        keys=order,
        positions={name: index for index, name in enumerate(order)},
        texts=texts,
        vocabulary=vocabulary,
        rows=_bm25_rows(documents, vocabulary, 1.2, 0.75),
    )


# ---------------------------------------------------------------------------
# B2: structured attribute matching
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StructuredIndex:
    """B2: B1's text score plus four attribute components.

    The weighting rule, fixed before measurement:

    - ``type`` 0.30 -- a slot is defined first by what kind of card fills it. An
      Instant does not replace a Creature at any cost. Half the credit is exact
      primary-type match, half is Jaccard over type and subtype words, so
      "Creature -- Elf Druid" against "Creature -- Elf Shaman" scores 0.5 + 0.33.
    - ``mana_value`` 0.20 -- full credit within +/-1, then linear decay to zero
      two steps out. Cost is the tightest curve constraint in deck building: a
      five-drop cannot replace a one-drop without rebuilding the deck's curve.
    - ``colour`` 0.15 -- Jaccard over colour-identity sets, with colourless
      against colourless scoring 1.0. Lower than type and cost because colour is
      a soft constraint in multicolour and Commander decks, but a green
      two-drop still cannot be cast in a mono-blue deck.
    - ``keyword`` 0.10 -- Jaccard over keyword ability sets. Keywords are a
      coarse role hint (Flying, Trample, Flash) and overlap is sparse, so this
      gets the least weight of the structural components.
    - ``text`` 0.25 -- B1's BM25 cosine, clipped to [0, 1]. Mechanics text is
      the richest signal but the noisiest, so it sits below type plus cost
      together (0.50) rather than dominating.

    Why this order and not equal weights: type and mana value are the two
    constraints a deck cannot flex (legality and curve), colour identity is a
    castability constraint that multicolour decks relax, and keyword/text
    overlap is preference. The weights encode that prior; they were not fitted.

    Missing attributes are *masked*: when either card lacks the field (no
    keywords on 55% of cards, no oracle text on 7.7%), that component is dropped
    and the remaining weights renormalise. Otherwise two vanilla cards would earn
    full keyword credit for sharing nothing. Consequence: a pair of text-less
    cards is ranked on structure alone, and a pair with no shared keywords is
    ranked as if keywords did not exist. The rule is identical for both arms, so
    the comparison stays fair; absolute scores are not comparable across queries.
    """

    name: str
    path: Path
    keys: tuple[str, ...]
    positions: Mapping[str, int]
    lexical: LexicalIndex
    primary: np.ndarray
    type_matrix: Any
    mana_value: np.ndarray
    colour_mask: np.ndarray
    keyword_matrix: Any
    has_text: np.ndarray
    has_keywords: np.ndarray
    weights: Mapping[str, float]

    @property
    def dim(self) -> int:
        return 0

    def __contains__(self, key: str) -> bool:
        return key in self.positions

    def cosines(self, query: str, candidates: Sequence[str]) -> np.ndarray:
        """Score exactly ``candidates``, in the order given."""
        if query not in self.positions:
            raise HeuristicError(f"{query!r} is not in source {self.name!r}")
        if not candidates:
            return np.zeros(0, dtype=np.float64)
        missing = [candidate for candidate in candidates if candidate not in self.positions]
        if missing:
            raise HeuristicError(
                f"source {self.name!r} lacks candidates {missing[:3]}"
                f"{'' if len(missing) <= 3 else f' (+{len(missing) - 3} more)'}"
            )
        row_ids = np.fromiter(
            (self.positions[candidate] for candidate in candidates),
            dtype=np.int64,
            count=len(candidates),
        )
        return self.score_rows(self.positions[query], row_ids)

    def score_rows(self, query_row: int, rows: np.ndarray) -> np.ndarray:
        """Weighted, masked mean over the five components, one value per row."""
        total = np.zeros(rows.size, dtype=np.float64)
        weight_sum = np.zeros(rows.size, dtype=np.float64)

        similarity = 0.5 * (self.primary[rows] == self.primary[query_row]) + 0.5 * _jaccard(
            self.type_matrix, query_row, rows
        )
        total += self.weights["type"] * similarity
        weight_sum += self.weights["type"]

        delta = np.abs(self.mana_value[rows] - self.mana_value[query_row])
        total += self.weights["mana_value"] * _plateau(delta)
        weight_sum += self.weights["mana_value"]

        total += self.weights["colour"] * _colour_jaccard(
            self.colour_mask[query_row], self.colour_mask[rows]
        )
        weight_sum += self.weights["colour"]

        keyword_rows = self.has_keywords[rows] & self.has_keywords[query_row]
        keyword_score = np.where(keyword_rows, _jaccard(self.keyword_matrix, query_row, rows), 0.0)
        total += self.weights["keyword"] * keyword_score
        weight_sum += np.where(keyword_rows, self.weights["keyword"], 0.0)

        text_rows = self.has_text[rows] & self.has_text[query_row]
        candidate_names = [self.keys[row] for row in rows]
        text_score = np.clip(self.lexical.cosines(self.keys[query_row], candidate_names), 0.0, 1.0)
        total += np.where(text_rows, self.weights["text"] * text_score, 0.0)
        weight_sum += np.where(text_rows, self.weights["text"], 0.0)

        return np.divide(total, weight_sum, out=np.zeros_like(total), where=weight_sum > 0)


def _jaccard(matrix: Any, query_row: int, rows: np.ndarray) -> np.ndarray:
    """Jaccard over multi-hot rows; two empty rows score 0.0, not 1.0."""
    subset = matrix[rows]
    product = subset @ matrix[query_row].T
    intersection = np.asarray(product.todense()).ravel().astype(np.float64)
    row_sizes = np.asarray(subset.sum(axis=1)).ravel().astype(np.float64)
    query_size = float(matrix[query_row].sum())
    union = row_sizes + query_size - intersection
    both = (row_sizes > 0) & (query_size > 0)
    return np.divide(intersection, union, out=np.zeros_like(intersection), where=both & (union > 0))


def _colour_jaccard(query_mask: int, masks: np.ndarray) -> np.ndarray:
    """Jaccard over colour-identity bitmasks; colourless against colourless is 1.0."""
    intersection = POPCOUNT[np.bitwise_and(masks, query_mask)]
    union = POPCOUNT[np.bitwise_or(masks, query_mask)]
    return np.divide(intersection, union, out=np.ones_like(intersection), where=union > 0)


def _plateau(delta: np.ndarray) -> np.ndarray:
    """1.0 within +/-1 mana value, then linear to 0.0 two steps out."""
    return np.clip(1.0 - np.maximum(delta - 1.0, 0.0) / 2.0, 0.0, 1.0)


def _multi_hot(order: Sequence[str], attributes: Mapping[str, CardAttributes], field: str) -> Any:
    """CSR multi-hot indicator for one tuple-valued attribute."""
    vocabulary: dict[str, int] = {}
    for name in order:
        for term in sorted(getattr(attributes[name], field)):
            vocabulary.setdefault(term, len(vocabulary))
    indptr = np.zeros(len(order) + 1, dtype=np.int64)
    indices: list[int] = []
    for position, name in enumerate(order):
        for term in sorted(getattr(attributes[name], field)):
            indices.append(vocabulary[term])
        indptr[position + 1] = len(indices)
    return sparse.csr_matrix(
        (np.ones(len(indices), dtype=np.float64), np.asarray(indices, dtype=np.int64), indptr),
        shape=(len(order), len(vocabulary)),
    )


def build_structured(game: str, metadata: Path | None = None) -> StructuredIndex:
    """B2 arm: B1 plus type, mana value, colour and keyword matching."""
    path = metadata_path_for(game, metadata)
    attributes, order = load_attributes(str(path))
    return StructuredIndex(
        name=f"heuristic:b2:{game}",
        path=path,
        keys=order,
        positions={name: index for index, name in enumerate(order)},
        lexical=build_lexical(game, path),
        primary=np.array([attributes[name].primary_type for name in order], dtype=object),
        type_matrix=_multi_hot(order, attributes, "type_words"),
        mana_value=np.array([attributes[name].mana_value for name in order], dtype=np.float64),
        colour_mask=np.array([attributes[name].colour_mask for name in order], dtype=np.int64),
        keyword_matrix=_multi_hot(order, attributes, "keywords"),
        has_text=np.array([bool(attributes[name].oracle_text.strip()) for name in order]),
        has_keywords=np.array([bool(attributes[name].keywords) for name in order]),
        weights=B2_WEIGHTS,
    )


def build_heuristic(spec: str, game: str, metadata: Path | None = None) -> Any:
    """Build the heuristic index named by ``spec``."""
    name = spec.strip().lower()
    if name.startswith(HEURISTIC_PREFIX):
        name = name[len(HEURISTIC_PREFIX) :]
    if name == "b1":
        return build_lexical(game, metadata)
    if name == "b2":
        return build_structured(game, metadata)
    raise HeuristicError(f"unknown heuristic {spec!r}; expected one of {HEURISTIC_NAMES}")

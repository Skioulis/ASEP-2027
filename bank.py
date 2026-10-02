"""The question bank as JSON files: validate, seed, import and export.

On-disk format (also the admin import/export format):

    index.json              [{name, slug, count}]
    categories/<slug>.json  [{id, n, q, a, c}]

``id`` is "<slug>-<n>", ``n`` the number printed in the PDF (optional on
import; defaults to the item's 1-based position), ``q`` the question text,
``a`` exactly four options (α..δ) and ``c`` the 0-based correct index.
"""

from __future__ import annotations

import json
import os
import re

from sqlalchemy import func, select

from extensions import db
from models import Category, Question

# Question ids end up in inline JS/HTML on the browse page: keep them boring.
ID_RE = re.compile(r"[a-z0-9._-]+")


class BankError(ValueError):
    """Question data failed validation; ``problems`` lists every issue."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_items(items: object, slug: str) -> list[str]:
    """Return human-readable problems with one category's items (empty = valid)."""
    if not isinstance(items, list):
        return ["Το αρχείο πρέπει να περιέχει λίστα ερωτήσεων (JSON array)."]
    problems: list[str] = []
    seen: set[str] = set()
    for pos, item in enumerate(items, 1):
        if not isinstance(item, dict):
            problems.append(f"Ερώτηση {pos}: δεν είναι αντικείμενο JSON.")
            continue
        qid = item.get("id")
        label = f"Ερώτηση {pos} ({qid})"
        if not isinstance(qid, str) or not qid.startswith(f"{slug}-"):
            problems.append(f"{label}: το id πρέπει να αρχίζει με «{slug}-».")
        elif not ID_RE.fullmatch(qid):
            problems.append(f"{label}: το id επιτρέπεται να περιέχει μόνο λατινικά πεζά, ψηφία και . _ -")
        elif qid in seen:
            problems.append(f"{label}: διπλό id.")
        else:
            seen.add(qid)
        if not isinstance(item.get("q"), str) or not item["q"].strip():
            problems.append(f"{label}: λείπει το κείμενο της ερώτησης.")
        options = item.get("a")
        if not (isinstance(options, list) and len(options) == 4
                and all(isinstance(o, str) and o.strip() for o in options)):
            problems.append(f"{label}: χρειάζονται ακριβώς 4 μη κενές απαντήσεις.")
        if not (_is_int(item.get("c")) and 0 <= item["c"] <= 3):
            problems.append(f"{label}: η σωστή απάντηση (c) πρέπει να είναι 0–3.")
        number = item.get("n", pos)
        if not (_is_int(number) and number > 0):
            problems.append(f"{label}: ο αριθμός (n) πρέπει να είναι θετικός ακέραιος.")
    return problems


def read_bank(data_dir: str) -> list[dict]:
    """Read and validate a bank directory → [{slug, name, items}] in index order."""
    with open(os.path.join(data_dir, "index.json"), encoding="utf-8") as fh:
        index = json.load(fh)
    bank, problems = [], []
    for entry in index:
        path = os.path.join(data_dir, "categories", f"{entry['slug']}.json")
        with open(path, encoding="utf-8") as fh:
            items = json.load(fh)
        problems += [f"{entry['slug']}: {p}" for p in validate_items(items, entry["slug"])]
        bank.append({"slug": entry["slug"], "name": entry["name"], "items": items})
    if problems:
        raise BankError(problems)
    return bank


def _new_question(item: dict, pos: int, category: Category) -> Question:
    return Question(id=item["id"], number=item.get("n", pos), text=item["q"],
                    options=list(item["a"]), correct=item["c"], category=category)


def seed(data_dir: str) -> int:
    """Load the bank into an empty database; return questions inserted (0 = already seeded)."""
    if db.session.scalar(select(func.count()).select_from(Question)):
        return 0
    total = 0
    for position, entry in enumerate(read_bank(data_dir)):
        category = Category(slug=entry["slug"], name=entry["name"], position=position)
        db.session.add(category)
        for pos, item in enumerate(entry["items"], 1):
            db.session.add(_new_question(item, pos, category))
            total += 1
    db.session.commit()
    return total

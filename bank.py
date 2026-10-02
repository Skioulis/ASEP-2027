"""The question bank as JSON files: validate, seed, import and export.

On-disk format (also the admin import/export format):

    index.json              [{name, slug, count}]
    categories/<slug>.json  [{id, n, q, a, c}]

``id`` is "<slug>-<n>", ``n`` the number printed in the PDF (optional on
import; defaults to the item's 1-based position), ``q`` the question text,
``a`` exactly four options (α..δ) and ``c`` the 0-based correct index.
"""

from __future__ import annotations

import io
import json
import os
import re
import zipfile
from dataclasses import dataclass, field

from sqlalchemy import func, select

from extensions import db
from models import Attempt, Category, Question

# Question ids end up in inline JS/HTML on the browse page: keep them boring.
ID_RE = re.compile(r"[a-z0-9._-]+")
# Question numbers are stored in a 32-bit-safe integer column.
MAX_NUMBER = 2_147_483_647


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
        if not (_is_int(number) and 0 < number <= MAX_NUMBER):
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
    """Load the bank into a database with no categories; return questions inserted.

    Returns 0 when categories already exist. The app never deletes categories,
    so this stays a no-op even if an admin has emptied every category.
    """
    if db.session.scalar(select(func.count()).select_from(Category)):
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


def category_items(category: Category) -> list[dict]:
    """A category's questions in the on-disk item format."""
    return [{"id": q.id, "n": q.number, "q": q.text, "a": list(q.options), "c": q.correct}
            for q in category.questions]


def export_zip() -> bytes:
    """The whole bank as a zip of index.json + categories/<slug>.json."""
    categories = db.session.scalars(select(Category).order_by(Category.position)).all()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        index = []
        for category in categories:
            items = category_items(category)
            archive.writestr(f"categories/{category.slug}.json",
                             json.dumps(items, ensure_ascii=False, indent=1))
            index.append({"name": category.name, "slug": category.slug, "count": len(items)})
        archive.writestr("index.json", json.dumps(index, ensure_ascii=False, indent=1))
    return buffer.getvalue()


@dataclass
class ImportPlan:
    """What importing a file into a category would do (or did)."""
    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: int = 0
    attempts_removed: int = 0


def plan_import(category: Category, items: object) -> ImportPlan:
    """Diff ``items`` against the category by id. Raises BankError if invalid."""
    problems = validate_items(items, category.slug)
    if problems:
        raise BankError(problems)
    existing = {q.id: q for q in category.questions}
    plan = ImportPlan()
    for pos, item in enumerate(items, 1):
        question = existing.get(item["id"])
        if question is None:
            plan.added.append(item["id"])
        elif ((question.number, question.text, list(question.options), question.correct)
              != (item.get("n", pos), item["q"], list(item["a"]), item["c"])):
            plan.changed.append(item["id"])
        else:
            plan.unchanged += 1
    if plan.added:
        clash = db.session.scalars(select(Question.id).where(Question.id.in_(plan.added))).all()
        if clash:
            raise BankError([f"Το id {qid} υπάρχει ήδη σε άλλη κατηγορία." for qid in clash])
    incoming = {item["id"] for item in items}
    plan.removed = [qid for qid in existing if qid not in incoming]
    if plan.removed:
        plan.attempts_removed = db.session.scalar(
            select(func.count()).select_from(Attempt)
            .where(Attempt.question_id.in_(plan.removed)))
    return plan


def apply_import(category: Category, items: list[dict]) -> ImportPlan:
    """Replace the category's questions with ``items``; attempts on removed ones are deleted."""
    plan = plan_import(category, items)
    existing = {q.id: q for q in category.questions}
    for qid in plan.removed:
        db.session.delete(existing[qid])
    for pos, item in enumerate(items, 1):
        question = existing.get(item["id"])
        if question is None:
            db.session.add(_new_question(item, pos, category))
        else:
            question.number = item.get("n", pos)
            question.text = item["q"]
            question.options = list(item["a"])
            question.correct = item["c"]
    db.session.commit()
    return plan

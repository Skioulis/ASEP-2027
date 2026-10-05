import os
import re

import pytest
from sqlalchemy import func, select

import bank
from extensions import db
from models import Category, Question
from tests.conftest import FIXTURE_BANK

REAL_DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
GOOD = {"id": "alpha-1", "n": 1, "q": "Ερώτηση;", "a": ["α", "β", "γ", "δ"], "c": 0}


def test_validate_accepts_good_items():
    assert bank.validate_items([GOOD], "alpha") == []


def test_validate_n_is_optional():
    item = {k: v for k, v in GOOD.items() if k != "n"}
    assert bank.validate_items([item], "alpha") == []


def test_validate_rejects_numbers_beyond_sqlite_integer_range():
    problems = bank.validate_items([dict(GOOD, n=10**30)], "alpha")
    assert len(problems) == 1 and "αριθμός (n)" in problems[0]
    assert bank.validate_items([dict(GOOD, n=2_147_483_647)], "alpha") == []


def test_validate_rejects_non_list():
    assert len(bank.validate_items({"id": "x"}, "alpha")) == 1


def test_validate_reports_every_problem():
    items = [
        GOOD,
        dict(GOOD),                                   # duplicate id
        dict(GOOD, id="beta-1"),                      # wrong prefix
        dict(GOOD, id="alpha-3", a=["α", "β", "γ"]),  # 3 options
        dict(GOOD, id="alpha-4", c=4),                # c out of range
        dict(GOOD, id="alpha-5", q="  "),             # empty question
        dict(GOOD, id="alpha-6", c=True),             # bool is not an index
    ]
    problems = bank.validate_items(items, "alpha")
    assert len(problems) == 6
    assert "διπλό id" in problems[0]
    assert "alpha-" in problems[1]


def test_validate_rejects_unsafe_id_characters():
    for bad_id in ("alpha-1');alert(1)//",   # quote/paren/slash would break inline JS
                   "alpha-Α1"):              # Greek capital alpha, not a latin "A"
        problems = bank.validate_items([dict(GOOD, id=bad_id)], "alpha")
        assert len(problems) == 1, bad_id
        assert "μόνο λατινικά" in problems[0]


def test_read_bank_returns_categories_in_index_order():
    data = bank.read_bank(FIXTURE_BANK)
    assert [c["slug"] for c in data] == ["alpha", "beta"]
    assert [len(c["items"]) for c in data] == [3, 2]


def test_real_extracted_bank_is_valid():
    data = bank.read_bank(REAL_DATA)
    assert len(data) == 11
    assert sum(len(c["items"]) for c in data) == 1988


def test_read_bank_raises_with_all_problems(tmp_path):
    (tmp_path / "categories").mkdir()
    (tmp_path / "index.json").write_text('[{"name": "Άλφα", "slug": "alpha", "count": 1}]')
    (tmp_path / "categories" / "alpha.json").write_text('[{"id": "zzz", "q": "", "a": [], "c": 9}]')
    with pytest.raises(bank.BankError) as excinfo:
        bank.read_bank(str(tmp_path))
    assert len(excinfo.value.problems) == 4


def test_seed_loads_once(app):
    assert bank.seed(FIXTURE_BANK) == 5
    assert bank.seed(FIXTURE_BANK) == 0
    assert db.session.scalar(select(func.count()).select_from(Question)) == 5
    alpha = db.session.scalar(select(Category).filter_by(slug="alpha"))
    assert [q.id for q in alpha.questions] == ["alpha-1", "alpha-2", "alpha-3"]
    assert alpha.questions[1].options[0] == "120"


def test_seed_after_bank_emptied_is_noop(app):
    bank.seed(FIXTURE_BANK)
    for category in db.session.scalars(select(Category)).all():
        bank.apply_import(category, [])
    assert db.session.scalar(select(func.count()).select_from(Question)) == 0
    assert bank.seed(FIXTURE_BANK) == 0


def test_seed_cli_command(app):
    runner = app.test_cli_runner()
    assert "Seeded 5 questions." in runner.invoke(args=["seed"]).output
    assert "Bank already loaded; nothing to do." in runner.invoke(args=["seed"]).output


SEPARATOR = re.compile(r"^\|(\s*:?-{3,}:?\s*\|)+$")


def _table_blocks(text):
    """Runs of consecutive lines that start with "|" (same rule as static/app.js)."""
    blocks, current = [], []
    for line in text.split("\n"):
        if line.strip().startswith("|"):
            current.append(line.strip())
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def test_real_bank_tables_are_well_formed():
    tables = {}
    for category in bank.read_bank(REAL_DATA):
        for item in category["items"]:
            for block in _table_blocks(item["q"]):
                rows = [r for r in block if not SEPARATOR.match(r)]
                widths = {len(r.strip("|").split("|")) for r in rows}
                assert all(r.endswith("|") for r in block), item["id"]
                assert len(widths) == 1 and widths.pop() >= 2, item["id"]
                tables[item["id"]] = block
    assert sorted(tables) == ["oikonomikes-epistimes-150", "oikonomikes-epistimes-197"]
    assert SEPARATOR.match(tables["oikonomikes-epistimes-150"][1])       # header row
    assert not any(SEPARATOR.match(r) for r in tables["oikonomikes-epistimes-197"])

import io
import json
import zipfile

import pytest
from sqlalchemy import select

import bank
from extensions import db
from models import Attempt, Category, Question


def _alpha():
    return db.session.scalar(select(Category).filter_by(slug="alpha"))


def _edited_alpha_items():
    """alpha-1 unchanged, alpha-2 reworded, alpha-3 dropped, alpha-4 new."""
    items = bank.category_items(_alpha())
    items[1]["q"] = "Πόσα άρθρα έχει σήμερα το Σύνταγμα;"
    del items[2]
    items.append({"id": "alpha-4", "n": 4, "q": "Νέα;", "a": ["1", "2", "3", "4"], "c": 3})
    return items


def test_plan_import_diffs_by_id(bank_loaded, user):
    db.session.add(Attempt(user_id=user.id, question_id="alpha-3", chosen=0,
                           is_correct=False, mode="quiz"))
    db.session.commit()
    plan = bank.plan_import(_alpha(), _edited_alpha_items())
    assert plan.added == ["alpha-4"]
    assert plan.changed == ["alpha-2"]
    assert plan.removed == ["alpha-3"]
    assert plan.unchanged == 1
    assert plan.attempts_removed == 1


def test_apply_import_replaces_category(bank_loaded):
    bank.apply_import(_alpha(), _edited_alpha_items())
    assert [q.id for q in _alpha().questions] == ["alpha-1", "alpha-2", "alpha-4"]
    assert db.session.get(Question, "alpha-2").text == "Πόσα άρθρα έχει σήμερα το Σύνταγμα;"


def test_plan_import_rejects_invalid_items(bank_loaded):
    with pytest.raises(bank.BankError):
        bank.plan_import(_alpha(), [{"id": "beta-1", "q": "x", "a": ["1", "2", "3", "4"], "c": 0}])


def test_export_round_trips_unchanged(bank_loaded):
    archive = zipfile.ZipFile(io.BytesIO(bank.export_zip()))
    index = json.loads(archive.read("index.json"))
    assert [(c["slug"], c["count"]) for c in index] == [("alpha", 3), ("beta", 2)]
    items = json.loads(archive.read("categories/alpha.json"))
    plan = bank.plan_import(_alpha(), items)
    assert (plan.added, plan.changed, plan.removed, plan.unchanged) == ([], [], [], 3)


def test_export_view_downloads_zip(admin_client, bank_loaded):
    response = admin_client.get("/admin/export")
    assert response.mimetype == "application/zip"
    assert "asep-questions.zip" in response.headers["Content-Disposition"]


def _upload(client, items, category="alpha"):
    payload = json.dumps(items, ensure_ascii=False).encode()
    return client.post("/admin/import", data={"category": category,
                                              "file": (io.BytesIO(payload), "alpha.json")},
                       content_type="multipart/form-data")


def test_import_preview_then_confirm(admin_client, bank_loaded):
    items = _edited_alpha_items()
    preview = _upload(admin_client, items)
    html = preview.get_data(as_text=True)
    assert preview.status_code == 200 and "Επιβεβαίωση εισαγωγής" in html
    assert db.session.get(Question, "alpha-4") is None          # nothing written yet

    confirm = admin_client.post("/admin/import", data={
        "category": "alpha", "confirm": "1", "payload": json.dumps(items, ensure_ascii=False)})
    assert confirm.headers["Location"] == "/admin/questions?category=alpha"
    assert db.session.get(Question, "alpha-4") is not None
    assert db.session.get(Question, "alpha-3") is None


def test_import_shows_validation_problems(admin_client, bank_loaded):
    response = _upload(admin_client, [{"id": "alpha-1", "q": "x", "a": ["1"], "c": 0}])
    assert response.status_code == 400
    assert "4 μη κενές απαντήσεις" in response.get_data(as_text=True)


def test_import_rejects_broken_json(admin_client, bank_loaded):
    response = admin_client.post("/admin/import", data={
        "category": "alpha", "file": (io.BytesIO(b"{not json"), "x.json")},
        content_type="multipart/form-data")
    assert response.status_code == 400
    assert "Μη έγκυρο JSON" in response.get_data(as_text=True)

from sqlalchemy import select

from extensions import db
from models import Attempt
from views import api


def _answer(client, qid, chosen, mode="quiz"):
    return client.post("/api/attempts", json={"question_id": qid, "chosen": chosen, "mode": mode})


def test_categories(client, bank_loaded):
    assert client.get("/api/categories").get_json() == [
        {"slug": "alpha", "name": "Άλφα Δίκαιο", "count": 3},
        {"slug": "beta", "name": "Βήτα Οικονομία", "count": 2},
    ]


def test_questions_all_and_by_category(client, bank_loaded):
    data = client.get("/api/questions").get_json()
    assert data["total"] == 5 and data["pages"] == 1
    assert [q["id"] for q in data["items"]] == ["alpha-1", "alpha-2", "alpha-3", "beta-1", "beta-2"]
    assert data["items"][0] == {"id": "alpha-1", "n": 1, "q": "Ποια είναι η πρωτεύουσα της Ελλάδας;",
                                "a": ["Θεσσαλονίκη", "Αθήνα", "Πάτρα", "Λάρισα"], "c": 1,
                                "category": "alpha"}
    beta = client.get("/api/questions?category=beta").get_json()
    assert [q["id"] for q in beta["items"]] == ["beta-1", "beta-2"]


def test_questions_pagination(client, bank_loaded, monkeypatch):
    monkeypatch.setattr(api, "PAGE_SIZE", 2)
    page3 = client.get("/api/questions?page=3").get_json()
    assert (page3["page"], page3["pages"], len(page3["items"])) == (3, 3, 1)
    clamped = client.get("/api/questions?page=99").get_json()
    assert clamped["page"] == 3
    assert client.get("/api/questions?page=abc").get_json()["page"] == 1


def test_unknown_category_is_404_json(client, bank_loaded):
    response = client.get("/api/questions?category=nope")
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_quiz_returns_random_unique_questions(client, bank_loaded):
    data = client.get("/api/quiz?size=3").get_json()
    ids = [q["id"] for q in data["items"]]
    assert len(ids) == 3 == len(set(ids))
    assert data["available"] == 5
    everything = client.get("/api/quiz?category=alpha&size=25").get_json()
    assert sorted(q["id"] for q in everything["items"]) == ["alpha-1", "alpha-2", "alpha-3"]


def test_quiz_pools_need_login(client, bank_loaded):
    assert client.get("/api/quiz?pool=wrong").status_code == 401
    assert client.get("/api/quiz?pool=bogus").status_code == 400


def test_quiz_unseen_and_wrong_pools(user_client, bank_loaded):
    _answer(user_client, "alpha-1", 1)   # correct
    _answer(user_client, "alpha-2", 3)   # wrong
    unseen = user_client.get("/api/quiz?category=alpha&pool=unseen").get_json()
    assert [q["id"] for q in unseen["items"]] == ["alpha-3"]
    wrong = user_client.get("/api/quiz?category=alpha&pool=wrong").get_json()
    assert [q["id"] for q in wrong["items"]] == ["alpha-2"]


def test_attempt_requires_login(client, bank_loaded):
    assert _answer(client, "alpha-1", 1).status_code == 401


def test_attempt_is_recorded(user_client, bank_loaded, user):
    response = _answer(user_client, "alpha-1", 0, mode="browse")
    assert response.status_code == 201
    assert response.get_json() == {"is_correct": False, "correct": 1}
    attempt = db.session.scalar(select(Attempt))
    assert (attempt.user_id, attempt.question_id, attempt.chosen, attempt.mode) == \
           (user.id, "alpha-1", 0, "browse")


def test_attempts_are_rate_limited_per_user(user_client, bank_loaded, app):
    app.config["ATTEMPT_RATE"] = (2, 60)
    assert _answer(user_client, "alpha-1", 1).status_code == 201
    assert _answer(user_client, "alpha-1", 1).status_code == 201
    response = _answer(user_client, "alpha-1", 1)
    assert response.status_code == 429
    assert "error" in response.get_json()


def test_attempt_validation(user_client, bank_loaded):
    assert _answer(user_client, "nope-1", 0).status_code == 404
    assert _answer(user_client, 7, 0).status_code == 404
    assert _answer(user_client, "alpha-1", 4).status_code == 400
    assert _answer(user_client, "alpha-1", True).status_code == 400
    assert _answer(user_client, "alpha-1", 0, mode="exam").status_code == 400


def test_attempt_rejects_non_object_body(user_client, bank_loaded):
    # Test with array body
    response = user_client.post("/api/attempts", json=[1])
    assert response.status_code == 400
    assert "error" in response.get_json()

    # Test with string body
    response = user_client.post("/api/attempts", json="x")
    assert response.status_code == 400
    assert "error" in response.get_json()

    # Test with raw JSON string that is not an object
    response = user_client.post("/api/attempts", data="not json", content_type="application/json")
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_quiz_pool_login_checked_before_category(client, bank_loaded):
    # Guest should get 401 for restricted pools before getting 404 for unknown category
    response = client.get("/api/quiz?pool=unseen&category=nope")
    assert response.status_code == 401
    assert "error" in response.get_json()

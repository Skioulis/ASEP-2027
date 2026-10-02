from sqlalchemy import func, select

from extensions import db
from models import Attempt, Question
from stats import latest_status


def _form(text="Νέα ερώτηση;", options=("α1", "β1", "γ1", "δ1"), correct=2):
    data = {"text": text, "correct": correct}
    data.update({f"a{i}": opt for i, opt in enumerate(options)})
    return data


def test_guest_is_sent_to_login(client):
    response = client.get("/admin/questions")
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/login")


def test_regular_user_is_forbidden(user_client):
    assert user_client.get("/admin/questions").status_code == 403


def test_admin_link_only_for_admins(user_client, bank_loaded):
    assert "/admin/" not in user_client.get("/").get_data(as_text=True)


def test_question_list_and_filters(admin_client, bank_loaded):
    html = admin_client.get("/admin/questions").get_data(as_text=True)
    assert "5 ερωτήσεις" in html
    html = admin_client.get("/admin/questions?category=beta").get_data(as_text=True)
    assert "2 ερωτήσεις" in html and "beta-1" in html and "alpha-1" not in html


def test_search_ignores_case_and_greek_accents(admin_client, bank_loaded):
    html = admin_client.get("/admin/questions?q=ΠΡΩΤΕΥΟΥΣΑ").get_data(as_text=True)
    assert "1 ερωτήσεις" in html and "alpha-1" in html
    html = admin_client.get("/admin/questions?q=τοκος").get_data(as_text=True)  # matches option «Ο τόκος»
    assert "beta-2" in html


def test_edit_question(admin_client, bank_loaded):
    response = admin_client.post("/admin/questions/alpha-1", data=_form())
    assert response.status_code == 302
    question = db.session.get(Question, "alpha-1")
    assert (question.text, question.options, question.correct) == \
           ("Νέα ερώτηση;", ["α1", "β1", "γ1", "δ1"], 2)


def test_editing_correct_answer_updates_user_progress(admin_client, bank_loaded, user):
    # alpha-2's correct answer is 0, so choosing 1 was recorded as wrong.
    db.session.add(Attempt(user_id=user.id, question_id="alpha-2", chosen=1,
                           is_correct=False, mode="quiz"))
    db.session.commit()
    assert latest_status(user.id)["alpha-2"] is False
    admin_client.post("/admin/questions/alpha-2", data=_form(
        text="Πόσα άρθρα έχει το Σύνταγμα;", options=("120", "100", "90", "150"), correct=1))
    assert latest_status(user.id)["alpha-2"] is True


def test_edit_rejects_incomplete_form(admin_client, bank_loaded):
    response = admin_client.post("/admin/questions/alpha-1",
                                 data=_form(options=("α1", "", "γ1", "δ1")))
    assert response.status_code == 200
    assert "Συμπληρώστε και τις 4 απαντήσεις" in response.get_data(as_text=True)
    assert db.session.get(Question, "alpha-1").options[1] == "Αθήνα"


def test_new_question_gets_next_number(admin_client, bank_loaded):
    response = admin_client.post("/admin/questions/new?category=beta", data=_form())
    assert response.headers["Location"] == "/admin/questions/beta-3"
    question = db.session.get(Question, "beta-3")
    assert question.number == 3 and question.category.slug == "beta"


def test_delete_question_removes_attempts(admin_client, bank_loaded, admin):
    db.session.add(Attempt(user_id=admin.id, question_id="alpha-3", chosen=2,
                           is_correct=True, mode="quiz"))
    db.session.commit()
    response = admin_client.post("/admin/questions/alpha-3/delete")
    assert response.headers["Location"] == "/admin/questions?category=alpha"
    assert db.session.get(Question, "alpha-3") is None
    assert db.session.scalar(select(func.count()).select_from(Attempt)) == 0


def test_missing_question_is_404(admin_client, bank_loaded):
    assert admin_client.get("/admin/questions/nope-1").status_code == 404

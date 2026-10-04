from extensions import db
from models import Attempt


def test_index_page_has_app_shell(client, bank_loaded):
    html = client.get("/").get_data(as_text=True)
    assert 'name="csrf-token"' in html
    assert 'id="categoryFilter"' in html
    assert "app.js" in html
    assert 'id="poolFilter"' not in html       # pools only for logged-in users


def test_index_links_to_the_official_asep_register(client, bank_loaded):
    html = client.get("/").get_data(as_text=True)
    assert 'href="https://info.asep.gr/mitroo-thematon-gnoseon"' in html
    assert 'target="_blank" rel="noopener"' in html


def test_index_shows_pool_filter_when_logged_in(user_client, bank_loaded):
    html = user_client.get("/").get_data(as_text=True)
    assert 'id="poolFilter"' in html
    assert 'data-auth="1"' in html


def test_stats_requires_login(client):
    response = client.get("/stats")
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/login")


def test_stats_page_shows_progress(user_client, bank_loaded, user):
    db.session.add(Attempt(user_id=user.id, question_id="alpha-2", chosen=1,
                           is_correct=False, mode="quiz"))
    db.session.commit()
    html = user_client.get("/stats").get_data(as_text=True)
    assert "Άλφα Δίκαιο" in html
    assert "1/3" in html
    assert "pool=wrong" in html and "category=alpha" in html


def test_unknown_page_uses_error_template(client):
    response = client.get("/nope")
    assert response.status_code == 404
    assert "Η σελίδα δεν βρέθηκε" in response.get_data(as_text=True)

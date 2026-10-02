from extensions import db
from models import Attempt, User
from tests.conftest import login, make_user


def test_users_page_lists_accounts(admin_client, user):
    html = admin_client.get("/admin/users").get_data(as_text=True)
    assert "maria" in html and "boss" in html


def test_confirm_dialogs_are_json_encoded(admin_client, bank_loaded, user):
    for url in ("/admin/users", "/admin/questions/alpha-1"):
        html = admin_client.get(url).get_data(as_text=True)
        assert "onsubmit='return confirm(\"" in html, url
        assert "confirm('" not in html, url


def test_toggle_active_blocks_login(admin_client, user, app):
    admin_client.post(f"/admin/users/{user.id}/toggle-active")
    assert db.session.get(User, user.id).active is False
    other = app.test_client()
    assert login(other).status_code == 403


def test_toggle_admin(admin_client, user):
    admin_client.post(f"/admin/users/{user.id}/toggle-admin")
    assert db.session.get(User, user.id).is_admin is True


def test_reset_password(admin_client, user, app):
    admin_client.post(f"/admin/users/{user.id}/reset-password", data={"password": "brand-new-pass"})
    assert login(app.test_client(), password="brand-new-pass").status_code == 302


def test_password_reset_logs_out_existing_sessions(admin_client, user, app):
    maria = app.test_client()
    login(maria)
    assert maria.get("/stats").status_code == 200
    admin_client.post(f"/admin/users/{user.id}/reset-password", data={"password": "brand-new-pass"})
    response = maria.get("/stats")
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/login")


def test_admin_resetting_own_password_stays_logged_in(admin_client, admin):
    admin_client.post(f"/admin/users/{admin.id}/reset-password", data={"password": "brand-new-pass"})
    assert db.session.get(User, admin.id).check_password("brand-new-pass")
    assert admin_client.get("/admin/users").status_code == 200


def test_reset_password_too_short(admin_client, user):
    admin_client.post(f"/admin/users/{user.id}/reset-password", data={"password": "short"})
    assert db.session.get(User, user.id).check_password("secret-pass")


def test_delete_user_and_their_attempts(admin_client, bank_loaded):
    victim = make_user("victim")
    db.session.add(Attempt(user_id=victim.id, question_id="alpha-1", chosen=1,
                           is_correct=True, mode="quiz"))
    db.session.commit()
    victim_id = victim.id
    admin_client.post(f"/admin/users/{victim_id}/delete")
    assert db.session.get(User, victim_id) is None
    assert db.session.query(Attempt).count() == 0


def test_admin_cannot_lock_themselves_out(admin_client, admin):
    for action in ("toggle-active", "toggle-admin", "delete"):
        admin_client.post(f"/admin/users/{admin.id}/{action}")
    me = db.session.get(User, admin.id)
    assert me is not None and me.active and me.is_admin


def test_unknown_action_is_404(admin_client, user):
    assert admin_client.post(f"/admin/users/{user.id}/explode").status_code == 404


def test_localtime_filter_shows_athens_time():
    from datetime import datetime
    from app import localtime
    assert localtime(datetime(2026, 7, 1, 9, 30)) == "01/07/2026 12:30"    # EEST, UTC+3
    assert localtime(datetime(2026, 1, 1, 9, 30), "%H:%M") == "11:30"      # EET, UTC+2
    assert localtime(None) == "—"

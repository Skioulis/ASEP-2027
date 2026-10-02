import pytest

ADMIN_GET_ROUTES = [
    "/admin/questions",
    "/admin/questions/alpha-1",
    "/admin/questions/new?category=alpha",
    "/admin/export",
    "/admin/import",
    "/admin/users",
]
ADMIN_POST_ROUTES = [
    "/admin/questions/alpha-1",
    "/admin/questions/alpha-1/delete",
    "/admin/import",
    "/admin/users/1/delete",
]


@pytest.mark.parametrize("path", ADMIN_GET_ROUTES)
def test_regular_user_gets_403_on_admin_pages(user_client, bank_loaded, path):
    assert user_client.get(path).status_code == 403


@pytest.mark.parametrize("path", ADMIN_POST_ROUTES)
def test_regular_user_gets_403_on_admin_actions(user_client, bank_loaded, path):
    assert user_client.post(path).status_code == 403

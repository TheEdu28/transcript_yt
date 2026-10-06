"""Pruebas de permisos y autorización granular a nivel de grupo."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Cliente de pruebas con inicio de ciclo de vida (startup/shutdown)."""
    with TestClient(app) as test_client:
        yield test_client


def register_and_login(client: TestClient, email: str, name: str, password: str = "password123") -> tuple[int, str]:
    """Registra un usuario y devuelve su (user_id, token_jwt)."""
    reg_res = client.post("/api/v1/auth/register", json={"email": email, "nombre": name, "password": password})
    assert reg_res.status_code == 201, reg_res.text
    user_id = reg_res.json()["id"]

    login_res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_res.status_code == 200, login_res.text
    token = login_res.json()["access_token"]
    return user_id, token


def auth_header(token: str) -> dict[str, str]:
    """Genera cabecera HTTP Authorization con Bearer token."""
    return {"Authorization": f"Bearer {token}"}


def test_group_creator_becomes_admin_and_permissions(client: TestClient) -> None:
    """El creador del grupo es admin y solo él puede crear temas o administrar."""
    import uuid

    suffix = uuid.uuid4().hex[:6]
    user1_id, token_user1 = register_and_login(client, f"alice_{suffix}@test.com", "Alice")
    user2_id, token_user2 = register_and_login(client, f"bob_{suffix}@test.com", "Bob")

    # 1. Alice crea el Grupo A
    res = client.post(
        "/api/v1/groups",
        json={"name": "Matemáticas Avanzadas"},
        headers=auth_header(token_user1),
    )
    assert res.status_code == 201
    group_a = res.json()
    assert group_a["admin_id"] == user1_id
    group_a_id = group_a["id"]

    # 2. Bob (no es miembro ni admin) intenta crear un tema en Grupo A -> 403 Forbidden
    res_forbidden = client.post(
        f"/api/v1/groups/{group_a_id}/topics",
        json={"title": "Tema no autorizado"},
        headers=auth_header(token_user2),
    )
    assert res_forbidden.status_code == 403
    assert res_forbidden.json()["detail"]["code"] == "FORBIDDEN_NOT_GROUP_ADMIN"

    # 3. Alice añade a Bob como miembro del Grupo A
    res_member = client.post(
        f"/api/v1/groups/{group_a_id}/members",
        json={"user_id": user2_id},
        headers=auth_header(token_user1),
    )
    assert res_member.status_code == 201

    # 4. Bob (ya es miembro, pero NO admin) intenta crear tema en Grupo A -> 403 Forbidden
    res_forbidden_member = client.post(
        f"/api/v1/groups/{group_a_id}/topics",
        json={"title": "Intento de Bob siendo miembro"},
        headers=auth_header(token_user2),
    )
    assert res_forbidden_member.status_code == 403
    assert res_forbidden_member.json()["detail"]["code"] == "FORBIDDEN_NOT_GROUP_ADMIN"

    # 5. Alice (admin) crea el tema exitosamente -> 201 Created
    res_topic = client.post(
        f"/api/v1/groups/{group_a_id}/topics",
        json={"title": "Cálculo Diferencial", "description": "Límites y derivadas"},
        headers=auth_header(token_user1),
    )
    assert res_topic.status_code == 201
    topic_id = res_topic.json()["id"]

    # 6. Ambos miembros pueden ver los temas publicados
    res_topics_bob = client.get(
        f"/api/v1/groups/{group_a_id}/topics",
        headers=auth_header(token_user2),
    )
    assert res_topics_bob.status_code == 200
    assert len(res_topics_bob.json()) == 1
    assert res_topics_bob.json()[0]["id"] == topic_id

    # 7. Bob realiza una actividad / intento en el tema
    res_attempt = client.post(
        f"/api/v1/groups/{group_a_id}/topics/{topic_id}/attempts",
        json={"score": 85, "details": "Primer intento completado"},
        headers=auth_header(token_user2),
    )
    assert res_attempt.status_code == 201

    # 8. Bob intenta ver la lista de todos los intentos del grupo -> 403 Forbidden
    res_attempts_all_bob = client.get(
        f"/api/v1/groups/{group_a_id}/attempts",
        headers=auth_header(token_user2),
    )
    assert res_attempts_all_bob.status_code == 403

    # 9. Bob consulta SOLO sus propios intentos -> 200 OK
    res_my_attempts = client.get(
        f"/api/v1/groups/{group_a_id}/my-attempts",
        headers=auth_header(token_user2),
    )
    assert res_my_attempts.status_code == 200
    assert len(res_my_attempts.json()) == 1
    assert res_my_attempts.json()[0]["user_id"] == user2_id

    # 10. Alice (admin) consulta todos los intentos del grupo -> 200 OK
    res_attempts_all_alice = client.get(
        f"/api/v1/groups/{group_a_id}/attempts",
        headers=auth_header(token_user1),
    )
    assert res_attempts_all_alice.status_code == 200
    assert len(res_attempts_all_alice.json()) == 1
    assert res_attempts_all_alice.json()[0]["user_id"] == user2_id


def test_cross_group_roles_independence(client: TestClient) -> None:
    """Una misma persona puede ser admin en un grupo y simple miembro en otro."""
    import uuid

    suffix = uuid.uuid4().hex[:6]
    user1_id, token_user1 = register_and_login(client, f"carol_{suffix}@test.com", "Carol")
    user2_id, token_user2 = register_and_login(client, f"dave_{suffix}@test.com", "Dave")

    # Carol crea Grupo A -> Carol es admin
    res_a = client.post("/api/v1/groups", json={"name": "Grupo Carol"}, headers=auth_header(token_user1))
    group_a_id = res_a.json()["id"]

    # Dave crea Grupo B -> Dave es admin
    res_b = client.post("/api/v1/groups", json={"name": "Grupo Dave"}, headers=auth_header(token_user2))
    group_b_id = res_b.json()["id"]

    # Dave añade a Carol como miembro en Grupo B
    client.post(
        f"/api/v1/groups/{group_b_id}/members",
        json={"user_id": user1_id},
        headers=auth_header(token_user2),
    )

    # Carol puede crear temas en Grupo A (su grupo)
    res_carol_a = client.post(
        f"/api/v1/groups/{group_a_id}/topics",
        json={"title": "Tema de Carol en Grupo A"},
        headers=auth_header(token_user1),
    )
    assert res_carol_a.status_code == 201

    # Carol NO puede crear temas en Grupo B (solo es miembro)
    res_carol_b = client.post(
        f"/api/v1/groups/{group_b_id}/topics",
        json={"title": "Intento de Carol en Grupo B"},
        headers=auth_header(token_user1),
    )
    assert res_carol_b.status_code == 403

    # Dave puede crear temas en Grupo B (su grupo)
    res_dave_b = client.post(
        f"/api/v1/groups/{group_b_id}/topics",
        json={"title": "Tema de Dave en Grupo B"},
        headers=auth_header(token_user2),
    )
    assert res_dave_b.status_code == 201

    # Dave NO puede crear temas en Grupo A (ni siquiera es miembro)
    res_dave_a = client.post(
        f"/api/v1/groups/{group_a_id}/topics",
        json={"title": "Intento de Dave en Grupo A"},
        headers=auth_header(token_user2),
    )
    assert res_dave_a.status_code == 403

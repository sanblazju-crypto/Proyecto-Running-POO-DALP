import pytest
from datetime import datetime, timedelta, timezone


# ─── Events ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_event(client, auth_headers):
    response = await client.post("/api/v1/events", headers=auth_headers, json={
        "name": "Madrid Rock'n'Roll Marathon",
        "discipline": "running",
        "difficulty": "intermediate",
        "date": (datetime.now(timezone.utc) + timedelta(days=60)).isoformat(),
        "city": "Madrid",
        "country": "Spain",
        "distance_km": 42.195,
        "latitude": 40.4168,
        "longitude": -3.7038,
        "organizer_name": "Rock'n'Roll Series",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Madrid Rock'n'Roll Marathon"
    assert data["discipline"] == "running"
    assert "slug" in data
    return data


@pytest.mark.asyncio
async def test_list_events(client, auth_headers):
    response = await client.get("/api/v1/events", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_list_events_filter_discipline(client, auth_headers):
    response = await client.get(
        "/api/v1/events?discipline=running",
        headers=auth_headers,
    )
    assert response.status_code == 200
    events = response.json()
    assert all(e["discipline"] == "running" for e in events)


@pytest.mark.asyncio
async def test_get_event_by_slug(client, auth_headers):
    # Create first
    create_resp = await client.post("/api/v1/events", headers=auth_headers, json={
        "name": "Slug Test Race",
        "discipline": "cycling",
        "date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "distance_km": 100,
    })
    slug = create_resp.json()["slug"]

    response = await client.get(f"/api/v1/events/{slug}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["slug"] == slug


@pytest.mark.asyncio
async def test_register_and_unregister_event(client, auth_headers):
    # Create event
    create_resp = await client.post("/api/v1/events", headers=auth_headers, json={
        "name": "Register Test Race",
        "discipline": "trail",
        "date": (datetime.now(timezone.utc) + timedelta(days=90)).isoformat(),
        "distance_km": 30,
    })
    event_id = create_resp.json()["id"]

    # Register
    reg = await client.post(f"/api/v1/events/{event_id}/register", headers=auth_headers)
    assert reg.status_code == 204

    # Duplicate registration
    dup = await client.post(f"/api/v1/events/{event_id}/register", headers=auth_headers)
    assert dup.status_code == 400

    # Unregister
    unreg = await client.delete(f"/api/v1/events/{event_id}/register", headers=auth_headers)
    assert unreg.status_code == 204


# ─── Activities ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_activity(client, auth_headers):
    response = await client.post("/api/v1/activities", headers=auth_headers, json={
        "title": "Morning run in Retiro",
        "discipline": "running",
        "activity_type": "training",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": 3600,
        "distance_meters": 10000,
        "avg_heart_rate": 145,
        "perceived_effort": 7,
    })
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Morning run in Retiro"
    assert data["avg_pace_sec_per_km"] == pytest.approx(360.0, rel=0.01)
    assert data["avg_speed_kmh"] == pytest.approx(10.0, rel=0.01)
    return data


@pytest.mark.asyncio
async def test_list_activities(client, auth_headers):
    response = await client.get("/api/v1/activities", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_get_activity(client, auth_headers):
    create_resp = await client.post("/api/v1/activities", headers=auth_headers, json={
        "title": "Interval session",
        "discipline": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": 1800,
        "distance_meters": 6000,
    })
    activity_id = create_resp.json()["id"]

    response = await client.get(f"/api/v1/activities/{activity_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == activity_id


@pytest.mark.asyncio
async def test_update_activity(client, auth_headers):
    create_resp = await client.post("/api/v1/activities", headers=auth_headers, json={
        "title": "Easy ride",
        "discipline": "cycling",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": 7200,
        "distance_meters": 50000,
    })
    activity_id = create_resp.json()["id"]

    update_resp = await client.patch(
        f"/api/v1/activities/{activity_id}",
        headers=auth_headers,
        json={"notes": "Great weather today", "perceived_effort": 5},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["notes"] == "Great weather today"


@pytest.mark.asyncio
async def test_delete_activity(client, auth_headers):
    create_resp = await client.post("/api/v1/activities", headers=auth_headers, json={
        "title": "To delete",
        "discipline": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": 900,
        "distance_meters": 2000,
    })
    activity_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/activities/{activity_id}", headers=auth_headers)
    assert delete_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/activities/{activity_id}", headers=auth_headers)
    assert get_resp.status_code == 404

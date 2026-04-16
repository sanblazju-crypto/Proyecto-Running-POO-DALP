import pytest
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_create_text_post(client, auth_headers):
    response = await client.post("/api/v1/feed", headers=auth_headers, json={
        "content": "Just finished a great training week!",
        "post_type": "text",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["content"] == "Just finished a great training week!"
    assert data["likes_count"] == 0
    return data


@pytest.mark.asyncio
async def test_get_feed(client, auth_headers):
    response = await client.get("/api/v1/feed", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_like_and_unlike_post(client, auth_headers):
    # Create post
    create_resp = await client.post("/api/v1/feed", headers=auth_headers, json={
        "content": "Test post for likes",
        "post_type": "text",
    })
    post_id = create_resp.json()["id"]

    # Like
    like_resp = await client.post(f"/api/v1/feed/{post_id}/like", headers=auth_headers)
    assert like_resp.status_code == 204

    # Unlike
    unlike_resp = await client.delete(f"/api/v1/feed/{post_id}/like", headers=auth_headers)
    assert unlike_resp.status_code == 204


@pytest.mark.asyncio
async def test_add_and_list_comments(client, auth_headers):
    # Create post
    post_resp = await client.post("/api/v1/feed", headers=auth_headers, json={
        "content": "Post with comments",
        "post_type": "text",
    })
    post_id = post_resp.json()["id"]

    # Add comment
    comment_resp = await client.post(
        f"/api/v1/feed/{post_id}/comments",
        headers=auth_headers,
        json={"content": "Great effort!"},
    )
    assert comment_resp.status_code == 201
    comment_id = comment_resp.json()["id"]

    # List comments
    list_resp = await client.get(f"/api/v1/feed/{post_id}/comments")
    assert list_resp.status_code == 200
    comments = list_resp.json()
    assert any(c["id"] == comment_id for c in comments)


@pytest.mark.asyncio
async def test_delete_post(client, auth_headers):
    post_resp = await client.post("/api/v1/feed", headers=auth_headers, json={
        "content": "Will be deleted",
        "post_type": "text",
    })
    post_id = post_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/feed/{post_id}", headers=auth_headers)
    assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_follow_unfollow(client, auth_headers, premium_user):
    user_id = str(premium_user.id)

    follow_resp = await client.post(f"/api/v1/users/{user_id}/follow", headers=auth_headers)
    assert follow_resp.status_code == 204

    # Duplicate follow
    dup_resp = await client.post(f"/api/v1/users/{user_id}/follow", headers=auth_headers)
    assert dup_resp.status_code == 400

    unfollow_resp = await client.delete(f"/api/v1/users/{user_id}/follow", headers=auth_headers)
    assert unfollow_resp.status_code == 204


@pytest.mark.asyncio
async def test_get_user_stats(client, auth_headers, test_user):
    # Create some activities first
    for i in range(3):
        await client.post("/api/v1/activities", headers=auth_headers, json={
            "title": f"Run {i}",
            "discipline": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": 3600 + i * 300,
            "distance_meters": 10000 + i * 1000,
        })

    response = await client.get("/api/v1/stats/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_activities"] >= 3
    assert data["total_distance_km"] > 0


@pytest.mark.asyncio
async def test_get_personal_bests(client, auth_headers):
    # Create a 10K+ activity to trigger PB recording
    await client.post("/api/v1/activities", headers=auth_headers, json={
        "title": "10K race",
        "discipline": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": 2700,  # 45 minutes → covers 5K and 10K at that pace
        "distance_meters": 10500,
    })

    response = await client.get("/api/v1/stats/me/personal-bests", headers=auth_headers)
    assert response.status_code == 200
    pbs = response.json()
    assert isinstance(pbs, list)


@pytest.mark.asyncio
async def test_search_users(client, auth_headers, test_user):
    response = await client.get(f"/api/v1/users/search?q={test_user.username[:4]}", headers=auth_headers)
    assert response.status_code == 200
    users = response.json()
    assert any(u["username"] == test_user.username for u in users)

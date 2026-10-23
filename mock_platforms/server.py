"""Mock Platform Server simulating external publishing targets."""

import asyncio
from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from typing import Dict, Any
import uuid

mock_app = FastAPI(title="IncuBrix Mock Platform Server", version="1.0.0")

# In-memory stores for simulated platforms
_discourse_posts: Dict[str, Any] = {}
_lemmy_posts: Dict[str, Any] = {}
_devto_articles: Dict[str, Any] = {}
_ghost_posts: Dict[str, Any] = {}
_webhook_records: Dict[str, Any] = {}


@mock_app.get("/health")
async def health_check():
    """Health check endpoint for mock platform service."""
    return {"status": "healthy", "service": "incubrix-mock"}


@mock_app.post("/mock/reset")
async def mock_reset():
    """Reset all in-memory mock databases."""
    _discourse_posts.clear()
    _lemmy_posts.clear()
    _devto_articles.clear()
    _ghost_posts.clear()
    _webhook_records.clear()
    return {"status": "reset"}


def check_simulation_triggers(request: Request):
    """Check for simulation trigger headers or query params."""
    sim = request.headers.get("x-simulate") or request.query_params.get("simulate")
    if sim == "429":
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded. Please slow down."},
            headers={"Retry-After": "2"}
        )
    elif sim == "401":
        return JSONResponse(status_code=401, content={"error": "Unauthorized or credentials expired."})
    elif sim == "422":
        return JSONResponse(status_code=422, content={"error": "Content violates platform community policy."})
    elif sim == "503":
        return JSONResponse(status_code=503, content={"error": "Platform temporarily unavailable."})
    elif sim == "timeout":
        return JSONResponse(status_code=504, content={"error": "Gateway Timeout"})
    return None


# ---------------- DEV.TO MOCK ----------------
@mock_app.post("/devto/api/articles")
async def devto_publish(request: Request):
    trigger = check_simulation_triggers(request)
    if trigger:
        return trigger

    api_key = request.headers.get("api-key")
    if not api_key or api_key == "invalid_key":
        return JSONResponse(status_code=401, content={"error": "Unauthorized: invalid api-key"})

    body = await request.json()
    article = body.get("article", {})
    if not article.get("title") or len(article.get("title", "")) < 5:
        return JSONResponse(status_code=422, content={"error": "Title too short"})

    art_id = str(uuid.uuid4().int)[:6]
    record = {
        "id": int(art_id),
        "title": article.get("title"),
        "url": f"https://dev.to/mock_user/{art_id}",
        "published": True,
        "page_views_count": 42,
        "public_reactions_count": 8,
        "comments_count": 3,
        "reading_list_count": 2
    }
    _devto_articles[art_id] = record

    sim = request.headers.get("x-simulate") or request.query_params.get("simulate")
    if sim == "timeout-after-create":
        return JSONResponse(status_code=504, content={"error": "Gateway Timeout after creation"})

    return JSONResponse(status_code=201, content=record)


@mock_app.get("/devto/api/articles")
async def devto_list_or_search(request: Request):
    title = request.query_params.get("title")
    articles = list(_devto_articles.values())
    if title:
        articles = [a for a in articles if a.get("title") == title]
    return JSONResponse(status_code=200, content=articles)


@mock_app.get("/devto/api/articles/{article_id}")
async def devto_get(article_id: str, request: Request):
    trigger = check_simulation_triggers(request)
    if trigger:
        return trigger

    if article_id not in _devto_articles:
        return JSONResponse(status_code=404, content={"error": "Article not found"})
    return JSONResponse(status_code=200, content=_devto_articles[article_id])


@mock_app.delete("/devto/api/articles/{article_id}")
async def devto_delete(article_id: str, request: Request):
    trigger = check_simulation_triggers(request)
    if trigger:
        return trigger

    if article_id in _devto_articles:
        del _devto_articles[article_id]
    return Response(status_code=204)


# ---------------- DISCOURSE MOCK ----------------
@mock_app.post("/discourse/posts.json")
async def discourse_publish(request: Request):
    trigger = check_simulation_triggers(request)
    if trigger:
        return trigger

    api_key = request.headers.get("Api-Key")
    api_user = request.headers.get("Api-Username")
    if not api_key or not api_user or api_key == "invalid_key":
        return JSONResponse(status_code=401, content={"errors": ["Invalid API credentials"]})

    body = await request.json()
    if not body.get("raw") or len(body.get("raw")) < 20:
        return JSONResponse(status_code=422, content={"errors": ["Body is too short (minimum 20 characters)"]})

    post_id = str(uuid.uuid4().int)[:5]
    topic_id = str(uuid.uuid4().int)[:4]
    record = {
        "id": int(post_id),
        "topic_id": int(topic_id),
        "topic_slug": "incubrix-test-topic",
        "title": body.get("title", ""),
        "raw": body.get("raw", ""),
        "post_number": 1,
        "reads": 25,
        "score": 10,
        "like_count": 5,
        "reply_count": 2
    }
    _discourse_posts[post_id] = record

    sim = request.headers.get("x-simulate") or request.query_params.get("simulate")
    if sim == "timeout-after-create":
        return JSONResponse(status_code=504, content={"error": "Gateway Timeout after creation"})

    return JSONResponse(status_code=200, content=record)


@mock_app.get("/discourse/search.json")
async def discourse_search(request: Request):
    q = request.query_params.get("q", "")
    posts = [
        p for p in _discourse_posts.values()
        if q in str(p.get("raw", "")) or q in str(p.get("title", "")) or q in str(p.get("topic_slug", ""))
    ]
    return JSONResponse(status_code=200, content={"posts": posts})


@mock_app.get("/discourse/posts/{post_id}.json")
async def discourse_get(post_id: str, request: Request):
    trigger = check_simulation_triggers(request)
    if trigger:
        return trigger

    if post_id not in _discourse_posts:
        return JSONResponse(status_code=404, content={"errors": ["Post not found"]})
    return JSONResponse(status_code=200, content=_discourse_posts[post_id])


@mock_app.delete("/discourse/posts/{post_id}.json")
async def discourse_delete(post_id: str, request: Request):
    trigger = check_simulation_triggers(request)
    if trigger:
        return trigger

    if post_id in _discourse_posts:
        del _discourse_posts[post_id]
    return JSONResponse(status_code=200, content={"deleted": True})


# ---------------- LEMMY MOCK ----------------
@mock_app.post("/lemmy/api/v3/post")
async def lemmy_publish(request: Request):
    trigger = check_simulation_triggers(request)
    if trigger:
        return trigger

    auth = request.headers.get("Authorization") or (await request.json()).get("auth")
    if not auth or "invalid" in str(auth):
        return JSONResponse(status_code=401, content={"error": "not_logged_in"})

    body = await request.json()
    post_id = int(str(uuid.uuid4().int)[:5])
    record = {
        "post_view": {
            "post": {
                "id": post_id,
                "name": body.get("name"),
                "body": body.get("body"),
                "deleted": False
            },
            "community": {
                "id": body.get("community_id", 1),
                "name": "tech"
            },
            "counts": {
                "score": 14,
                "upvotes": 15,
                "comments": 4
            }
        }
    }
    _lemmy_posts[str(post_id)] = record

    sim = request.headers.get("x-simulate") or request.query_params.get("simulate")
    if sim == "timeout-after-create":
        return JSONResponse(status_code=504, content={"error": "Gateway Timeout after creation"})

    return JSONResponse(status_code=200, content=record)


@mock_app.get("/lemmy/api/v3/search")
async def lemmy_search(request: Request):
    q = request.query_params.get("q", "")
    matching = [
        p["post_view"] for p in _lemmy_posts.values()
        if "post_view" in p and q in p["post_view"].get("post", {}).get("name", "")
    ]
    return JSONResponse(status_code=200, content={"posts": matching})


@mock_app.get("/lemmy/api/v3/post")
async def lemmy_get(request: Request):
    trigger = check_simulation_triggers(request)
    if trigger:
        return trigger

    post_id = request.query_params.get("id")
    if not post_id or post_id not in _lemmy_posts:
        return JSONResponse(status_code=404, content={"error": "post_not_found"})
    return JSONResponse(status_code=200, content=_lemmy_posts[post_id])


@mock_app.post("/lemmy/api/v3/post/delete")
async def lemmy_delete(request: Request):
    trigger = check_simulation_triggers(request)
    if trigger:
        return trigger

    body = await request.json()
    post_id = str(body.get("post_id"))
    if post_id in _lemmy_posts:
        del _lemmy_posts[post_id]
    return JSONResponse(status_code=200, content={"success": True})


# ---------------- GHOST MOCK ----------------
@mock_app.post("/ghost/api/admin/posts/")
async def ghost_publish(request: Request):
    trigger = check_simulation_triggers(request)
    if trigger:
        return trigger

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Ghost "):
        return JSONResponse(status_code=401, content={"errors": [{"message": "Invalid Ghost Token"}]})

    body = await request.json()
    post_in = body.get("posts", [{}])[0]
    post_id = f"ghost_{str(uuid.uuid4().hex)[:16]}"
    record = {
        "id": post_id,
        "title": post_in.get("title"),
        "status": "published",
        "url": f"https://mock-ghost.incubrix.test/{post_id}/",
        "custom_excerpt": post_in.get("custom_excerpt")
    }
    _ghost_posts[post_id] = record

    sim = request.headers.get("x-simulate") or request.query_params.get("simulate")
    if sim == "timeout-after-create":
        return JSONResponse(status_code=504, content={"error": "Gateway Timeout after creation"})

    return JSONResponse(status_code=201, content={"posts": [record]})


@mock_app.get("/ghost/api/admin/posts/")
async def ghost_list_posts(request: Request):
    filter_val = request.query_params.get("filter", "")
    posts = list(_ghost_posts.values())
    if "title:" in filter_val:
        title_target = filter_val.split("title:", 1)[1].strip("'\"")
        posts = [p for p in posts if p.get("title") == title_target]
    return JSONResponse(status_code=200, content={"posts": posts})


@mock_app.get("/ghost/api/admin/posts/{post_id}/")
async def ghost_get(post_id: str, request: Request):
    trigger = check_simulation_triggers(request)
    if trigger:
        return trigger

    if post_id not in _ghost_posts:
        return JSONResponse(status_code=404, content={"errors": [{"message": "Post not found"}]})
    return JSONResponse(status_code=200, content={"posts": [_ghost_posts[post_id]]})


@mock_app.delete("/ghost/api/admin/posts/{post_id}/")
async def ghost_delete(post_id: str, request: Request):
    trigger = check_simulation_triggers(request)
    if trigger:
        return trigger

    if post_id in _ghost_posts:
        del _ghost_posts[post_id]
    return Response(status_code=204)


# ---------------- WEBHOOK MOCK ----------------
@mock_app.post("/webhook")
async def webhook_receiver(request: Request):
    trigger = check_simulation_triggers(request)
    if trigger:
        return trigger

    sig = request.headers.get("X-IncuBrix-Signature")
    if not sig:
        return JSONResponse(status_code=401, content={"error": "Missing signature"})

    body = await request.json()
    idempotency_key = request.headers.get("Idempotency-Key") or body.get("idempotency_key")
    wh_id = f"wh_{str(uuid.uuid4().hex)[:8]}"
    _webhook_records[wh_id] = {
        "id": wh_id,
        "idempotency_key": idempotency_key,
        "payload": body,
        "status": "delivered"
    }

    sim = request.headers.get("x-simulate") or request.query_params.get("simulate")
    if sim == "timeout-after-create":
        return JSONResponse(status_code=504, content={"error": "Gateway Timeout after creation"})

    return JSONResponse(status_code=200, content={
        "status": "delivered",
        "id": wh_id,
        "url": f"https://partner.incubrix.test/posts/{wh_id}"
    })


@mock_app.get("/webhook/status")
async def webhook_status_by_key(request: Request):
    key = request.query_params.get("idempotency_key") or request.headers.get("Idempotency-Key")
    for r in _webhook_records.values():
        if r.get("idempotency_key") == key:
            return JSONResponse(status_code=200, content={
                "status": "published",
                "id": r["id"],
                "live_url": f"https://partner.incubrix.test/posts/{r['id']}"
            })
    return JSONResponse(status_code=404, content={"error": "Not found"})


@mock_app.get("/webhook/{wh_id}")
async def webhook_get(wh_id: str, request: Request):
    if wh_id not in _webhook_records:
        return JSONResponse(status_code=404, content={"error": "Webhook post not found"})
    return JSONResponse(status_code=200, content={"status": "published", "live_url": f"https://partner.incubrix.test/posts/{wh_id}"})


@mock_app.delete("/webhook/{wh_id}")
async def webhook_delete(wh_id: str, request: Request):
    if wh_id in _webhook_records:
        del _webhook_records[wh_id]
    return JSONResponse(status_code=200, content={"deleted": True})

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
_s3_buckets: Dict[str, Dict[str, bytes]] = {"incubrix-evidence": {}}


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
    _s3_buckets.clear()
    _s3_buckets["incubrix-evidence"] = {}
    return {"status": "reset"}



@mock_app.get("/robots.txt")
async def mock_robots():
    return Response(content="User-agent: *\nAllow: /\n", media_type="text/plain")


@mock_app.get("/mock_csv")
async def mock_csv():
    csv_content = (
        "name,url,platform_key,connector_key,surface,category,audience_tags,est_audience,rules_url,frequency_cap\n"
        "URL Imported Community,http://localhost:8001/discourse/c/url_imp,discourse,discourse,main,technology,\"tech,ai\",1000,http://localhost:8001/discourse/rules,5\n"
    )
    return Response(content=csv_content, media_type="text/csv")



@mock_app.get("/discourse/c/{path:path}")
@mock_app.get("/mock/community/{path:path}")
async def mock_community_endpoint(path: str):
    return JSONResponse(status_code=200, content={"status": "active", "path": path, "platform": "discourse"})


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


# ---------------- HASHNODE MOCK ----------------
_hashnode_posts: Dict[str, Any] = {}

@mock_app.post("/hashnode/graphql")
async def hashnode_graphql(request: Request):
    trigger = check_simulation_triggers(request)
    if trigger:
        return trigger

    auth = request.headers.get("Authorization")
    if not auth or "invalid" in auth:
        return JSONResponse(status_code=401, content={"errors": [{"message": "Unauthorized: invalid personal access token"}]})

    body = await request.json()
    query = body.get("query", "")
    variables = body.get("variables", {})

    if "publishPost" in query:
        post_input = variables.get("input", {})
        post_id = f"hn_{uuid.uuid4().hex[:8]}"
        title = post_input.get("title", "")
        post_obj = {
            "id": post_id,
            "title": title,
            "url": f"https://hashnode.com/post/{post_id}",
            "views": 25,
            "reactions": 5,
            "comments": 2
        }
        _hashnode_posts[post_id] = post_obj
        return JSONResponse(status_code=200, content={"data": {"publishPost": {"post": post_obj}}})

    elif "deletePost" in query:
        del_input = variables.get("input", {})
        p_id = del_input.get("id")
        if p_id in _hashnode_posts:
            del _hashnode_posts[p_id]
        return JSONResponse(status_code=200, content={"data": {"deletePost": {"post": {"id": p_id}}}})

    elif "post(" in query or "query Post" in query:
        p_id = variables.get("id")
        post_obj = _hashnode_posts.get(p_id)
        if not post_obj:
            return JSONResponse(status_code=200, content={"data": {"post": None}})
        return JSONResponse(status_code=200, content={"data": {"post": post_obj}})

    return JSONResponse(status_code=200, content={"data": {}})


# ---------------- SLACK MOCK ----------------
_slack_messages: Dict[str, Any] = {}

@mock_app.post("/slack/api/chat.postMessage")
async def slack_post_message(request: Request):
    trigger = check_simulation_triggers(request)
    if trigger:
        return trigger

    auth = request.headers.get("Authorization")
    if not auth or "invalid" in auth:
        return JSONResponse(status_code=401, content={"ok": False, "error": "invalid_auth"})

    body = await request.json()
    channel = body.get("channel", "C123")
    text = body.get("text", "")
    msg_id = f"{int(uuid.uuid4().int % 1000000000)}.000100"

    record = {
        "channel": channel,
        "ts": msg_id,
        "text": text,
        "reactions": [{"name": "thumbsup", "count": 4}],
        "reply_count": 1
    }
    _slack_messages[msg_id] = record

    return JSONResponse(status_code=200, content={
        "ok": True,
        "channel": channel,
        "ts": msg_id,
        "message": record
    })


@mock_app.post("/slack/api/chat.delete")
async def slack_delete_message(request: Request):
    body = await request.json()
    ts = body.get("ts")
    if ts in _slack_messages:
        del _slack_messages[ts]
        return JSONResponse(status_code=200, content={"ok": True, "ts": ts})
    return JSONResponse(status_code=404, content={"ok": False, "error": "message_not_found"})


@mock_app.get("/slack/api/conversations.history")
async def slack_history(request: Request):
    latest = request.query_params.get("latest")
    if latest and latest in _slack_messages:
        return JSONResponse(status_code=200, content={"ok": True, "messages": [_slack_messages[latest]]})
    return JSONResponse(status_code=200, content={"ok": True, "messages": list(_slack_messages.values())})


# ---------------- MAILCHIMP MOCK ----------------
_mailchimp_campaigns: Dict[str, Any] = {}

@mock_app.post("/mailchimp/3.0/campaigns")
async def mailchimp_create_campaign_draft(request: Request):
    trigger = check_simulation_triggers(request)
    if trigger:
        return trigger

    auth = request.headers.get("Authorization")
    if not auth or "invalid" in auth:
        return JSONResponse(status_code=401, content={"title": "Unauthorized", "detail": "Invalid API key"})

    body = await request.json()
    camp_id = f"mc_{uuid.uuid4().hex[:8]}"

    # Enforce DRAFT status only: Mailchimp campaign creation creates a draft ("save")
    record = {
        "id": camp_id,
        "type": body.get("type", "regular"),
        "status": "save",  # "save" represents draft in Mailchimp
        "settings": body.get("settings", {}),
        "archive_url": f"https://mailchimp.com/campaigns/{camp_id}",
        "emails_sent": 0  # CRITICAL: Drafts only, 0 emails sent to real subscribers
    }
    _mailchimp_campaigns[camp_id] = record

    return JSONResponse(status_code=201, content=record)


@mock_app.put("/mailchimp/3.0/campaigns/{campaign_id}/content")
async def mailchimp_set_content(campaign_id: str, request: Request):
    if campaign_id not in _mailchimp_campaigns:
        return JSONResponse(status_code=404, content={"title": "Not Found"})
    body = await request.json()
    _mailchimp_campaigns[campaign_id]["html"] = body.get("html", "")
    return JSONResponse(status_code=200, content={"status": "save"})


@mock_app.get("/mailchimp/3.0/campaigns/{campaign_id}")
async def mailchimp_get_campaign(campaign_id: str, request: Request):
    if campaign_id not in _mailchimp_campaigns:
        return JSONResponse(status_code=404, content={"title": "Not Found", "detail": "Campaign draft not found"})
    return JSONResponse(status_code=200, content=_mailchimp_campaigns[campaign_id])


@mock_app.delete("/mailchimp/3.0/campaigns/{campaign_id}")
async def mailchimp_delete_campaign(campaign_id: str, request: Request):
    if campaign_id in _mailchimp_campaigns:
        del _mailchimp_campaigns[campaign_id]
        return Response(status_code=204)
    return JSONResponse(status_code=404, content={"title": "Not Found"})


@mock_app.get("/mailchimp/3.0/reports/{campaign_id}")
async def mailchimp_get_report(campaign_id: str, request: Request):
    return JSONResponse(status_code=200, content={
        "opens": {"unique_opens": 15},
        "clicks": {"unique_subscriber_clicks": 5},
        "shares": {"facebook_shares": 1}
    })


# ---------------- S3 / MINIO MOCK ENDPOINTS ----------------
@mock_app.head("/{bucket}")
async def s3_head_bucket(bucket: str):
    if bucket in _s3_buckets:
        return Response(status_code=200)
    return Response(status_code=404)


@mock_app.put("/{bucket}")
async def s3_create_bucket(bucket: str):
    _s3_buckets.setdefault(bucket, {})
    return Response(status_code=200)


@mock_app.put("/{bucket}/{key:path}")
async def s3_put_object(bucket: str, key: str, request: Request):
    data = await request.body()
    _s3_buckets.setdefault(bucket, {})[key] = data
    etag = f'"{uuid.uuid4().hex}"'
    return Response(status_code=200, headers={"ETag": etag})


@mock_app.get("/{bucket}/{key:path}")
async def s3_get_object(bucket: str, key: str):
    b = _s3_buckets.get(bucket)
    if b is None or key not in b:
        return Response(status_code=404, content="NoSuchKey")
    content = b[key]
    media_type = "application/json" if key.endswith(".json") else "text/plain"
    return Response(content=content, media_type=media_type)


@mock_app.head("/{bucket}/{key:path}")
async def s3_head_object(bucket: str, key: str):
    b = _s3_buckets.get(bucket)
    if b is None or key not in b:
        return Response(status_code=404)
    content = b[key]
    return Response(status_code=200, headers={"Content-Length": str(len(content))})


@mock_app.delete("/{bucket}/{key:path}")
async def s3_delete_object(bucket: str, key: str):
    b = _s3_buckets.get(bucket)
    if b and key in b:
        del b[key]
    return Response(status_code=204)



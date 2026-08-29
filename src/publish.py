from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "state.json"


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def graph_request(method: str, url: str, fields: dict[str, str] | None = None) -> dict:
    data = urllib.parse.urlencode(fields or {}).encode("utf-8") if method == "POST" else None
    if method == "GET" and fields:
        url += "?" + urllib.parse.urlencode(fields)
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1200]
        raise RuntimeError(f"Instagram API error {exc.code}: {body}") from exc


def wait_until_ready(host: str, version: str, container_id: str, token: str) -> None:
    for _ in range(18):
        status = graph_request(
            "GET",
            f"{host}/{version}/{container_id}",
            {"fields": "status_code", "access_token": token},
        ).get("status_code")
        if status in {"FINISHED", "PUBLISHED"}:
            return
        if status in {"ERROR", "EXPIRED"}:
            raise RuntimeError(f"Instagram container failed with status {status}")
        time.sleep(10)
    raise RuntimeError("Instagram container did not become ready in time")


def notify(topic: str | None, message: str) -> None:
    if not topic:
        return
    req = urllib.request.Request(
        f"https://ntfy.sh/{urllib.parse.quote(topic)}",
        data=message.encode("utf-8"),
        headers={"Title": "AI 써봄 게시 완료", "Tags": "white_check_mark,robot"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30):
        pass


def main() -> None:
    post_path = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "generated/current/post.json")
    post = json.loads(post_path.read_text(encoding="utf-8"))
    token = required("INSTAGRAM_ACCESS_TOKEN")
    ig_user_id = required("INSTAGRAM_USER_ID")
    repo = required("GITHUB_REPOSITORY")
    commit_sha = required("MEDIA_COMMIT_SHA")
    version = os.environ.get("IG_GRAPH_VERSION", "v26.0")
    host = "https://graph.instagram.com"
    media_base = f"https://raw.githubusercontent.com/{repo}/{commit_sha}/generated/current"

    children: list[str] = []
    for index in range(1, 8):
        item = graph_request(
            "POST",
            f"{host}/{version}/{ig_user_id}/media",
            {
                "image_url": f"{media_base}/{index:02d}.jpg",
                "is_carousel_item": "true",
                "access_token": token,
            },
        )
        container_id = item["id"]
        wait_until_ready(host, version, container_id, token)
        children.append(container_id)

    carousel = graph_request(
        "POST",
        f"{host}/{version}/{ig_user_id}/media",
        {
            "media_type": "CAROUSEL",
            "children": ",".join(children),
            "caption": post["caption_full"],
            "is_ai_generated": "true",
            "access_token": token,
        },
    )
    carousel_id = carousel["id"]
    wait_until_ready(host, version, carousel_id, token)
    published = graph_request(
        "POST",
        f"{host}/{version}/{ig_user_id}/media_publish",
        {"creation_id": carousel_id, "access_token": token},
    )

    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    state.setdefault("published", []).append(
        {
            "topic": post["topic"],
            "published_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "instagram_media_id": published["id"],
            "commit_sha": commit_sha,
        }
    )
    state["published"] = state["published"][-100:]
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    notify(os.environ.get("NTFY_TOPIC"), f"@ai.sseobom에 새 카드뉴스가 게시됐습니다.\n주제: {post['topic']}")
    print(f"Published Instagram media ID: {published['id']}")


if __name__ == "__main__":
    main()


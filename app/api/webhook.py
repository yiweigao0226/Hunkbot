"""
GitHub webhook endpoint.

Security: GitHub signs every webhook payload with HMAC-SHA256.
We verify the signature before processing anything.

Events handled:
- pull_request: opened, synchronize (new commits pushed), reopened
"""
import hashlib
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request, BackgroundTasks

from app.core.config import settings
from app.services.diff_processor import process_pr_files
from app.services.llm_reviewer import review_pr
from app.services.github_service import get_github_client, post_review

logger = logging.getLogger(__name__)
router = APIRouter()

REVIEW_ACTIONS = {"opened", "synchronize", "reopened"}

def _verify_signature(payload: bytes, signature_header: str) -> bool:
    """
    Verify GitHub's HMAC-SHA256 webhook signature.
    GitHub sends: X-Hub-Signature-256: sha256=<hex_digest>
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.github_webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    received = signature_header[len("sha256="):]
    return hmac.compare_digest(expected, received)


async def _handle_pr_event(payload: dict) -> None:
    """
    Core review logic — runs in background so webhook returns 200 immediately.
    GitHub retries if we don't respond within ~10 seconds.
    """
    action = payload.get("action")
    pr_data = payload.get("pull_request", {})
    installation_id = payload.get("installation", {}).get("id")

    if not installation_id:
        logger.warning("No installation_id in payload, skipping")
        return

    repo_full_name = payload["repository"]["full_name"]
    pr_number = pr_data["number"]

    logger.info(f"Reviewing PR #{pr_number} in {repo_full_name} (action={action})")

    try:
        gh = get_github_client(installation_id)
        repo = gh.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)

        # TODO: load custom_rules from DB per repo (hardcoded empty for now)
        ctx = process_pr_files(pr, custom_rules=[])

        if not ctx.files:
            logger.info(f"PR #{pr_number}: no reviewable files after filtering, skipping")
            return

        result = await review_pr(ctx)
        logger.info(
            f"PR #{pr_number}: review complete — "
            f"{len(result.comments)} comments, approved={result.approved}"
        )

        post_review(pr, result)

    except Exception as e:
        logger.exception(f"Failed to review PR #{pr_number} in {repo_full_name}: {e}")
        # Don't re-raise — we don't want GitHub to retry (it would double-review)


@router.post("/webhook")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
):
    payload_bytes = await request.body()

    if not _verify_signature(payload_bytes, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = await request.json()

    if x_github_event == "pull_request":
        action = payload.get("action")
        if action in REVIEW_ACTIONS:
            background_tasks.add_task(_handle_pr_event, payload)
            return {"status": "review queued", "action": action}

    return {"status": "ignored", "event": x_github_event}

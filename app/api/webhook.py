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
import uuid

from fastapi import APIRouter, Header, HTTPException, Request, BackgroundTasks
from app.core.database import AsyncSessionLocal
from app.services.review_store import save_review, get_repo_patterns, annotate_with_patterns

from app.core.config import settings
from app.services.diff_processor import process_pr_files
from app.services.llm_reviewer import review_pr
from app.services.github_service import get_github_client, post_review, post_review_failure_notice

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
    action = payload.get("action")
    pr_data = payload.get("pull_request", {})
    installation_id = payload.get("installation", {}).get("id")

    if not installation_id:
        logger.warning("No installation_id in payload, skipping")
        return

    repo_full_name = payload["repository"]["full_name"]
    pr_number = pr_data["number"]

    logger.info(f"Reviewing PR #{pr_number} in {repo_full_name} (action={action})")

    pr = None
    try:
        gh = get_github_client(installation_id)
        repo = gh.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)

        ctx = process_pr_files(pr, custom_rules=[])

        if not ctx.files:
            logger.info(f"PR #{pr_number}: no reviewable files after filtering, skipping")
            return

        async with AsyncSessionLocal() as db:
            patterns = await get_repo_patterns(db, repo_full_name, query_text=ctx.pr_title)
            if patterns:
                logger.info(f"Injecting {len(patterns)} historical patterns for {repo_full_name}")
                logger.info(f"Historical patterns: {patterns}")
            else:
                logger.info(f"No historical patterns found for {repo_full_name}")

        result = await review_pr(ctx, historical_patterns=patterns)
        logger.info(
            f"PR #{pr_number}: review complete — "
            f"{len(result.comments)} comments, approved={result.approved}"
        )

        async with AsyncSessionLocal() as db:
            await annotate_with_patterns(db, repo_full_name, result)

        post_review(pr, result)

        async with AsyncSessionLocal() as db:
            await save_review(db, repo_full_name, pr_number, result)

    except Exception as e:
        error_type = type(e).__name__
        incident_id = uuid.uuid4().hex[:12]
        # Retryable errors (transient):
        # - RateLimitError: OpenAI rate limit (will retry in provider)
        # - APITimeoutError: Timeout (will retry in provider)  
        # - APIConnectionError: Network (will retry in provider)
        # Fatal errors:
        # - ValidationError: Schema mismatch (after all retries exhausted)
        # - JSONDecodeError: Unparseable response
        # - Other: Unknown errors
        
        is_transient = error_type in {"RateLimitError", "APITimeoutError", "APIConnectionError", "Timeout"}
        error_level = "warning" if is_transient else "error"
        
        logger_fn = getattr(logger, error_level)
        logger_fn(
            f"Failed to review PR #{pr_number} in {repo_full_name}: "
            f"{error_type}: {str(e)[:200]}. "
            f"(Transient: {is_transient}, Incident: {incident_id})"
        )
        logger.exception(f"Full traceback for PR #{pr_number} (incident {incident_id}):")

        if pr is not None:
            try:
                if is_transient:
                    failure_category = "temporary"
                elif error_type in {"ValidationError", "JSONDecodeError", "ValueError"}:
                    failure_category = "schema"
                else:
                    failure_category = "unexpected"

                post_review_failure_notice(
                    pr,
                    failure_category=failure_category,
                    incident_id=incident_id,
                )
            except Exception as notify_err:
                logger.warning(
                    f"Failed to post failure notice for PR #{pr_number} in {repo_full_name} "
                    f"(incident {incident_id}): {notify_err}"
                )


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

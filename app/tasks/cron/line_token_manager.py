"""
LINE channel access token management background task.

This task runs every 15 days to:
1. Generate new channel access tokens before expiration
2. Revoke expired tokens via LINE API
3. Clean up old revoked tokens from database
"""

import asyncio

from app.celery import celery
from app.db.session import get_sync_session
from app.services.line.line_token_management_service import (
    get_line_channel_token_service,
)
from app.utils.logging import get_logger
from app.utils.datetime_utils import naive_utc_now


@celery.task(bind=True, max_retries=3, default_retry_delay=300)
def line_token_manager_task(self, request_id: str):
    """
    Manage LINE channel access tokens.

    1. Generate new token if current expires within 7 days
    2. Revoke expired tokens via LINE API
    3. Clean up old revoked tokens
    """
    return asyncio.run(_async_line_token_manager(request_id))


async def _async_line_token_manager(request_id: str):

    logger = get_logger().bind(request_id=request_id)
    for db_session in get_sync_session():
        try:

            line_channel_token_service = get_line_channel_token_service(db_session)
            stats = {
                "new_tokens_generated": 0,
                "tokens_revoked": 0,
                "tokens_cleaned": 0,
            }

            # Generate new token if needed
            current_token = await line_channel_token_service.get_active_access_token()
            if (
                not current_token
                or (current_token.expires_at - naive_utc_now()).days <= 7
            ):
                new_token = (
                    await line_channel_token_service.generate_and_store_new_token()
                )
                if new_token:
                    stats["new_tokens_generated"] = 1
                    logger.info(f"Generated new token: {new_token.key_id}")

            # Revoke expired tokens
            try:
                valid_kids = await line_channel_token_service.get_valid_token_kids()
                logger.info(f"Valid KIDs: {valid_kids}")
                expired_tokens = (
                    await line_channel_token_service.get_expired_tokens_by_kids(
                        valid_kids
                    )
                )

                for token in expired_tokens:
                    if await line_channel_token_service.revoke_channel_access_token(
                        token.access_token
                    ):
                        await line_channel_token_service.mark_token_as_revoked(
                            token.key_id
                        )
                        stats["tokens_revoked"] += 1
            except Exception as e:
                logger.error(f"Token revocation failed: {str(e)}")

            # Clean up old tokens
            stats["tokens_cleaned"] = (
                await line_channel_token_service.cleanup_expired_tokens()
            )

            logger.info("LINE token management completed", **stats)
            return {"status": "success"}

        except Exception as e:
            logger.error(f"LINE token management failed: {str(e)}", exc_info=True)
            return {"status": "error", "message": str(e)}

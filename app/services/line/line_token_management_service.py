import json
import time
from datetime import timedelta
from pathlib import Path
from typing import Dict, List, Optional

import httpx
import jwt
from jwcrypto import jwk
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import select, and_, update
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.db.models import LineChannelAccessToken
from app.utils.logging import get_logger
from app.utils.errors import LineApplicationError
from app.utils.datetime_utils import naive_utc_now

logger = get_logger()


class LineChannelTokenService:
    """Service for managing LINE channel access tokens."""

    def __init__(self, db_session: Session):
        self.db = db_session
        self.key_file = Path(settings.LINE_SIGNING_KEY_PATH)

    def _load_signing_keys(self) -> dict:
        """Load RSA signing keys from file."""
        if not self.key_file.exists():
            raise LineApplicationError(
                f"Signing key file not found: {self.key_file}",
            )

        with open(self.key_file, "r") as f:
            keys = json.load(f)

        if "private_key" not in keys:
            raise LineApplicationError(
                "Invalid key file: missing private_key",
            )

        return keys

    def _generate_jwt_token(self, exp_minutes: int = 30) -> str:
        """Generate JWT token for LINE API authentication."""
        if not all([settings.LINE_CHANNEL_ID, settings.LINE_KID]):
            raise LineApplicationError(
                "LINE_CHANNEL_ID and LINE_KID must be configured",
            )

        keys = self._load_signing_keys()
        current_time = int(time.time())

        headers = {
            "alg": "RS256",
            "typ": "JWT",
            "kid": settings.LINE_KID,
        }

        payload = {
            "iss": settings.LINE_CHANNEL_ID,
            "sub": settings.LINE_CHANNEL_ID,
            "aud": "https://api.line.me/",
            "exp": current_time + (exp_minutes * 60),
            "iat": current_time,
            "token_exp": 60 * 60 * 24 * 30,  # 30 days
        }

        private_key_obj = RSAAlgorithm.from_jwk(json.dumps(keys["private_key"]))
        return jwt.encode(payload, private_key_obj, algorithm="RS256", headers=headers)  # type: ignore

    async def issue_channel_access_token(self) -> Dict[str, str]:
        """Issue a new channel access token via LINE API."""
        jwt_token = self._generate_jwt_token()

        data = {
            "grant_type": "client_credentials",
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": jwt_token,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.line.me/oauth2/v2.1/token",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data=data,
                timeout=30.0,
            )

            if response.status_code != 200:
                raise LineApplicationError(
                    f"Failed to issue access token: {response.status_code} - {response.text}",
                )

            return response.json()

    async def get_valid_token_kids(self) -> List[str]:
        """Get all valid channel access token key IDs from LINE API."""
        jwt_token = self._generate_jwt_token()

        params = {
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": jwt_token,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.line.me/oauth2/v2.1/tokens/kid",
                params=params,
                timeout=30.0,
            )

            if response.status_code != 200:
                raise LineApplicationError(
                    f"Failed to get token kids: {response.status_code} - {response.text}",
                )

            return response.json().get("kids", [])

    async def revoke_channel_access_token(self, access_token: str) -> bool:
        """Revoke a channel access token via LINE API."""
        if not settings.LINE_CHANNEL_SECRET:
            raise LineApplicationError(
                "LINE_CHANNEL_SECRET must be configured",
            )

        data = {
            "client_id": settings.LINE_CHANNEL_ID,
            "client_secret": settings.LINE_CHANNEL_SECRET,
            "access_token": access_token,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.line.me/oauth2/v2.1/revoke",
                data=data,
                timeout=30.0,
            )

            return response.status_code == 200

    async def store_access_token(
        self, token_data: Dict[str, str]
    ) -> LineChannelAccessToken:
        """Store a new access token in the database."""
        expires_at = naive_utc_now() + timedelta(seconds=int(token_data["expires_in"]))

        # Deactivate all existing tokens first
        self.db.execute(
            update(LineChannelAccessToken)
            .values(is_active=False)
            .where(LineChannelAccessToken.is_active == True)
        )

        # Create new token record
        new_token = LineChannelAccessToken(
            key_id=token_data["key_id"],
            access_token=token_data["access_token"],
            token_type=token_data.get("token_type", "Bearer"),
            expires_in=token_data["expires_in"],
            expires_at=expires_at,
            is_active=True,
        )

        self.db.add(new_token)
        self.db.commit()
        self.db.refresh(new_token)

        return new_token

    async def get_active_access_token(self) -> Optional[LineChannelAccessToken]:
        """Get the currently active access token."""
        result = self.db.execute(
            select(LineChannelAccessToken)
            .where(
                and_(
                    LineChannelAccessToken.is_active == True,
                    LineChannelAccessToken.is_revoked == False,
                    LineChannelAccessToken.expires_at > naive_utc_now(),
                )
            )
            .order_by(LineChannelAccessToken.expires_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_expired_tokens_by_kids(
        self, valid_kids: List[str]
    ) -> List[LineChannelAccessToken]:
        """Get expired tokens that match the provided key IDs."""
        result = self.db.execute(
            select(LineChannelAccessToken).where(
                and_(
                    LineChannelAccessToken.key_id.in_(valid_kids),
                    LineChannelAccessToken.expires_at <= naive_utc_now(),
                    LineChannelAccessToken.is_revoked == False,
                )
            )
        )
        return list(result.scalars().all())

    async def mark_token_as_revoked(self, key_id: str) -> bool:
        """Mark a token as revoked in the database."""
        result = self.db.execute(
            update(LineChannelAccessToken)
            .where(LineChannelAccessToken.key_id == key_id)
            .values(
                is_revoked=True,
                is_active=False,
                revoked_at=naive_utc_now(),
            )
        )
        self.db.commit()
        return result.rowcount > 0

    async def generate_and_store_new_token(self) -> Optional[LineChannelAccessToken]:
        """Generate a new access token and store it in the database."""
        try:
            token_data = await self.issue_channel_access_token()
            return await self.store_access_token(token_data)
        except Exception as e:
            logger.error(f"Failed to generate and store new token: {e}")
            return None

    async def cleanup_expired_tokens(self) -> int:
        """Remove expired and revoked tokens that are safe to clean up."""
        cutoff_date = naive_utc_now() - timedelta(days=7)

        result = self.db.execute(
            select(LineChannelAccessToken).where(
                and_(
                    LineChannelAccessToken.is_revoked == True,
                    LineChannelAccessToken.revoked_at <= cutoff_date,
                )
            )
        )
        tokens_to_delete = list(result.scalars().all())

        for token in tokens_to_delete:
            self.db.delete(token)

        self.db.commit()
        return len(tokens_to_delete)

    async def get_messaging_access_token(self) -> Optional[str]:
        """Get the access token for LINE Messaging API calls."""
        active_token = await self.get_active_access_token()
        return active_token.access_token if active_token else None


def generate_signing_keys() -> None:
    """Generate RSA key pair for LINE Messaging API signing."""
    key_file = Path(settings.LINE_SIGNING_KEY_PATH)
    key_file.parent.mkdir(parents=True, exist_ok=True)

    # Generate RSA key pair
    key = jwk.JWK.generate(kty="RSA", alg="RS256", use="sig", size=2048)

    keys = {
        "private_key": json.loads(key.export_private()),
        "public_key": json.loads(key.export_public()),
        "generated_at": int(time.time()),
    }

    with open(key_file, "w") as f:
        json.dump(keys, f, indent=2)

    key_file.chmod(0o600)


def get_line_channel_token_service(db_session: Session) -> LineChannelTokenService:
    return LineChannelTokenService(db_session)

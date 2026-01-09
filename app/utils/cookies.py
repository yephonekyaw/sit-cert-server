from typing import Optional


class CookieUtils:
    """Utility class for managing authentication cookies"""

    @staticmethod
    def extract_bearer_token(authorization_header: Optional[str]) -> Optional[str]:
        """Extract Bearer token from Authorization header"""
        if not authorization_header:
            return None

        if not authorization_header.startswith("Bearer "):
            return None

        return authorization_header[7:]  # Remove "Bearer " prefix

"""Public product routes.

Company self-registration is not part of this single-instance edition.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/v1/public", tags=["public-product"])

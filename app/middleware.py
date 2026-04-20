"""Application middleware configuration."""

import uuid

from fastapi import Request

from app.config import settings


async def set_anonymous_user_id_cookie(request: Request, call_next):
    """Set anonymous_user_id cookie if not present and add it to request state."""
    anonymous_user_id = request.cookies.get("anonymous_user_id")
    generated_new_id = False
    
    if not anonymous_user_id:
        anonymous_user_id = str(uuid.uuid4())
        generated_new_id = True
    
    request.state.anonymous_user_id = anonymous_user_id
    request.state.generated_new_anonymous_id = generated_new_id
    
    response = await call_next(request)
    
    if generated_new_id:
        response.set_cookie(
            key="anonymous_user_id",
            value=anonymous_user_id,
            max_age=settings.anonymous_cookie_max_age,
            httponly=True,
            samesite="lax",
            secure=not settings.debug,
        )
    
    return response

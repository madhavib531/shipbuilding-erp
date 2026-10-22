"""Request authentication and role checks.

`current_user` resolves the bearer token to an active user (401 otherwise). `require(permission)` also checks
the user's role (403 otherwise). Handlers that record who made a change take the name from the returned
user, never from the request body.
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services import auth_service


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = bearer_token(request)
    user = auth_service.user_for_token(db, token) if token else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


def require(permission: str):
    """Dependency: the signed-in user, if their role grants `permission`."""
    def check(user: User = Depends(current_user)) -> User:
        if permission not in auth_service.PERMISSIONS[user.role]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Your role ({user.role.value}) does not allow this action")
        return user
    return check


def stamp(data, user: User):
    """A copy of a request body with `actor` set to the signed-in user's name."""
    return data.model_copy(update={"actor": user.display_name})

"""Sign-in, sign-out, the signed-in user, and user administration (admins only)."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import bearer_token, current_user, require
from app.database import get_db
from app.errors import InvalidInputError
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.schemas.user import LoginRequest, Me, PasswordChange, PasswordReset, UserCreate, UserRead, UserUpdate
from app.services import auth_service as service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
users_router = APIRouter(prefix="/api/v1/users", tags=["users"])


def _me(user: User) -> dict:
    return Me.model_validate(user).model_copy(update={"permissions": service.permissions_of(user.role)}).model_dump(mode="json")


@router.post("/login", response_model=SuccessResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    try:
        token, user, expires = service.login(db, data.username, data.password)
    except service.TooManyAttempts as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Too many failed sign-ins. Try again in {exc.retry_after // 60 + 1} minutes.",
                            headers={"Retry-After": str(exc.retry_after)})
    except InvalidInputError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.detail)
    return SuccessResponse(message="Signed in", data={"token": token, "expires_at": expires.isoformat(), "user": _me(user)})


@router.post("/logout", response_model=SuccessResponse)
def logout(request: Request, db: Session = Depends(get_db)):
    token = bearer_token(request)
    if token:
        service.logout(db, token)
    return SuccessResponse(message="Signed out")


@router.get("/me", response_model=SuccessResponse)
def me(user: User = Depends(current_user)):
    return SuccessResponse(message="Signed-in user", data=_me(user))


@router.post("/password", response_model=SuccessResponse)
def change_password(data: PasswordChange, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Changes your own password and signs out every session, including this one."""
    if not service.verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="The current password is incorrect")
    service.set_password(db, user, data.new_password)
    return SuccessResponse(message="Password changed; sign in again with the new password")


@users_router.get("", response_model=SuccessResponse)
def list_users(_: User = Depends(require("users")), db: Session = Depends(get_db)):
    users = db.scalars(select(User).order_by(User.display_name)).all()
    return SuccessResponse(message="Users retrieved", data=[UserRead.model_validate(u).model_dump(mode="json") for u in users])


@users_router.post("", response_model=SuccessResponse, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, _: User = Depends(require("users")), db: Session = Depends(get_db)):
    user = service.create_user(db, data.username, data.display_name, data.role, data.password, data.email or None)
    return SuccessResponse(message="User created", data=UserRead.model_validate(user).model_dump(mode="json"))


@users_router.patch("/{user_id}", response_model=SuccessResponse)
def update_user(user_id: int, data: UserUpdate, admin: User = Depends(require("users")), db: Session = Depends(get_db)):
    user = service.update_user(db, user_id, display_name=data.display_name, email=data.email, role=data.role,
                               is_active=data.is_active, acting_user=admin)
    return SuccessResponse(message="User updated", data=UserRead.model_validate(user).model_dump(mode="json"))


@users_router.post("/{user_id}/password", response_model=SuccessResponse)
def reset_password(user_id: int, data: PasswordReset, _: User = Depends(require("users")), db: Session = Depends(get_db)):
    """Sets a user's password and signs them out everywhere."""
    service.set_password(db, service.get_user(db, user_id), data.new_password)
    return SuccessResponse(message="Password reset; the user must sign in again")

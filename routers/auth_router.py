"""
Auth Router — JWT tabanlı KOBİ admin kimlik doğrulama
=====================================================
POST /auth/login  → {access_token, token_type, user}
GET  /auth/me     → mevcut kullanıcı bilgisi
"""

from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
import bcrypt as _bcrypt
from pydantic import BaseModel

from database.db import get_connection
from config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Kriptografi yardımcıları (passlib yerine bcrypt doğrudan kullanılıyor)
# ---------------------------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _hash(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def _verify(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# DB yardımcıları
# ---------------------------------------------------------------------------

def _get_user_by_username(username: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT id, username, password_hash, role, full_name, is_active, tenant_id "
        "FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _touch_last_login(user_id: int):
    conn = get_connection()
    conn.execute(
        "UPDATE users SET last_login = datetime('now','localtime') WHERE id = ?",
        (user_id,),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Dependency — mevcut kullanıcıyı token'dan al
# ---------------------------------------------------------------------------

class CurrentUser(BaseModel):
    id: int
    username: str
    role: str
    full_name: str | None
    tenant_id: int


async def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    cred_exc = HTTPException(status_code=401, detail="Kimlik doğrulaması başarısız")
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise cred_exc
    except JWTError:
        raise cred_exc

    user = _get_user_by_username(username)
    if not user or not user["is_active"]:
        raise cred_exc

    return CurrentUser(**{k: user[k] for k in ("id", "username", "role", "full_name", "tenant_id")})


# ---------------------------------------------------------------------------
# Endpointler
# ---------------------------------------------------------------------------

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


@router.post("/login", response_model=LoginResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = _get_user_by_username(form_data.username)
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya şifre hatalı")
    if not _verify(form_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya şifre hatalı")

    _touch_last_login(user["id"])
    token = _create_token({"sub": user["username"], "role": user["role"], "tid": user["tenant_id"]})

    return LoginResponse(
        access_token=token,
        user={
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "full_name": user["full_name"],
        },
    )


@router.get("/me")
async def me(current_user: CurrentUser = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "full_name": current_user.full_name,
    }

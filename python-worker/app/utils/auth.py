"""
Authentication and User Management Utilities
JWT-based authentication with role-based access control
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
import bcrypt as _bcrypt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging
import os

logger = logging.getLogger(__name__)

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# bcrypt directly — passlib 1.7.4 breaks on bcrypt>=4 (its version
# probe + 72-byte self-test crash on import); bcrypt is already a dep.

# HTTP Bearer for token extraction
security = HTTPBearer()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Dict[str, Any]:
    """Verify JWT token and return payload"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        # log it — an expired-token burst is session rot in the
        # client, and without this line the watcher sees silence while
        # every authed call 401s
        logger.warning("auth: token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:  # Catch all JWT exceptions
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

def hash_password(password: str) -> str:
    """bcrypt hash for storage — real accounts must never sit in the
    users table as readable passwords. Truncated at bcrypt's 72-byte
    input limit (standard practice — the digest is still salted)."""
    return _bcrypt.hashpw(password.encode()[:72], _bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """bcrypt verify with a legacy-plaintext fallback — rows created
    before hashing landed store the raw password; they still verify so
    existing accounts keep working (rehash on next write)."""
    try:
        if hashed_password and hashed_password.startswith("$2"):
            return _bcrypt.checkpw(
                plain_password.encode()[:72], hashed_password.encode())
        return plain_password == hashed_password
    except Exception:
        return False

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """Get current user from JWT token"""
    token = credentials.credentials
    payload = verify_token(token)
    
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # In a real application, you would fetch user from database
    # For now, return basic user info from token
    return {
        "id": user_id,  # Keep as string (UUID)
        "username": payload.get("username"),
        "role": payload.get("role", "user")
    }

async def get_admin_user(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Get current user and verify admin role"""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

def create_user_token(user_data: Dict[str, Any]) -> str:
    """Create token for user with user data embedded"""
    token_data = {
        "sub": str(user_data["id"]),
        "username": user_data["username"],
        "role": user_data["role"],
        "email": user_data["email"]
    }
    return create_access_token(token_data)

def get_token_from_header(authorization: str) -> Optional[str]:
    """Extract token from Authorization header"""
    if authorization.startswith("Bearer "):
        return authorization[7:]  # Remove "Bearer " prefix
    return None

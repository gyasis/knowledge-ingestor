"""
Authentication and authorization module for the Knowledge Ingestor API.

This module provides comprehensive authentication support including:
- API key authentication
- OAuth 2.0 / JWT token authentication
- Role-based access control
- Rate limiting integration
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from pydantic import BaseModel
import secrets
import hashlib
from enum import Enum

from ..core.config import get_config
from ..utils.logging import get_logger

logger = get_logger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class UserRole(str, Enum):
    """User roles for access control."""
    ADMIN = "admin"
    USER = "user"
    READONLY = "readonly"


class APIKeyScope(str, Enum):
    """API key scopes for fine-grained access control."""
    INGEST = "ingest"
    SEARCH = "search"
    ADMIN = "admin"
    READONLY = "readonly"


class User(BaseModel):
    """User model for authentication."""
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    roles: List[UserRole] = []
    is_active: bool = True
    created_at: datetime
    last_login: Optional[datetime] = None


class APIKey(BaseModel):
    """API key model."""
    key_id: str
    name: str
    scopes: List[APIKeyScope]
    is_active: bool = True
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used: Optional[datetime] = None
    usage_count: int = 0


class TokenData(BaseModel):
    """JWT token data model."""
    username: Optional[str] = None
    scopes: List[str] = []
    exp: Optional[datetime] = None


class AuthManager:
    """
    Centralized authentication and authorization manager.
    
    Handles both API key and JWT token authentication,
    user management, and access control.
    """
    
    def __init__(self):
        self.config = get_config()
        self.users_db: Dict[str, Dict[str, Any]] = {}
        self.api_keys_db: Dict[str, Dict[str, Any]] = {}
        self.secret_key = self.config.api.auth_secret_key or self._generate_secret_key()
        self.algorithm = self.config.api.auth_algorithm
        self.access_token_expire_minutes = self.config.api.auth_expire_minutes
        
        # Initialize with default admin user if enabled
        if self.config.api.auth_enabled:
            self._initialize_default_users()
    
    def _generate_secret_key(self) -> str:
        """Generate a secure random secret key."""
        return secrets.token_urlsafe(32)
    
    def _initialize_default_users(self):
        """Initialize default users for testing/development."""
        admin_user = {
            "username": "admin",
            "email": "admin@knowledge-ingestor.local",
            "full_name": "System Administrator",
            "hashed_password": self.get_password_hash("admin123"),
            "roles": [UserRole.ADMIN],
            "is_active": True,
            "created_at": datetime.utcnow(),
            "last_login": None
        }
        self.users_db["admin"] = admin_user
        logger.info("Initialized default admin user")
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)
    
    def get_password_hash(self, password: str) -> str:
        """Generate password hash."""
        return pwd_context.hash(password)
    
    def get_user(self, username: str) -> Optional[User]:
        """Get user by username."""
        user_data = self.users_db.get(username)
        if user_data:
            return User(**user_data)
        return None
    
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username and password."""
        user_data = self.users_db.get(username)
        if not user_data:
            return None
        if not self.verify_password(password, user_data["hashed_password"]):
            return None
        
        # Update last login
        user_data["last_login"] = datetime.utcnow()
        
        return User(**user_data)
    
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None):
        """Create JWT access token."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def verify_token(self, token: str) -> Optional[TokenData]:
        """Verify and decode JWT token."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            username: str = payload.get("sub")
            scopes: List[str] = payload.get("scopes", [])
            exp = payload.get("exp")
            
            if username is None:
                return None
            
            return TokenData(
                username=username,
                scopes=scopes,
                exp=datetime.fromtimestamp(exp) if exp else None
            )
        except JWTError as e:
            logger.warning(f"JWT verification failed: {e}")
            return None
    
    def generate_api_key(self, name: str, scopes: List[APIKeyScope], 
                        expires_days: Optional[int] = None) -> tuple[str, str]:
        """
        Generate a new API key.
        
        Returns:
            tuple: (key_id, api_key) where key_id is for storage and api_key is for client
        """
        key_id = secrets.token_urlsafe(16)
        api_key = f"ki_{secrets.token_urlsafe(32)}"
        
        # Hash the API key for storage
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        expires_at = None
        if expires_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_days)
        
        api_key_data = {
            "key_id": key_id,
            "name": name,
            "key_hash": key_hash,
            "scopes": scopes,
            "is_active": True,
            "created_at": datetime.utcnow(),
            "expires_at": expires_at,
            "last_used": None,
            "usage_count": 0
        }
        
        self.api_keys_db[key_hash] = api_key_data
        logger.info(f"Generated API key '{name}' with scopes: {scopes}")
        
        return key_id, api_key
    
    def verify_api_key(self, api_key: str) -> Optional[APIKey]:
        """Verify API key and return key info."""
        if not api_key or not api_key.startswith("ki_"):
            return None
        
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_data = self.api_keys_db.get(key_hash)
        
        if not key_data:
            return None
        
        # Check if key is active
        if not key_data["is_active"]:
            return None
        
        # Check if key has expired
        if key_data["expires_at"] and datetime.utcnow() > key_data["expires_at"]:
            return None
        
        # Update usage statistics
        key_data["last_used"] = datetime.utcnow()
        key_data["usage_count"] += 1
        
        return APIKey(**key_data)
    
    def revoke_api_key(self, key_id: str) -> bool:
        """Revoke an API key."""
        for key_hash, key_data in self.api_keys_db.items():
            if key_data["key_id"] == key_id:
                key_data["is_active"] = False
                logger.info(f"Revoked API key: {key_id}")
                return True
        return False
    
    def list_api_keys(self) -> List[APIKey]:
        """List all API keys (without sensitive data)."""
        keys = []
        for key_data in self.api_keys_db.values():
            # Don't include key_hash in the response
            safe_data = {k: v for k, v in key_data.items() if k != "key_hash"}
            keys.append(APIKey(**safe_data))
        return keys


# Global auth manager instance
auth_manager = AuthManager()


# Authentication dependencies
async def get_current_user_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
) -> Optional[User]:
    """Get current user from JWT token."""
    if not credentials:
        return None
    
    token_data = auth_manager.verify_token(credentials.credentials)
    if not token_data:
        return None
    
    user = auth_manager.get_user(username=token_data.username)
    if not user or not user.is_active:
        return None
    
    return user


async def get_current_user_api_key(
    api_key: Optional[str] = Security(api_key_header)
) -> Optional[tuple[APIKey, List[str]]]:
    """Get current user from API key."""
    if not api_key:
        return None
    
    key_info = auth_manager.verify_api_key(api_key)
    if not key_info:
        return None
    
    # Convert scopes to strings
    scopes = [scope.value for scope in key_info.scopes]
    return key_info, scopes


async def get_current_user(
    token_user: Optional[User] = Depends(get_current_user_token),
    api_key_result: Optional[tuple] = Depends(get_current_user_api_key)
) -> Optional[Dict[str, Any]]:
    """
    Get current authenticated user from either JWT token or API key.
    
    Returns user info with authentication method and scopes.
    """
    if token_user:
        return {
            "auth_method": "jwt",
            "user": token_user,
            "scopes": [role.value for role in token_user.roles]
        }
    
    if api_key_result:
        key_info, scopes = api_key_result
        return {
            "auth_method": "api_key",
            "api_key": key_info,
            "scopes": scopes
        }
    
    return None


def require_auth(scopes: Optional[List[str]] = None):
    """
    Dependency factory for requiring authentication with optional scopes.
    
    Args:
        scopes: List of required scopes (permissions)
    
    Returns:
        Dependency function
    """
    async def auth_dependency(
        current_user: Optional[Dict[str, Any]] = Depends(get_current_user)
    ):
        if not current_user:
            raise HTTPException(
                status_code=401,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Check scopes if specified
        if scopes:
            user_scopes = current_user.get("scopes", [])
            if not any(scope in user_scopes for scope in scopes):
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient permissions. Required: {scopes}",
                )
        
        return current_user
    
    return auth_dependency


def require_api_key(scopes: Optional[List[APIKeyScope]] = None):
    """
    Dependency factory specifically for API key authentication.
    
    Args:
        scopes: List of required API key scopes
        
    Returns:
        Dependency function
    """
    async def api_key_dependency(
        api_key: Optional[str] = Security(api_key_header)
    ):
        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="API key required",
                headers={"WWW-Authenticate": "ApiKey"},
            )
        
        key_info = auth_manager.verify_api_key(api_key)
        if not key_info:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key"
            )
        
        # Check scopes if specified
        if scopes:
            if not any(scope in key_info.scopes for scope in scopes):
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient API key permissions. Required: {scopes}",
                )
        
        return key_info
    
    return api_key_dependency


# Role-based access control helpers
def require_role(role: UserRole):
    """Require specific user role."""
    return require_auth([role.value])


def require_admin():
    """Require admin role."""
    return require_role(UserRole.ADMIN)


# Scope-based access control for API keys
def require_ingest_scope():
    """Require ingest scope for API operations."""
    return require_api_key([APIKeyScope.INGEST])


def require_search_scope():
    """Require search scope for API operations."""
    return require_api_key([APIKeyScope.SEARCH])


def require_admin_scope():
    """Require admin scope for API operations."""
    return require_api_key([APIKeyScope.ADMIN])
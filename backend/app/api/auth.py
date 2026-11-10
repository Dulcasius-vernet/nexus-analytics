from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from psycopg import Error as PsycopgError

from app.core.config import settings
from app.core.security import create_session, hash_password, read_session, verify_password
from app.db.connection import DatabaseConnectionError, get_connection

router = APIRouter(prefix="/auth", tags=["authentication"])
COOKIE_NAME = "nexus_session"


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    business_name: str = Field(min_length=2, max_length=160)
    industry: str = Field(min_length=2, max_length=100)
    workspace_name: str = Field(min_length=2, max_length=160)
    objective_type: str = Field(min_length=2, max_length=80)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


def set_session(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, secure=settings.app_env == "production",
        samesite="lax", max_age=12 * 60 * 60, path="/",
    )


def get_current_user(nexus_session: str | None = Cookie(default=None)) -> dict:
    if not nexus_session:
        raise HTTPException(status_code=401, detail="Please sign in to continue")
    claims = read_session(nexus_session)
    if not claims:
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again")
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT u.user_id, u.full_name, u.email, bm.business_id, bm.role
                   FROM users u JOIN business_memberships bm ON bm.user_id = u.user_id
                   WHERE u.user_id = %s AND bm.business_id = %s AND u.is_active = TRUE""",
                (claims["uid"], claims["bid"]),
            )
            row = cur.fetchone()
    except (DatabaseConnectionError, PsycopgError) as exc:
        raise HTTPException(status_code=503, detail="Authentication service is unavailable") from exc
    if not row:
        raise HTTPException(status_code=401, detail="This account no longer has access to the workspace")
    return {"user_id": row[0], "full_name": row[1], "email": row[2], "business_id": row[3], "role": row[4]}


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, response: Response):
    email = str(request.email).strip().lower()
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE LOWER(email) = %s", (email,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="An account with this email already exists")
            cur.execute(
                "INSERT INTO users (full_name, email, password_hash) VALUES (%s, %s, %s) RETURNING user_id",
                (request.full_name.strip(), email, hash_password(request.password)),
            )
            user_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO businesses (business_name, industry) VALUES (%s, %s) RETURNING business_id",
                (request.business_name.strip(), request.industry.strip()),
            )
            business_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO business_memberships (user_id, business_id, role) VALUES (%s, %s, 'owner')",
                (user_id, business_id),
            )
            cur.execute(
                "INSERT INTO workspaces (business_id, workspace_name, description) VALUES (%s, %s, %s) RETURNING workspace_id",
                (business_id, request.workspace_name.strip(), "Default business analytics workspace"),
            )
            workspace_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO analytical_objectives (workspace_id, objective_name, objective_type, description) VALUES (%s, %s, %s, %s)",
                (workspace_id, request.objective_type.replace("-", " ").title(), request.objective_type, "Initial objective selected during onboarding"),
            )
    except HTTPException:
        raise
    except (DatabaseConnectionError, PsycopgError) as exc:
        raise HTTPException(status_code=503, detail="Unable to create the account. Check database availability and try again") from exc
    set_session(response, create_session(user_id, business_id))
    return {"user_id": user_id, "business_id": business_id, "workspace_id": workspace_id, "full_name": request.full_name, "email": email, "role": "owner"}


@router.post("/login")
def login(request: LoginRequest, response: Response):
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT u.user_id, u.full_name, u.email, u.password_hash, bm.business_id, bm.role
                   FROM users u JOIN business_memberships bm ON bm.user_id = u.user_id
                   WHERE LOWER(u.email) = %s AND u.is_active = TRUE
                   ORDER BY bm.business_id LIMIT 1""",
                (str(request.email).strip().lower(),),
            )
            row = cur.fetchone()
    except (DatabaseConnectionError, PsycopgError) as exc:
        raise HTTPException(status_code=503, detail="Authentication service is unavailable") from exc
    if not row or not verify_password(request.password, row[3]):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    set_session(response, create_session(row[0], row[4]))
    return {"user_id": row[0], "full_name": row[1], "email": row[2], "business_id": row[4], "role": row[5]}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax")
    return {"status": "signed_out"}

from fastapi import Query


def get_business_id(business_id: int | None = Query(default=None, ge=1), user: dict = Depends(get_current_user)) -> int:
    """Resolve a requested business only when it belongs to the authenticated user."""
    owned_business_id = int(user["business_id"])
    if business_id is not None and business_id != owned_business_id:
        raise HTTPException(status_code=403, detail="You do not have access to this business")
    return owned_business_id

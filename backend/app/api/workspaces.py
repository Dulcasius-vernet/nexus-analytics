from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from psycopg import Error as PsycopgError

from app.api.auth import get_current_user
from app.db.connection import DatabaseConnectionError, get_connection

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class WorkspaceCreate(BaseModel):
    workspace_name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=1000)


@router.get("")
def list_workspaces(user: dict = Depends(get_current_user)):
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT workspace_id, workspace_name, description, created_at FROM workspaces WHERE business_id = %s ORDER BY created_at", (user["business_id"],))
            return [{"workspace_id": r[0], "workspace_name": r[1], "description": r[2], "created_at": r[3]} for r in cur.fetchall()]
    except (DatabaseConnectionError, PsycopgError) as exc:
        raise HTTPException(status_code=503, detail="Workspace service is unavailable") from exc


@router.post("", status_code=201)
def create_workspace(payload: WorkspaceCreate, user: dict = Depends(get_current_user)):
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO workspaces (business_id, workspace_name, description) VALUES (%s, %s, %s) RETURNING workspace_id, workspace_name, description, created_at", (user["business_id"], payload.workspace_name.strip(), payload.description))
            row = cur.fetchone()
        return {"workspace_id": row[0], "workspace_name": row[1], "description": row[2], "created_at": row[3]}
    except PsycopgError as exc:
        if getattr(exc, "sqlstate", None) == "23505":
            raise HTTPException(status_code=409, detail="A workspace with that name already exists") from exc
        raise HTTPException(status_code=503, detail="Workspace could not be created") from exc

#!/usr/bin/env python3
"""Manage local username/password users for public Kuma workflow pages."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import stat
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path("/Users/kumaai/Library/Application Support/kumaai-sync/meeting-minutes-review")
DB_PATH = Path(os.environ.get("MEETING_ACCESS_DB_PATH") or BASE_DIR / "access-users.sqlite3").expanduser()
LEGACY_CONFIG_PATH = Path(os.environ.get("MEETING_ACCESS_CONFIG_PATH") or BASE_DIR / "access-control.json").expanduser()
TOKEN_DIR = DB_PATH.parent / "user-tokens"
PASSWORD_DIR = DB_PATH.parent / "user-passwords"
ADMIN_PASSWORD_PATH = Path(os.environ.get("MEETING_ADMIN_PASSWORD_PATH") or DB_PATH.parent / "admin-access-password.txt").expanduser()
ADMIN_TOKEN_PATH = Path(os.environ.get("MEETING_ADMIN_TOKEN_PATH") or DB_PATH.parent / "admin-access-token.txt").expanduser()
VALID_ROLES = {"admin", "editor", "viewer", "external_viewer"}
PASSWORD_HASH_ITERATIONS = 260000


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def password_hash(password: str) -> str:
    salt = secrets.token_urlsafe(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return hmac.compare_digest(expected, digest)
    except Exception:
        return False


def generate_password() -> str:
    return "Kuma-" + secrets.token_urlsafe(14)


def normalize_groups(value: str | list[Any] | None) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def safe_filename(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value.strip())
    return cleaned.strip("._") or "user"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS access_users (
            user_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT 'viewer',
            groups_json TEXT NOT NULL DEFAULT '[]',
            password_hash TEXT NOT NULL DEFAULT '',
            token_hash TEXT NOT NULL DEFAULT '',
            disabled INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    DB_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)
    migrate_legacy_config(conn)
    ensure_admin(conn)
    return conn


def row_to_user(row: sqlite3.Row) -> dict[str, Any]:
    try:
        groups = json.loads(row["groups_json"] or "[]")
    except Exception:
        groups = []
    return {
        "user_id": row["user_id"],
        "display_name": row["display_name"] or "",
        "role": row["role"] or "",
        "groups": normalize_groups(groups),
        "disabled": bool(row["disabled"]),
        "created_at": row["created_at"] or "",
        "updated_at": row["updated_at"] or "",
        "password_present": bool(row["password_hash"]),
        "token_present": bool(row["token_hash"]),
    }


def upsert_user(conn: sqlite3.Connection, user: dict[str, Any]) -> None:
    timestamp = now_iso()
    conn.execute(
        """
        INSERT INTO access_users (
            user_id, display_name, role, groups_json, password_hash, token_hash, disabled, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            display_name=excluded.display_name,
            role=excluded.role,
            groups_json=excluded.groups_json,
            password_hash=excluded.password_hash,
            token_hash=excluded.token_hash,
            disabled=excluded.disabled,
            updated_at=excluded.updated_at
        """,
        (
            str(user.get("user_id") or "").strip(),
            str(user.get("display_name") or user.get("user_id") or ""),
            str(user.get("role") or "viewer"),
            json.dumps(normalize_groups(user.get("groups")), ensure_ascii=False),
            str(user.get("password_hash") or ""),
            str(user.get("token_hash") or ""),
            1 if user.get("disabled") is True else 0,
            str(user.get("created_at") or timestamp),
            str(user.get("updated_at") or timestamp),
        ),
    )


def migrate_legacy_config(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) FROM access_users").fetchone()[0] or not LEGACY_CONFIG_PATH.exists():
        return
    try:
        payload = json.loads(LEGACY_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return
    for user in payload.get("users") or []:
        if isinstance(user, dict) and str(user.get("user_id") or "").strip():
            upsert_user(conn, user)
    conn.commit()


def ensure_admin(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT * FROM access_users WHERE user_id = ?", ("admin",)).fetchone()
    if row and row["password_hash"]:
        return
    password = generate_password()
    write_password_file("admin", password)
    if row:
        conn.execute(
            "UPDATE access_users SET password_hash = ?, disabled = 0, updated_at = ? WHERE user_id = ?",
            (password_hash(password), now_iso(), "admin"),
        )
    else:
        token = secrets.token_urlsafe(32)
        ADMIN_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        ADMIN_TOKEN_PATH.write_text(token + "\n", encoding="utf-8")
        ADMIN_TOKEN_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)
        upsert_user(
            conn,
            {
                "user_id": "admin",
                "display_name": "管理员",
                "role": "admin",
                "groups": ["admin", "local"],
                "password_hash": password_hash(password),
                "token_hash": token_hash(token),
                "created_at": now_iso(),
                "updated_at": now_iso(),
            },
        )
    conn.commit()


def find_user(conn: sqlite3.Connection, user_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM access_users WHERE user_id = ?", (user_id,)).fetchone()


def write_token_file(user_id: str, token: str) -> Path:
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    token_path = TOKEN_DIR / f"{safe_filename(user_id)}.txt"
    token_path.write_text(token + "\n", encoding="utf-8")
    token_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return token_path


def write_password_file(user_id: str, password: str) -> Path:
    password_path = ADMIN_PASSWORD_PATH if user_id == "admin" else PASSWORD_DIR / f"{safe_filename(user_id)}.txt"
    password_path.parent.mkdir(parents=True, exist_ok=True)
    password_path.write_text(password + "\n", encoding="utf-8")
    password_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return password_path


def add_user(args: argparse.Namespace) -> dict[str, Any]:
    if args.role not in VALID_ROLES:
        raise SystemExit(f"invalid role: {args.role}")
    with connect() as conn:
        if find_user(conn, args.user_id):
            raise SystemExit(f"user already exists: {args.user_id}")
        password = args.password or generate_password()
        password_path = write_password_file(args.user_id, password)
        upsert_user(
            conn,
            {
                "user_id": args.user_id,
                "display_name": args.display_name or args.user_id,
                "role": args.role,
                "groups": normalize_groups(args.groups),
                "password_hash": password_hash(password),
                "disabled": False,
                "created_at": now_iso(),
                "updated_at": now_iso(),
            },
        )
        conn.commit()
        return {"ok": True, "action": "added", "user": public_user(conn, args.user_id), "password_path": str(password_path)}


def update_user(args: argparse.Namespace) -> dict[str, Any]:
    if args.role not in VALID_ROLES:
        raise SystemExit(f"invalid role: {args.role}")
    with connect() as conn:
        row = find_user(conn, args.user_id)
        if not row:
            raise SystemExit(f"user not found: {args.user_id}")
        conn.execute(
            """
            UPDATE access_users
            SET display_name = ?, role = ?, groups_json = ?, disabled = 0, updated_at = ?
            WHERE user_id = ?
            """,
            (
                args.display_name or row["display_name"] or args.user_id,
                args.role,
                json.dumps(normalize_groups(args.groups), ensure_ascii=False),
                now_iso(),
                args.user_id,
            ),
        )
        conn.commit()
        return {"ok": True, "action": "updated", "user": public_user(conn, args.user_id)}


def reset_password(args: argparse.Namespace) -> dict[str, Any]:
    with connect() as conn:
        if not find_user(conn, args.user_id):
            raise SystemExit(f"user not found: {args.user_id}")
        password = args.password or generate_password()
        password_path = write_password_file(args.user_id, password)
        conn.execute(
            "UPDATE access_users SET password_hash = ?, disabled = 0, updated_at = ? WHERE user_id = ?",
            (password_hash(password), now_iso(), args.user_id),
        )
        conn.commit()
        return {"ok": True, "action": "password_reset", "user": public_user(conn, args.user_id), "password_path": str(password_path)}


def rotate_token(args: argparse.Namespace) -> dict[str, Any]:
    with connect() as conn:
        if not find_user(conn, args.user_id):
            raise SystemExit(f"user not found: {args.user_id}")
        token = secrets.token_urlsafe(32)
        token_path = write_token_file(args.user_id, token)
        conn.execute(
            "UPDATE access_users SET token_hash = ?, disabled = 0, updated_at = ? WHERE user_id = ?",
            (token_hash(token), now_iso(), args.user_id),
        )
        conn.commit()
        return {"ok": True, "action": "token_rotated", "user": public_user(conn, args.user_id), "token_path": str(token_path)}


def disable_user(args: argparse.Namespace) -> dict[str, Any]:
    with connect() as conn:
        if not find_user(conn, args.user_id):
            raise SystemExit(f"user not found: {args.user_id}")
        conn.execute("UPDATE access_users SET disabled = 1, updated_at = ? WHERE user_id = ?", (now_iso(), args.user_id))
        conn.commit()
        return {"ok": True, "action": "disabled", "user": public_user(conn, args.user_id)}


def remove_user(args: argparse.Namespace) -> dict[str, Any]:
    with connect() as conn:
        if not find_user(conn, args.user_id):
            raise SystemExit(f"user not found: {args.user_id}")
        conn.execute("DELETE FROM access_users WHERE user_id = ?", (args.user_id,))
        conn.commit()
    for directory in (TOKEN_DIR, PASSWORD_DIR):
        path = directory / f"{safe_filename(args.user_id)}.txt"
        if path.exists():
            path.unlink()
    return {"ok": True, "action": "removed", "user_id": args.user_id}


def public_user(conn: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    row = find_user(conn, user_id)
    if not row:
        return {}
    return row_to_user(row)


def list_users(_args: argparse.Namespace) -> dict[str, Any]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM access_users ORDER BY created_at, user_id").fetchall()
        users = [row_to_user(row) for row in rows]
    return {"ok": True, "db_path": str(DB_PATH), "legacy_config_path": str(LEGACY_CONFIG_PATH), "user_count": len(users), "users": users}


def print_result(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"{result.get('action') or 'list'}: ok")
    if result.get("db_path"):
        print(f"db_path: {result['db_path']}")
    if result.get("password_path"):
        print(f"password_path: {result['password_path']}")
    if result.get("token_path"):
        print(f"token_path: {result['token_path']}")
    if result.get("user"):
        print(json.dumps(result["user"], ensure_ascii=False))
    if result.get("users") is not None:
        for user in result["users"]:
            print(json.dumps(user, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="管理 Kuma 公网用户名/密码访问用户")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="新增用户并生成或设置密码")
    add.add_argument("--user-id", required=True)
    add.add_argument("--display-name", default="")
    add.add_argument("--role", default="viewer", choices=sorted(VALID_ROLES))
    add.add_argument("--groups", default="")
    add.add_argument("--password", default="", help="指定登录密码；留空则自动生成")

    update = sub.add_parser("update", help="修改用户显示名、角色和分组，不改密码")
    update.add_argument("--user-id", required=True)
    update.add_argument("--display-name", default="")
    update.add_argument("--role", default="viewer", choices=sorted(VALID_ROLES))
    update.add_argument("--groups", default="")

    rotate = sub.add_parser("reset-password", aliases=["rotate"], help="重置用户登录密码")
    rotate.add_argument("--user-id", required=True)
    rotate.add_argument("--password", default="", help="指定登录密码；留空则自动生成")

    rotate_token_cmd = sub.add_parser("rotate-token", help="轮换用户 API 令牌")
    rotate_token_cmd.add_argument("--user-id", required=True)

    disable = sub.add_parser("disable", help="禁用用户")
    disable.add_argument("--user-id", required=True)

    remove = sub.add_parser("remove", help="删除用户和该用户本地密码/API 令牌文件")
    remove.add_argument("--user-id", required=True)

    sub.add_parser("list", help="列出用户，不输出密码或令牌明文")

    args = parser.parse_args()
    if args.command == "add":
        result = add_user(args)
    elif args.command == "update":
        result = update_user(args)
    elif args.command in {"reset-password", "rotate"}:
        result = reset_password(args)
    elif args.command == "rotate-token":
        result = rotate_token(args)
    elif args.command == "disable":
        result = disable_user(args)
    elif args.command == "remove":
        result = remove_user(args)
    else:
        result = list_users(args)
    print_result(result, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

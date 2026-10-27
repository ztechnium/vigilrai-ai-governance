"""
Admin Provisioning CLI

Phase 22: Bootstrap Admin Hardening

Explicit admin provisioning for production deployments.
Never auto-create admin accounts in production.
"""

import sys
from datetime import datetime, timezone
from getpass import getpass
from typing import Optional

import click
from sqlalchemy.orm import Session

from rai_gateway.core.config import settings
from rai_gateway.core.database import SessionLocal, init_db
from rai_gateway.models.database import (
    AdminCredential,
    RoleDefinition,
    UserAccount,
    UserRole,
)
from rai_gateway.services.admin_console import hash_password


def _normalize_role(role_input: str) -> str:
    """Normalize role name to role_id."""
    normalized = role_input.lower().replace(" ", "_").replace("-", "_")
    return normalized


def _ensure_rbac_roles(db: Session) -> None:
    """Ensure default RBAC roles exist."""
    default_roles = {
        "admin": {
            "name": "General Admin",
            "description": "Full system access (legacy platform bootstrap)",
            "permissions": ["*"],
        },
        "platform_admin": {
            "name": "Platform Admin",
            "description": "Internal platform administration for this instance",
            "permissions": ["*"],
        },
        "platform_support": {
            "name": "Platform Support",
            "description": "Internal support access for this instance",
            "permissions": ["platform:support"],
        },
    }

    for role_id, role_data in default_roles.items():
        existing = (
            db.query(RoleDefinition).filter(RoleDefinition.role_id == role_id).first()
        )
        if not existing:
            db.add(
                RoleDefinition(
                    role_id=role_id,
                    name=role_data["name"],
                    description=role_data["description"],
                    permissions=role_data["permissions"],
                    platform_role=True,
                )
            )
    db.commit()


def create_admin_user(
    db: Session,
    email: str,
    password: str,
    name: str,
    role: str = "platform_admin",
    user_id: Optional[str] = None,
) -> tuple[UserAccount, AdminCredential]:
    """
    Create a platform admin user with credentials.

    Args:
        db: Database session
        email: Admin email address
        password: Admin password (will be hashed)
        name: Display name
        role: Platform role (default: platform_admin)
        user_id: Optional user_id (generated from email if not provided)

    Returns:
        Tuple of (UserAccount, AdminCredential)

    Raises:
        ValueError: If email already exists or role is invalid
    """
    email = email.strip().lower()

    # Check if email already exists
    existing_cred = (
        db.query(AdminCredential).filter(AdminCredential.email == email).first()
    )
    if existing_cred:
        raise ValueError(f"Admin with email {email} already exists")

    # Generate user_id from email if not provided
    if not user_id:
        user_id = email.split("@")[0].replace(".", "_").replace("-", "_")

    # Check if user_id is taken
    existing_user = db.query(UserAccount).filter(UserAccount.user_id == user_id).first()
    if existing_user:
        # Append a number to make it unique
        counter = 1
        while (
            db.query(UserAccount)
            .filter(UserAccount.user_id == f"{user_id}_{counter}")
            .first()
        ):
            counter += 1
        user_id = f"{user_id}_{counter}"

    # Ensure RBAC roles exist
    _ensure_rbac_roles(db)

    # Normalize and validate role
    role_id = _normalize_role(role)
    role_def = (
        db.query(RoleDefinition).filter(RoleDefinition.role_id == role_id).first()
    )
    if not role_def:
        raise ValueError(
            f"Invalid role: {role}. Valid roles: admin, platform_admin, platform_support"
        )

    # Create UserAccount
    user = UserAccount(
        user_id=user_id,
        email=email,
        name=name,
        status="active",
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()

    # Create UserRole
    user_role = UserRole(
        user_id=user_id,
        role_id=role_id,
        granted_at=datetime.now(timezone.utc),
    )
    db.add(user_role)

    # Create AdminCredential
    credential = AdminCredential(
        email=email,
        user_id=user_id,
        password_hash=hash_password(password),
        is_active=True,
    )
    db.add(credential)

    db.commit()
    db.refresh(user)
    db.refresh(credential)

    return user, credential


def list_admin_users(db: Session) -> list[dict]:
    """List all admin users with their roles."""
    admins = []

    credentials = db.query(AdminCredential).all()
    for cred in credentials:
        user = db.query(UserAccount).filter(UserAccount.user_id == cred.user_id).first()
        roles = (
            db.query(UserRole, RoleDefinition)
            .join(RoleDefinition, UserRole.role_id == RoleDefinition.role_id)
            .filter(UserRole.user_id == cred.user_id)
            .all()
        )

        admins.append(
            {
                "email": cred.email,
                "user_id": cred.user_id,
                "name": user.name if user else "N/A",
                "status": user.status if user else "unknown",
                "is_active": cred.is_active,
                "roles": [r.RoleDefinition.role_id for r in roles],
                "email_verified": bool(user.email_verified_at) if user else False,
            }
        )

    return admins


def deactivate_admin_user(db: Session, email: str) -> bool:
    """
    Deactivate an admin user (soft delete).

    Returns True if deactivated, False if not found.
    """
    email = email.strip().lower()

    credential = (
        db.query(AdminCredential).filter(AdminCredential.email == email).first()
    )
    if not credential:
        return False

    credential.is_active = False

    # Also mark user as inactive
    user = (
        db.query(UserAccount).filter(UserAccount.user_id == credential.user_id).first()
    )
    if user:
        user.status = "inactive"

    db.commit()
    return True


def reset_admin_password(db: Session, email: str, new_password: str) -> bool:
    """
    Reset an admin user's password.

    Returns True if reset, False if not found.
    """
    email = email.strip().lower()

    credential = (
        db.query(AdminCredential).filter(AdminCredential.email == email).first()
    )
    if not credential:
        return False

    credential.password_hash = hash_password(new_password)
    db.commit()
    return True


# ============================================================================
# Click CLI Commands
# ============================================================================


@click.group()
def admin():
    """Admin user provisioning and management."""
    pass


@admin.command()
@click.option("--email", prompt=True, help="Admin email address")
@click.option("--name", prompt=True, help="Display name")
@click.option(
    "--role",
    default="platform_admin",
    help="Platform role (admin, platform_admin, platform_support)",
)
@click.option("--password", help="Password (will prompt if not provided)")
@click.option(
    "--user-id", help="Optional user_id (generated from email if not provided)"
)
def create(
    email: str, name: str, role: str, password: Optional[str], user_id: Optional[str]
):
    """Create a new platform admin user."""
    if not password:
        password = getpass("Password: ")
        password_confirm = getpass("Confirm password: ")
        if password != password_confirm:
            click.echo("❌ Passwords do not match", err=True)
            sys.exit(1)

    if len(password) < 8:
        click.echo("❌ Password must be at least 8 characters", err=True)
        sys.exit(1)

    try:
        init_db()
        db = SessionLocal()

        user, credential = create_admin_user(
            db, email=email, password=password, name=name, role=role, user_id=user_id
        )

        click.echo(f"✅ Created admin user: {user.email}")
        click.echo(f"   User ID: {user.user_id}")
        click.echo(f"   Name: {user.name}")
        click.echo(f"   Role: {role}")
        click.echo(f"   Status: {user.status}")

    except ValueError as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        sys.exit(1)
    finally:
        db.close()


@admin.command()
def list():
    """List all platform admin users."""
    try:
        init_db()
        db = SessionLocal()

        admins = list_admin_users(db)

        if not admins:
            click.echo("No admin users found")
            return

        click.echo(
            f"\n{'Email':<40} {'User ID':<20} {'Name':<25} {'Roles':<30} {'Active':<10}"
        )
        click.echo("=" * 125)

        for admin in admins:
            email = admin["email"]
            user_id = admin["user_id"]
            name = admin["name"][:24] if admin["name"] else "N/A"
            roles = ", ".join(admin["roles"])
            active = "✅ Yes" if admin["is_active"] else "❌ No"

            click.echo(f"{email:<40} {user_id:<20} {name:<25} {roles:<30} {active:<10}")

        click.echo(f"\nTotal: {len(admins)} admin user(s)")

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)
    finally:
        db.close()


@admin.command()
@click.option("--email", prompt=True, help="Admin email address")
@click.confirmation_option(prompt="Are you sure you want to deactivate this admin?")
def deactivate(email: str):
    """Deactivate an admin user (soft delete)."""
    try:
        init_db()
        db = SessionLocal()

        if deactivate_admin_user(db, email):
            click.echo(f"✅ Deactivated admin user: {email}")
        else:
            click.echo(f"❌ Admin user not found: {email}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)
    finally:
        db.close()


@admin.command()
@click.option("--email", prompt=True, help="Admin email address")
@click.option("--password", help="New password (will prompt if not provided)")
def reset_password(email: str, password: Optional[str]):
    """Reset an admin user's password."""
    if not password:
        password = getpass("New password: ")
        password_confirm = getpass("Confirm password: ")
        if password != password_confirm:
            click.echo("❌ Passwords do not match", err=True)
            sys.exit(1)

    if len(password) < 8:
        click.echo("❌ Password must be at least 8 characters", err=True)
        sys.exit(1)

    try:
        init_db()
        db = SessionLocal()

        if reset_admin_password(db, email, password):
            click.echo(f"✅ Reset password for admin user: {email}")
        else:
            click.echo(f"❌ Admin user not found: {email}", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)
    finally:
        db.close()


@admin.command()
def bootstrap():
    """
    Create bootstrap admin from environment configuration.

    Uses RAI_ADMIN_BOOTSTRAP_* environment variables.
    Only works if RAI_ADMIN_BOOTSTRAP_ENABLED=true.
    """
    if not settings.admin_bootstrap_enabled:
        click.echo(
            "❌ Bootstrap admin creation is disabled (RAI_ADMIN_BOOTSTRAP_ENABLED=false)",
            err=True,
        )
        click.echo(
            "\nTo create an admin user, use 'rai-admin create' instead.", err=True
        )
        sys.exit(1)

    try:
        init_db()
        db = SessionLocal()

        # Check if bootstrap admin already exists
        bootstrap_email = settings.admin_bootstrap_email.strip().lower()
        existing = (
            db.query(AdminCredential)
            .filter(AdminCredential.email == bootstrap_email)
            .first()
        )

        if existing:
            click.echo(f"ℹ️  Bootstrap admin already exists: {bootstrap_email}")
            return

        # Create bootstrap admin
        user, credential = create_admin_user(
            db,
            email=settings.admin_bootstrap_email,
            password=settings.admin_bootstrap_password,
            name=settings.admin_bootstrap_name,
            role=settings.admin_bootstrap_role,
            user_id="admin",
        )

        click.echo(f"✅ Created bootstrap admin: {user.email}")
        click.echo(f"   User ID: {user.user_id}")
        click.echo(f"   Name: {user.name}")
        click.echo(f"   Role: {settings.admin_bootstrap_role}")
        click.echo("\n⚠️  IMPORTANT: Change the bootstrap password immediately!")
        click.echo("   Use: rai-admin reset-password --email={user.email}")

    except ValueError as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    admin()

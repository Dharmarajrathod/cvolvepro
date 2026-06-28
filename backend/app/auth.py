from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import Boolean, DateTime, Integer, String, delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import Settings


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(220))
    mobile_number: Mapped[str] = mapped_column(String(32))
    country: Mapped[str] = mapped_column(String(80))
    account_type: Mapped[str] = mapped_column(String(20), default="personal")
    credits: Mapped[int] = mapped_column(Integer, default=0)
    plan_id: Mapped[str] = mapped_column(String(40), default="none")
    personal_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class EmailVerificationCode(Base):
    __tablename__ = "email_verification_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    code_hash: Mapped[str] = mapped_column(String(220))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


engine = None
SessionLocal: Optional[async_sessionmaker[AsyncSession]] = None


def configure_database(database_url: str) -> None:
    global engine, SessionLocal
    engine = create_async_engine(database_url, future=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_auth_database(database_url: str) -> None:
    if engine is None or SessionLocal is None:
        configure_database(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await ensure_user_columns(conn)


async def ensure_user_columns(conn) -> None:
    additions = {
        "account_type": "VARCHAR(20) DEFAULT 'personal'",
        "credits": "INTEGER DEFAULT 0",
        "plan_id": "VARCHAR(40) DEFAULT 'none'",
        "personal_ip": "VARCHAR(64)",
    }
    dialect = conn.engine.dialect.name
    if dialect == "sqlite":
        result = await conn.execute(text("PRAGMA table_info(users)"))
        columns = {row[1] for row in result.fetchall()}
    else:
        result = await conn.execute(text("select column_name from information_schema.columns where table_name = 'users'"))
        columns = {row[0] for row in result.fetchall()}
    for column, definition in additions.items():
        if column not in columns:
            await conn.execute(text(f"ALTER TABLE users ADD COLUMN {column} {definition}"))


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if SessionLocal is None:
        raise RuntimeError("Auth database has not been initialized.")
    return SessionLocal


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_secret(secret: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, 120_000)
    return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"


def verify_secret(secret: str, stored_hash: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored_hash.split("$", 2)
    except ValueError:
        return False
    expected = hash_secret(secret, bytes.fromhex(salt_hex)).split("$", 2)[2]
    return hmac.compare_digest(expected, digest_hex)


def public_user(user: User) -> dict[str, str]:
    return {
        "name": user.name,
        "email": user.email,
        "mobile_number": user.mobile_number,
        "country": user.country,
        "account_type": user.account_type,
        "credits": user.credits,
        "plan_id": user.plan_id,
    }


def as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def build_verification_email(settings: Settings, email: str, code: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = email
    message["Subject"] = "Your CvolvePro verification code"
    message.set_content(
        "\n".join(
            [
                "Welcome to CvolvePro.",
                "",
                f"Your verification code is {code}.",
                f"This code expires in {settings.verification_code_ttl_minutes} minutes.",
                "",
                "If you did not request this code, you can ignore this email.",
            ]
        )
    )
    return message


def send_email(settings: Settings, message: EmailMessage) -> None:
    if not settings.smtp_host or not settings.smtp_username or not settings.smtp_password:
        raise HTTPException(503, "Email delivery is not configured.")
    smtp_class = smtplib.SMTP_SSL if settings.smtp_use_ssl or settings.smtp_port == 465 else smtplib.SMTP
    with smtp_class(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if smtp_class is smtplib.SMTP:
            smtp.starttls()
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


async def send_verification_code(settings: Settings, email: str) -> None:
    normalized_email = normalize_email(email)
    code = f"{secrets.randbelow(900000) + 100000}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.verification_code_ttl_minutes)
    session_factory = get_session_factory()
    async with session_factory() as session:
        await session.execute(delete(EmailVerificationCode).where(EmailVerificationCode.email == normalized_email))
        session.add(EmailVerificationCode(email=normalized_email, code_hash=hash_secret(code), expires_at=expires_at))
        await session.commit()

    try:
        await asyncio.to_thread(send_email, settings, build_verification_email(settings, normalized_email, code))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "Could not send the verification email. Check SMTP settings and try again.") from exc


async def consume_verification_code(email: str, code: str) -> None:
    normalized_email = normalize_email(email)
    now = datetime.now(timezone.utc)
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(EmailVerificationCode)
            .where(EmailVerificationCode.email == normalized_email, EmailVerificationCode.used.is_(False))
            .order_by(EmailVerificationCode.created_at.desc())
            .limit(1)
        )
        record = result.scalar_one_or_none()
        if not record or as_aware_utc(record.expires_at) < now or not verify_secret(code.strip(), record.code_hash):
            raise HTTPException(400, "Enter a valid verification code.")
        record.used = True
        await session.commit()


async def assert_personal_ip_available(session: AsyncSession, ip: Optional[str], email: str) -> None:
    if not ip:
        return
    result = await session.execute(
        select(User).where(User.account_type == "personal", User.personal_ip == ip, User.email != email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(409, "A personal account is already active from this IP address.")


async def create_user(name: str, email: str, password: str, mobile_number: str, country: str, account_type: str, ip: Optional[str]) -> dict[str, str]:
    normalized_email = normalize_email(email)
    session_factory = get_session_factory()
    async with session_factory() as session:
        existing = await session.scalar(select(User).where(User.email == normalized_email))
        if existing:
            raise HTTPException(409, "An account already exists for this email.")
        if account_type == "personal":
            await assert_personal_ip_available(session, ip, normalized_email)
        user = User(
            name=name.strip(),
            email=normalized_email,
            password_hash=hash_secret(password),
            mobile_number=mobile_number.strip(),
            country=country.strip(),
            account_type=account_type,
            credits=0,
            plan_id="none",
            personal_ip=ip if account_type == "personal" else None,
            email_verified=True,
        )
        session.add(user)
        await session.commit()
        return public_user(user)


async def authenticate_user(email: str, password: str, ip: Optional[str]) -> dict[str, str]:
    normalized_email = normalize_email(email)
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == normalized_email))
        if not user or not verify_secret(password, user.password_hash):
            raise HTTPException(401, "Invalid email or password.")
        if user.account_type == "personal":
            await assert_personal_ip_available(session, ip, normalized_email)
            if user.personal_ip and ip and user.personal_ip != ip:
                raise HTTPException(403, "This personal account is already linked to another IP address.")
            if not user.personal_ip and ip:
                user.personal_ip = ip
                await session.commit()
        return public_user(user)


async def reset_user_password(email: str, password: str) -> dict[str, str]:
    normalized_email = normalize_email(email)
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == normalized_email))
        if not user:
            raise HTTPException(404, "No account exists for this email.")
        user.password_hash = hash_secret(password)
        await session.commit()
        return public_user(user)


async def update_user_plan(email: str, plan_id: str, credits: int) -> dict[str, str]:
    normalized_email = normalize_email(email)
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == normalized_email))
        if not user:
            raise HTTPException(404, "No account exists for this email.")
        user.plan_id = plan_id
        user.credits = credits
        await session.commit()
        return public_user(user)


async def get_public_user(email: str) -> dict[str, str]:
    normalized_email = normalize_email(email)
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == normalized_email))
        if not user:
            raise HTTPException(404, "No account exists for this email.")
        return public_user(user)


async def spend_user_credits(email: str, amount: int, action: str) -> dict[str, str]:
    normalized_email = normalize_email(email)
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == normalized_email))
        if not user:
            raise HTTPException(401, "Login is required.")
        if user.credits < amount:
            raise HTTPException(402, f"Not enough credits for {action}. Please choose a plan.")
        user.credits -= amount
        await session.commit()
        return public_user(user)


async def require_user_credits(email: str, amount: int, action: str) -> None:
    normalized_email = normalize_email(email)
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == normalized_email))
        if not user:
            raise HTTPException(401, "Login is required.")
        if user.credits < amount:
            raise HTTPException(402, f"Not enough credits for {action}. Please choose a plan.")

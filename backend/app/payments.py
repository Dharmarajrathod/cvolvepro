from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from fastapi import HTTPException

from .config import Settings


@dataclass(frozen=True)
class StripePlan:
    name: str
    amount: int
    currency: str
    credits: int
    interval_label: str


STRIPE_PLANS: dict[str, StripePlan] = {
    "classic": StripePlan("CVOLVE PRO Classic", 49_900, "inr", 50, "Monthly access"),
    "premium": StripePlan("CVOLVE PRO Premium", 69_900, "inr", 100, "Monthly access"),
    "premium_plus": StripePlan("CVOLVE PRO Premium Plus", 179_900, "inr", 350, "3 months access"),
    "business_starter": StripePlan("CVOLVE PRO Business Starter", 249_900, "inr", 500, "Monthly access"),
    "business_growth": StripePlan("CVOLVE PRO Business Growth", 649_900, "inr", 2_000, "Quarterly access"),
    "business_enterprise": StripePlan("CVOLVE PRO Business Enterprise", 2_499_900, "inr", 10_000, "Yearly access"),
}

FREE_PLAN_CREDITS = 10


def absolute_frontend_url(settings: Settings, path: str) -> str:
    return urljoin(settings.frontend_url.rstrip("/") + "/", path.lstrip("/"))


async def create_checkout_session(settings: Settings, plan_id: str, email: str | None = None) -> dict[str, str]:
    plan = STRIPE_PLANS.get(plan_id)
    if not plan:
        raise HTTPException(400, "Unknown payment plan.")
    if not settings.stripe_secret_key:
        raise HTTPException(503, "Stripe secret key is not configured.")

    form = {
        "mode": "payment",
        "success_url": absolute_frontend_url(settings, "/payment/success?session_id={CHECKOUT_SESSION_ID}"),
        "cancel_url": absolute_frontend_url(settings, "/payment/cancel"),
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": plan.currency,
        "line_items[0][price_data][unit_amount]": str(plan.amount),
        "line_items[0][price_data][product_data][name]": plan.name,
        "line_items[0][price_data][product_data][description]": f"{plan.credits} credits - {plan.interval_label}",
        "metadata[plan_id]": plan_id,
        "metadata[credits]": str(plan.credits),
    }
    if email:
        form["customer_email"] = email

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data=form,
                headers={"Authorization": f"Bearer {settings.stripe_secret_key}"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Could not connect to Stripe.") from exc

    data = response.json()
    if response.status_code >= 400:
        message = data.get("error", {}).get("message") if isinstance(data, dict) else None
        raise HTTPException(response.status_code, message or "Stripe checkout could not be created.")
    checkout_url = data.get("url")
    if not checkout_url:
        raise HTTPException(502, "Stripe did not return a checkout URL.")
    return {"url": checkout_url}


async def retrieve_checkout_session(settings: Settings, session_id: str) -> dict:
    if not settings.stripe_secret_key:
        raise HTTPException(503, "Stripe secret key is not configured.")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"https://api.stripe.com/v1/checkout/sessions/{session_id}",
                headers={"Authorization": f"Bearer {settings.stripe_secret_key}"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Could not connect to Stripe.") from exc

    data = response.json()
    if response.status_code >= 400:
        message = data.get("error", {}).get("message") if isinstance(data, dict) else None
        raise HTTPException(response.status_code, message or "Stripe checkout could not be verified.")
    return data

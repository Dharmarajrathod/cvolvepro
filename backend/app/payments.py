from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from fastapi import HTTPException, Request

from .config import Settings


@dataclass(frozen=True)
class StripePlan:
    name: str
    amount: int
    currency: str
    credits: int
    interval_label: str
    display_price: str
    period: str
    tag: str
    items: tuple[str, ...]


PLAN_LABELS = {
    "classic": ("Classic", "Best for starters", "month", ("50 credits", "10 job searches", "10 ATS matches", "2 AI interviews", "Email support")),
    "premium": ("Premium", "Best value", "month", ("100 credits", "20 job searches", "20 ATS matches", "5 AI interviews", "Priority support")),
    "premium_plus": ("Premium Plus", "Best for active search", "3 months", ("350 credits", "70 job searches", "70 ATS matches", "17 AI interviews", "Priority support")),
    "business_starter": ("Business Starter", "Best for small teams", "month", ("500 credits", "Up to 5 team members", "Shared credits", "Job Search, ATS, AI Interview")),
    "business_growth": ("Business Growth", "Best value for teams", "quarter", ("2,000 credits", "Up to 15 team members", "Shared dashboard", "Priority support")),
    "business_enterprise": ("Business Enterprise", "Best for scale", "year", ("10,000 credits", "Unlimited team members", "API and analytics", "Priority support")),
}

FREE_PLAN_CREDITS = 10
PricingRegion = str


def stripe_plan(plan_id: str, amount: int, currency: str, credits: int, interval_label: str, display_price: str) -> StripePlan:
    name, tag, period, items = PLAN_LABELS[plan_id]
    return StripePlan(f"CVOLVE PRO {name}", amount, currency, credits, interval_label, display_price, period, tag, items)


REGIONAL_STRIPE_PLANS: dict[PricingRegion, dict[str, StripePlan]] = {
    "india": {
        "classic": stripe_plan("classic", 49_900, "inr", 50, "Monthly access", "₹499"),
        "premium": stripe_plan("premium", 69_900, "inr", 100, "Monthly access", "₹699"),
        "premium_plus": stripe_plan("premium_plus", 179_900, "inr", 350, "3 months access", "₹1,799"),
        "business_starter": stripe_plan("business_starter", 249_900, "inr", 500, "Monthly access", "₹2,499"),
        "business_growth": stripe_plan("business_growth", 649_900, "inr", 2_000, "Quarterly access", "₹6,499"),
        "business_enterprise": stripe_plan("business_enterprise", 2_499_900, "inr", 10_000, "Yearly access", "₹24,999"),
    },
    "international": {
        "classic": stripe_plan("classic", 900, "usd", 50, "Monthly access", "$9"),
        "premium": stripe_plan("premium", 1_300, "usd", 100, "Monthly access", "$13"),
        "premium_plus": stripe_plan("premium_plus", 2_900, "usd", 350, "3 months access", "$29"),
        "business_starter": stripe_plan("business_starter", 4_900, "usd", 500, "Monthly access", "$49"),
        "business_growth": stripe_plan("business_growth", 12_900, "usd", 2_000, "Quarterly access", "$129"),
        "business_enterprise": stripe_plan("business_enterprise", 49_900, "usd", 10_000, "Yearly access", "$499"),
    },
}
STRIPE_PLANS = REGIONAL_STRIPE_PLANS["india"]


def request_country_code(request: Request) -> str:
    for header in ("cf-ipcountry", "x-vercel-ip-country", "x-country-code", "x-forwarded-country"):
        value = request.headers.get(header)
        if value:
            return value.strip().upper()
    return ""


def pricing_region_for_request(request: Request) -> PricingRegion:
    return "india" if request_country_code(request) == "IN" else "international"


def get_regional_plan(plan_id: str, region: PricingRegion) -> StripePlan | None:
    return REGIONAL_STRIPE_PLANS.get(region, REGIONAL_STRIPE_PLANS["international"]).get(plan_id)


def public_pricing(region: PricingRegion) -> dict:
    plans = REGIONAL_STRIPE_PLANS.get(region, REGIONAL_STRIPE_PLANS["international"])
    free_plan = {
        "id": "free",
        "name": "Free",
        "tag": "Best to try",
        "price": "₹0" if region == "india" else "$0",
        "period": "forever",
        "items": ["10 credits", "2 job searches", "2 ATS matches", "Community support"],
    }

    def serialize(plan_id: str, plan: StripePlan) -> dict:
        return {
            "id": plan_id,
            "name": plan.name.replace("CVOLVE PRO ", ""),
            "tag": plan.tag,
            "price": plan.display_price,
            "period": plan.period,
            "items": list(plan.items),
        }

    return {
        "region": region,
        "country_code": "IN" if region == "india" else None,
        "personal_plans": [
            free_plan,
            *(serialize(plan_id, plans[plan_id]) for plan_id in ("classic", "premium", "premium_plus")),
        ],
        "business_plans": [
            serialize(plan_id, plans[plan_id])
            for plan_id in ("business_starter", "business_growth", "business_enterprise")
        ],
    }


def absolute_frontend_url(settings: Settings, path: str) -> str:
    return urljoin(settings.frontend_url.rstrip("/") + "/", path.lstrip("/"))


async def create_checkout_session(settings: Settings, plan_id: str, region: PricingRegion, email: str | None = None) -> dict[str, str]:
    plan = get_regional_plan(plan_id, region)
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
        "metadata[pricing_region]": region,
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

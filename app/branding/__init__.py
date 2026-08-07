"""
The Void AI Orchestration System — White-Label Branding Layer
Version: 2.2.0 | ZQM Computing LLC

Injects customer brand identity into API responses and web UIs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class BrandProfile:
    product_name: str
    company_name: str
    support_email: str
    portal_url: str
    theme: Dict[str, str]


class BrandingLayer:
    def __init__(self) -> None:
        self.profile = BrandProfile(
            product_name=os.getenv("BRAND_PRODUCT_NAME", "The Void AI Orchestration System"),
            company_name=os.getenv("BRAND_COMPANY_NAME", os.getenv("CUSTOMER_NAME", "Customer")),
            support_email=os.getenv("BRAND_SUPPORT_EMAIL", "admin@zqmlabs.com"),
            portal_url=os.getenv("BRAND_PORTAL_URL", "http://localhost:8808/docs"),
            theme={
                "primary": os.getenv("BRAND_PRIMARY_COLOR", "#0a0e17"),
                "accent": os.getenv("BRAND_ACCENT_COLOR", "#5eead4"),
            },
        )

    def inject_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        headers["X-Product-Name"] = self.profile.product_name
        headers["X-Support-Email"] = self.profile.support_email
        return headers

    def portal_identity(self) -> Dict[str, str]:
        return {
            "product_name": self.profile.product_name,
            "company_name": self.profile.company_name,
            "support_email": self.profile.support_email,
            "portal_url": self.profile.portal_url,
        }


branding_layer = BrandingLayer()

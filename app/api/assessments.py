"""Assessment endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.report import Report
from app.core.auth import get_current_user, get_current_user_required
from app.models.user import User
from app.models.assessment import Assessment, AssessmentAnswer, AssessmentStatus
from app.models.question import Question, QuestionOption
from app.schemas.assessment import (
    AssessmentCreate,
    QuestionSchema,
    QuestionOptionSchema,
    AnswerSubmit,
    ScopeResult,
)
from app.schemas.claim import AssessmentClaimRequest, AssessmentClaimResponse
from app.schemas.saq_assessment import SaqAssessmentSync, SaqAssessmentSyncResponse
from app.services.assessment_service import AssessmentService

router = APIRouter()


def _map_saq_env(environment_type: str) -> str:
    """Map wizard env to DB assessment environment_type."""
    m = {
        "ecommerce": "ecommerce",
        "pos": "pos",
        "card_present": "pos",
        "moto": "ecommerce",
        "service_provider": "payment_platform",
        "payment_platform": "payment_platform",
    }
    return m.get(environment_type, "ecommerce")


# Registered BEFORE /{assessment_id} so "saq-sync" is not captured as an id (avoids POST -> 405).
@router.post("/saq-sync", response_model=SaqAssessmentSyncResponse)
async def sync_saq_assessment(
    data: SaqAssessmentSync,
    db: AsyncSession = Depends(get_db),
):
    """
    Create or update a guest assessment keyed by client_session_id (stored as anonymous_id).
    Call before checkout so assessment_id exists for Stripe metadata.
    """
    client_key = data.client_session_id.strip()[:64]
    env = _map_saq_env(data.environment_type.strip())

    result = await db.execute(select(Assessment).where(Assessment.anonymous_id == client_key))
    row = result.scalar_one_or_none()

    if row:
        row.environment_type = env
        row.scope_result = data.scope_result
        row.status = AssessmentStatus.COMPLETED.value
        if data.guest_email:
            row.guest_email = data.guest_email.strip().lower()[:255]
        await db.flush()
        await db.refresh(row)
        return SaqAssessmentSyncResponse(assessment_id=row.id)

    assessment = Assessment(
        user_id=None,
        framework="pci_dss",
        environment_type=env,
        status=AssessmentStatus.COMPLETED.value,
        scope_result=data.scope_result,
        anonymous_id=client_key,
        guest_email=data.guest_email.strip().lower()[:255] if data.guest_email else None,
    )
    db.add(assessment)
    await db.flush()
    await db.refresh(assessment)
    return SaqAssessmentSyncResponse(assessment_id=assessment.id)


# Phase 6: Full question trees. Ecommerce: 35 questions (ids 1-35); POS: 35 (ids 10-44)
ECOMMERCE_QUESTIONS = [
    # Section 1: Platform Architecture
    {"id": 1, "question_key": "ecom_q1", "question_text": "What type of ecommerce platform do you use?", "question_type": "single_choice", "category": "Platform Architecture", "help_text": None, "options": [{"value": "shopify", "label": "Shopify"}, {"value": "magento", "label": "Magento"}, {"value": "woocommerce", "label": "WooCommerce"}, {"value": "custom", "label": "Custom platform"}, {"value": "other", "label": "Other"}]},
    {"id": 2, "question_key": "ecom_q2", "question_text": "Where is your website hosted?", "question_type": "single_choice", "category": "Platform Architecture", "help_text": None, "options": [{"value": "cloud", "label": "Cloud hosting"}, {"value": "platform", "label": "Platform provider"}, {"value": "on_premise", "label": "On-premise"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 3, "question_key": "ecom_q3", "question_text": "Who manages your website infrastructure?", "question_type": "single_choice", "category": "Platform Architecture", "help_text": None, "options": [{"value": "internal", "label": "Internal team"}, {"value": "hosting", "label": "Hosting provider"}, {"value": "vendor", "label": "Platform vendor"}, {"value": "agency", "label": "Third-party agency"}]},
    # Section 2: Payment Flow
    {"id": 4, "question_key": "ecom_q4", "question_text": "How do customers enter card details?", "question_type": "single_choice", "category": "Payment Flow", "help_text": "This determines whether card data touches your systems.", "options": [{"value": "redirect", "label": "Redirect to payment provider page"}, {"value": "embedded", "label": "Embedded payment form"}, {"value": "iframe", "label": "Payment iframe"}, {"value": "merchant_hosted", "label": "Merchant hosted payment form"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 5, "question_key": "ecom_q5", "question_text": "Does your website ever receive raw card data?", "question_type": "single_choice", "category": "Payment Flow", "help_text": None, "options": [{"value": "no", "label": "No"}, {"value": "yes", "label": "Yes"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 6, "question_key": "ecom_q6", "question_text": "Does your backend server process payment requests?", "question_type": "single_choice", "category": "Payment Flow", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 7, "question_key": "ecom_q7", "question_text": "Does your system store full card numbers (PAN)?", "question_type": "single_choice", "category": "Payment Flow", "help_text": None, "options": [{"value": "no", "label": "No"}, {"value": "yes", "label": "Yes"}, {"value": "tokenized", "label": "Tokenized only"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 8, "question_key": "ecom_q8", "question_text": "Does your system store card data after authorization?", "question_type": "single_choice", "category": "Payment Flow", "help_text": None, "options": [{"value": "no", "label": "No"}, {"value": "yes_temporarily", "label": "Yes temporarily"}, {"value": "yes_permanently", "label": "Yes permanently"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section 3: Payment Providers
    {"id": 9, "question_key": "ecom_q9", "question_text": "Which payment processor do you use?", "question_type": "single_choice", "category": "Payment Providers", "help_text": None, "options": [{"value": "stripe", "label": "Stripe"}, {"value": "adyen", "label": "Adyen"}, {"value": "braintree", "label": "Braintree"}, {"value": "paypal", "label": "PayPal"}, {"value": "multiple", "label": "Multiple"}, {"value": "other", "label": "Other"}]},
    {"id": 10, "question_key": "ecom_q10", "question_text": "Is the payment page hosted by the payment provider?", "question_type": "single_choice", "category": "Payment Providers", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section 4: Security Controls
    {"id": 11, "question_key": "ecom_q11", "question_text": "Does your website load payment scripts from third parties?", "question_type": "single_choice", "category": "Security Controls", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 12, "question_key": "ecom_q12", "question_text": "Are payment page scripts integrity-checked?", "question_type": "single_choice", "category": "Security Controls", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 13, "question_key": "ecom_q13", "question_text": "Is web application firewall (WAF) used?", "question_type": "single_choice", "category": "Security Controls", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section 5: Access Control
    {"id": 14, "question_key": "ecom_q14", "question_text": "Do administrators use unique accounts?", "question_type": "single_choice", "category": "Access Control", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
    {"id": 15, "question_key": "ecom_q15", "question_text": "Is multi-factor authentication enabled?", "question_type": "single_choice", "category": "Access Control", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section 6: Logging & Monitoring
    {"id": 16, "question_key": "ecom_q16", "question_text": "Are website access logs monitored?", "question_type": "single_choice", "category": "Logging & Monitoring", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 17, "question_key": "ecom_q17", "question_text": "Are vulnerability scans performed?", "question_type": "single_choice", "category": "Logging & Monitoring", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 18, "question_key": "ecom_q18", "question_text": "Is penetration testing performed annually?", "question_type": "single_choice", "category": "Logging & Monitoring", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section 7: Data Security
    {"id": 19, "question_key": "ecom_q19", "question_text": "Is tokenization used for stored payment references?", "question_type": "single_choice", "category": "Data Security", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 20, "question_key": "ecom_q20", "question_text": "Is TLS used for all checkout pages?", "question_type": "single_choice", "category": "Data Security", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section 8: Recurring & Saved Cards
    {"id": 21, "question_key": "ecom_q21", "question_text": "Do you handle recurring billing or saved cards?", "question_type": "single_choice", "category": "Recurring Payments", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
    {"id": 22, "question_key": "ecom_q22", "question_text": "Where are payment tokens stored for recurring payments?", "question_type": "single_choice", "category": "Recurring Payments", "help_text": None, "options": [{"value": "processor", "label": "At payment processor"}, {"value": "merchant", "label": "In our systems"}, {"value": "both", "label": "Both"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section 9: Third-Party Integrations
    {"id": 23, "question_key": "ecom_q23", "question_text": "Do you use third-party payment widgets or plugins?", "question_type": "single_choice", "category": "Third-Party Integrations", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 24, "question_key": "ecom_q24", "question_text": "Are third-party integrations PCI compliant?", "question_type": "single_choice", "category": "Third-Party Integrations", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section 10: Checkout Page
    {"id": 25, "question_key": "ecom_q25", "question_text": "Who renders the page where card data is entered?", "question_type": "single_choice", "category": "Checkout Page", "help_text": None, "options": [{"value": "processor", "label": "Payment processor (redirect)"}, {"value": "merchant", "label": "Our servers"}, {"value": "embedded", "label": "Our page with embedded processor fields"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 26, "question_key": "ecom_q26", "question_text": "Can your website influence the payment form (e.g., styling, layout)?", "question_type": "single_choice", "category": "Checkout Page", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section 11: Incident Response
    {"id": 27, "question_key": "ecom_q27", "question_text": "Do you have an incident response plan?", "question_type": "single_choice", "category": "Incident Response", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 28, "question_key": "ecom_q28", "question_text": "Are security policies documented and reviewed?", "question_type": "single_choice", "category": "Incident Response", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section 12: Compliance
    {"id": 29, "question_key": "ecom_q29", "question_text": "Have you completed a PCI assessment in the past 12 months?", "question_type": "single_choice", "category": "Compliance", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 30, "question_key": "ecom_q30", "question_text": "What SAQ did you last complete (if applicable)?", "question_type": "single_choice", "category": "Compliance", "help_text": None, "options": [{"value": "saq_a", "label": "SAQ A"}, {"value": "saq_a_ep", "label": "SAQ A-EP"}, {"value": "saq_d", "label": "SAQ D"}, {"value": "roc", "label": "ROC"}, {"value": "none", "label": "None / Not applicable"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section 13: Sub-merchant / Marketplace
    {"id": 31, "question_key": "ecom_q31", "question_text": "Do you operate as a marketplace or platform with sub-merchants?", "question_type": "single_choice", "category": "Marketplace", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
    {"id": 32, "question_key": "ecom_q32", "question_text": "Does card data flow through your systems to sub-merchants?", "question_type": "single_choice", "category": "Marketplace", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section 14: CDN & Caching
    {"id": 33, "question_key": "ecom_q33", "question_text": "Is your checkout page cached by CDN or edge servers?", "question_type": "single_choice", "category": "Infrastructure", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 34, "question_key": "ecom_q34", "question_text": "Are payment-related API keys stored securely?", "question_type": "single_choice", "category": "Infrastructure", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 35, "question_key": "ecom_q35", "question_text": "Do you use a secure vault or HSM for sensitive data?", "question_type": "single_choice", "category": "Infrastructure", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "na", "label": "Not applicable"}, {"value": "not_sure", "label": "Not sure"}]},
]
# POS questionnaire: 35-question PCI DSS scoping (ids 10-44)
# Scope engine keys: terminal_type(10), locations(11), network_segmentation(25), terminal_connectivity(26), p2pe(20)
POS_QUESTIONS = [
    # Section 1: POS Environment
    {"id": 10, "question_key": "terminal_type", "question_text": "What type of POS system do you use?", "question_type": "single_choice", "category": "POS Environment", "help_text": None, "options": [{"value": "standalone", "label": "Standalone payment terminal"}, {"value": "integrated", "label": "Integrated POS system"}, {"value": "mobile", "label": "Mobile POS (tablet or smartphone)"}, {"value": "self_checkout", "label": "Self-checkout kiosk"}, {"value": "mixed", "label": "Mixed environment"}]},
    {"id": 11, "question_key": "locations", "question_text": "How many POS terminals are deployed?", "question_type": "single_choice", "category": "POS Environment", "help_text": None, "options": [{"value": "1", "label": "1–5"}, {"value": "2_10", "label": "6–20"}, {"value": "11_plus", "label": "21–100 or more"}]},
    {"id": 12, "question_key": "pos_q3", "question_text": "Who provides the POS terminals?", "question_type": "single_choice", "category": "POS Environment", "help_text": None, "options": [{"value": "processor", "label": "Payment processor"}, {"value": "vendor", "label": "POS vendor"}, {"value": "merchant", "label": "Purchased by merchant"}, {"value": "leased", "label": "Leased equipment"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 13, "question_key": "pos_q4", "question_text": "Do POS terminals run a general-purpose operating system?", "question_type": "single_choice", "category": "POS Environment", "help_text": None, "options": [{"value": "no", "label": "No"}, {"value": "windows", "label": "Yes – Windows"}, {"value": "linux", "label": "Yes – Linux"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 14, "question_key": "pos_q5", "question_text": "Do you use unattended POS devices such as kiosks or vending systems?", "question_type": "single_choice", "category": "POS Environment", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
    # Section 2: Card Data Handling
    {"id": 15, "question_key": "pos_q6", "question_text": "How are cards accepted at the POS?", "question_type": "single_choice", "category": "Card Data Handling", "help_text": None, "options": [{"value": "chip", "label": "Chip (EMV)"}, {"value": "tap", "label": "Tap (NFC / contactless)"}, {"value": "magstripe", "label": "Magstripe"}, {"value": "manual", "label": "Manual entry"}, {"value": "all", "label": "All of the above"}]},
    {"id": 16, "question_key": "pos_q7", "question_text": "Does your POS system store full card numbers (PAN)?", "question_type": "single_choice", "category": "Card Data Handling", "help_text": None, "options": [{"value": "no", "label": "No"}, {"value": "yes", "label": "Yes"}, {"value": "tokenized", "label": "Tokenized only"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 17, "question_key": "pos_q8", "question_text": "Does your POS system store card data after authorization?", "question_type": "single_choice", "category": "Card Data Handling", "help_text": None, "options": [{"value": "no", "label": "No"}, {"value": "temporarily", "label": "Temporarily"}, {"value": "permanently", "label": "Yes permanently"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 18, "question_key": "pos_q9", "question_text": "Are printed receipts configured to mask card numbers?", "question_type": "single_choice", "category": "Card Data Handling", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 19, "question_key": "pos_q10", "question_text": "Can employees manually enter card numbers into the POS system?", "question_type": "single_choice", "category": "Card Data Handling", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
    # Section 3: Encryption and P2PE
    {"id": 20, "question_key": "p2pe", "question_text": "Do your terminals use a PCI-listed P2PE solution?", "question_type": "single_choice", "category": "Encryption and P2PE", "help_text": None, "options": [{"value": "p2pe_validated", "label": "Yes – PCI validated P2PE"}, {"value": "p2pe_encryption", "label": "Yes – encryption but not PCI validated"}, {"value": "no", "label": "No"}, {"value": "unsure", "label": "Not sure"}]},
    {"id": 21, "question_key": "pos_q12", "question_text": "Is card data encrypted immediately at the terminal during card capture?", "question_type": "single_choice", "category": "Encryption and P2PE", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 22, "question_key": "pos_q13", "question_text": "Is cardholder data decrypted within your environment?", "question_type": "single_choice", "category": "Encryption and P2PE", "help_text": None, "options": [{"value": "no", "label": "No"}, {"value": "yes", "label": "Yes"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 23, "question_key": "pos_q14", "question_text": "Does your POS software perform payment processing directly?", "question_type": "single_choice", "category": "Encryption and P2PE", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "processor", "label": "No – handled by payment processor"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 24, "question_key": "pos_q15", "question_text": "Is tokenization used for storing payment references?", "question_type": "single_choice", "category": "Encryption and P2PE", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section 4: Network Architecture
    {"id": 25, "question_key": "network_segmentation", "question_text": "Are POS terminals connected to a dedicated payment network?", "question_type": "single_choice", "category": "Network Architecture", "help_text": None, "options": [{"value": "yes_full", "label": "Yes – fully segmented network"}, {"value": "yes_partial", "label": "Partially segmented"}, {"value": "no_shared", "label": "No – shared network"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 26, "question_key": "terminal_connectivity", "question_text": "Do POS terminals connect directly to the payment processor?", "question_type": "single_choice", "category": "Network Architecture", "help_text": None, "options": [{"value": "internet_direct", "label": "Yes"}, {"value": "vpn", "label": "No – through POS server"}, {"value": "internet_gateway", "label": "No – through gateway"}, {"value": "internet_unsure", "label": "Not sure"}]},
    {"id": 27, "question_key": "pos_q18", "question_text": "Are firewalls used to protect the POS network?", "question_type": "single_choice", "category": "Network Architecture", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 28, "question_key": "pos_q19", "question_text": "Are wireless networks used for POS connectivity?", "question_type": "single_choice", "category": "Network Architecture", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
    {"id": 29, "question_key": "pos_q20", "question_text": "If wireless is used, is it secured using WPA2/WPA3 encryption?", "question_type": "single_choice", "category": "Network Architecture", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section 5: Authentication and Access
    {"id": 30, "question_key": "pos_q21", "question_text": "Do employees log into POS systems using unique user IDs?", "question_type": "single_choice", "category": "Authentication and Access", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 31, "question_key": "pos_q22", "question_text": "Are default passwords changed on POS devices?", "question_type": "single_choice", "category": "Authentication and Access", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 32, "question_key": "pos_q23", "question_text": "Are administrative accounts restricted to authorized personnel only?", "question_type": "single_choice", "category": "Authentication and Access", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 33, "question_key": "pos_q24", "question_text": "Is multi-factor authentication used for POS administration access?", "question_type": "single_choice", "category": "Authentication and Access", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 34, "question_key": "pos_q25", "question_text": "Are inactive POS user accounts disabled or removed regularly?", "question_type": "single_choice", "category": "Authentication and Access", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section 6: Logging and Monitoring
    {"id": 35, "question_key": "pos_q26", "question_text": "Are POS system activities logged and monitored?", "question_type": "single_choice", "category": "Logging and Monitoring", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 36, "question_key": "pos_q27", "question_text": "Are security logs reviewed regularly?", "question_type": "single_choice", "category": "Logging and Monitoring", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 37, "question_key": "pos_q28", "question_text": "Do POS devices receive regular software or firmware updates?", "question_type": "single_choice", "category": "Logging and Monitoring", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 38, "question_key": "pos_q29", "question_text": "Are antivirus or endpoint protection tools installed on POS systems (if applicable)?", "question_type": "single_choice", "category": "Logging and Monitoring", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "na", "label": "Not applicable"}]},
    {"id": 39, "question_key": "pos_q30", "question_text": "Are vulnerability scans performed on POS systems or networks?", "question_type": "single_choice", "category": "Logging and Monitoring", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section 7: Vendor and Remote Access
    {"id": 40, "question_key": "pos_q31", "question_text": "Does your POS vendor remotely access systems for support?", "question_type": "single_choice", "category": "Vendor and Remote Access", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
    {"id": 41, "question_key": "pos_q32", "question_text": "Is vendor remote access restricted and monitored?", "question_type": "single_choice", "category": "Vendor and Remote Access", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 42, "question_key": "pos_q33", "question_text": "Are vendor access credentials rotated regularly?", "question_type": "single_choice", "category": "Vendor and Remote Access", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 43, "question_key": "pos_q34", "question_text": "Is vendor access disabled when not actively needed?", "question_type": "single_choice", "category": "Vendor and Remote Access", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 44, "question_key": "pos_q35", "question_text": "Is your POS vendor listed as PCI DSS compliant by the PCI Security Standards Council?", "question_type": "single_choice", "category": "Vendor and Remote Access", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
]
# Payment Platform questionnaire: 30 questions (ids 50-79)
PLATFORM_QUESTIONS = [
    # Section: Platform Overview
    {"id": 50, "question_key": "psp_q1", "question_text": "What type of payment platform do you operate?", "question_type": "single_choice", "category": "Platform Overview", "help_text": None, "options": [{"value": "gateway", "label": "Payment gateway"}, {"value": "processor", "label": "Payment processor"}, {"value": "facilitator", "label": "Payment facilitator"}, {"value": "marketplace", "label": "Marketplace platform"}, {"value": "fintech", "label": "Fintech payment application"}, {"value": "other", "label": "Other"}]},
    {"id": 51, "question_key": "psp_q2", "question_text": "Does your platform receive cardholder data from merchants?", "question_type": "single_choice", "category": "Platform Overview", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 52, "question_key": "psp_q3", "question_text": "Does your system store cardholder data?", "question_type": "single_choice", "category": "Platform Overview", "help_text": None, "options": [{"value": "no", "label": "No"}, {"value": "yes_encrypted", "label": "Yes encrypted"}, {"value": "yes_unencrypted", "label": "Yes unencrypted"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 53, "question_key": "psp_q4", "question_text": "Does your system decrypt cardholder data?", "question_type": "single_choice", "category": "Platform Overview", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 54, "question_key": "psp_q5", "question_text": "Does your platform tokenize card data?", "question_type": "single_choice", "category": "Platform Overview", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section: Architecture
    {"id": 55, "question_key": "psp_q6", "question_text": "Where is your platform hosted?", "question_type": "single_choice", "category": "Architecture", "help_text": None, "options": [{"value": "aws", "label": "AWS"}, {"value": "azure", "label": "Azure"}, {"value": "gcp", "label": "Google Cloud"}, {"value": "private", "label": "Private infrastructure"}, {"value": "hybrid", "label": "Hybrid"}]},
    {"id": 56, "question_key": "psp_q7", "question_text": "Do merchants connect to your platform through APIs?", "question_type": "single_choice", "category": "Architecture", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
    {"id": 57, "question_key": "psp_q8", "question_text": "Do you provide payment SDKs or libraries?", "question_type": "single_choice", "category": "Architecture", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
    {"id": 58, "question_key": "psp_q9", "question_text": "Does your platform process payment authorization requests?", "question_type": "single_choice", "category": "Architecture", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section: Card Data Protection
    {"id": 59, "question_key": "psp_q10", "question_text": "Is cardholder data encrypted in transit?", "question_type": "single_choice", "category": "Card Data Protection", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 60, "question_key": "psp_q11", "question_text": "Is cardholder data encrypted at rest?", "question_type": "single_choice", "category": "Card Data Protection", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 61, "question_key": "psp_q12", "question_text": "Is encryption key management handled internally?", "question_type": "single_choice", "category": "Card Data Protection", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "external_hsm", "label": "External HSM"}]},
    {"id": 62, "question_key": "psp_q13", "question_text": "Do you maintain tokenized card references?", "question_type": "single_choice", "category": "Card Data Protection", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section: Network Architecture
    {"id": 63, "question_key": "psp_q14", "question_text": "Is the cardholder data environment segmented from other networks?", "question_type": "single_choice", "category": "Network Architecture", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 64, "question_key": "psp_q15", "question_text": "Are firewalls deployed to protect the CDE?", "question_type": "single_choice", "category": "Network Architecture", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
    {"id": 65, "question_key": "psp_q16", "question_text": "Are intrusion detection or prevention systems deployed?", "question_type": "single_choice", "category": "Network Architecture", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
    {"id": 66, "question_key": "psp_q17", "question_text": "Is production infrastructure separated from development environments?", "question_type": "single_choice", "category": "Network Architecture", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section: Access Control
    {"id": 67, "question_key": "psp_q18", "question_text": "Do administrators use unique user IDs?", "question_type": "single_choice", "category": "Access Control", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
    {"id": 68, "question_key": "psp_q19", "question_text": "Is multi-factor authentication required for administrative access?", "question_type": "single_choice", "category": "Access Control", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
    {"id": 69, "question_key": "psp_q20", "question_text": "Are privileged accounts regularly reviewed?", "question_type": "single_choice", "category": "Access Control", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section: Monitoring and Testing
    {"id": 70, "question_key": "psp_q21", "question_text": "Are system logs centrally collected and monitored?", "question_type": "single_choice", "category": "Monitoring and Testing", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
    {"id": 71, "question_key": "psp_q22", "question_text": "Are vulnerability scans performed quarterly?", "question_type": "single_choice", "category": "Monitoring and Testing", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 72, "question_key": "psp_q23", "question_text": "Is penetration testing performed annually?", "question_type": "single_choice", "category": "Monitoring and Testing", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 73, "question_key": "psp_q24", "question_text": "Is file integrity monitoring deployed?", "question_type": "single_choice", "category": "Monitoring and Testing", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    # Section: Vendor and Infrastructure Security
    {"id": 74, "question_key": "psp_q25", "question_text": "Do third-party vendors have remote access to your environment?", "question_type": "single_choice", "category": "Vendor and Infrastructure Security", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
    {"id": 75, "question_key": "psp_q26", "question_text": "Is vendor access restricted and monitored?", "question_type": "single_choice", "category": "Vendor and Infrastructure Security", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 76, "question_key": "psp_q27", "question_text": "Is remote access disabled when not required?", "question_type": "single_choice", "category": "Vendor and Infrastructure Security", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 77, "question_key": "psp_q28", "question_text": "Do infrastructure providers manage any security controls?", "question_type": "single_choice", "category": "Vendor and Infrastructure Security", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "not_sure", "label": "Not sure"}]},
    {"id": 78, "question_key": "psp_q29", "question_text": "Do you maintain formal security policies?", "question_type": "single_choice", "category": "Vendor and Infrastructure Security", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
    {"id": 79, "question_key": "psp_q30", "question_text": "Is PCI DSS compliance currently validated by an external assessor?", "question_type": "single_choice", "category": "Vendor and Infrastructure Security", "help_text": None, "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}, {"value": "in_progress", "label": "In progress"}]},
]
QUESTIONS_BY_ENV = {"ecommerce": ECOMMERCE_QUESTIONS, "pos": POS_QUESTIONS, "payment_platform": PLATFORM_QUESTIONS}


@router.post("", status_code=201)
async def create_assessment(
    data: AssessmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
):
    """Create new assessment. Auth optional - anonymous users can start, sign up to save."""
    assessment = await AssessmentService.create(
        db, data.environment_type, user=current_user
    )
    response = {"id": assessment.id, "environment_type": assessment.environment_type}
    if assessment.anonymous_id:
        response["anonymous_id"] = assessment.anonymous_id
    return response


@router.post("/claim", response_model=AssessmentClaimResponse)
async def claim_assessment(
    data: AssessmentClaimRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Claim an anonymous assessment. Requires authentication."""
    assessment = await AssessmentService.claim(
        db, data.assessment_id, data.token, current_user
    )
    return AssessmentClaimResponse(assessment_id=assessment.id)


@router.get("/{assessment_id}/questions")
async def get_questions(
    assessment_id: int,
    db: AsyncSession = Depends(get_db),
):
    assessment = await AssessmentService.get_or_404(db, assessment_id)
    questions = QUESTIONS_BY_ENV.get(assessment.environment_type, ECOMMERCE_QUESTIONS)
    return {
        "questions": [
            QuestionSchema(
                id=q["id"],
                question_key=q["question_key"],
                question_text=q["question_text"],
                question_type=q["question_type"],
                category=q["category"],
                help_text=q.get("help_text"),
                options=[QuestionOptionSchema(**o) for o in q.get("options", [])],
            )
            for q in questions
        ]
    }


@router.post("/{assessment_id}/answer")
async def submit_answer(
    assessment_id: int,
    answer: AnswerSubmit,
    db: AsyncSession = Depends(get_db),
):
    assessment = await AssessmentService.get_or_404(db, assessment_id)
    existing = await db.execute(
        select(AssessmentAnswer).where(
            AssessmentAnswer.assessment_id == assessment_id,
            AssessmentAnswer.question_id == answer.question_id,
        )
    )
    ans = existing.scalar_one_or_none()
    if ans:
        ans.answer_value = answer.answer_value
    else:
        ans = AssessmentAnswer(
            assessment_id=assessment_id,
            question_id=answer.question_id,
            answer_value=answer.answer_value,
        )
        db.add(ans)
    await db.flush()
    return {"ok": True}


@router.post("/{assessment_id}/complete")
async def complete_assessment(
    assessment_id: int,
    db: AsyncSession = Depends(get_db),
):
    assessment = await AssessmentService.get_or_404(db, assessment_id)
    scope = await AssessmentService.complete(db, assessment)
    return {"scope_result": scope}


@router.get("/{assessment_id}")
async def get_assessment(
    assessment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
):
    """Get assessment. When authenticated, includes is_owned, anonymous_id, and report info for purchase flow."""
    assessment = await AssessmentService.get_or_404(db, assessment_id)
    out = {
        "id": assessment.id,
        "environment_type": assessment.environment_type,
        "status": assessment.status,
        "scope_result": assessment.scope_result,
    }
    if assessment.anonymous_id:
        out["anonymous_id"] = assessment.anonymous_id
    if current_user:
        out["is_owned"] = assessment.user_id == current_user.id
        # Include report info when user has purchased a report for this assessment
        report_result = await db.execute(
            select(Report).where(
                Report.assessment_id == assessment_id,
                Report.user_id == current_user.id,
            )
        )
        report = report_result.scalar_one_or_none()
        if report:
            out["report_id"] = report.id
            out["report_status"] = report.status
    return out

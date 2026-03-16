"""Assessment business logic: create, claim, complete."""
import uuid
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.assessment import Assessment, AssessmentAnswer, AssessmentStatus
from app.models.user import User
from app.schemas.assessment import ScopeResult
from app.services.scope_service import ScopeService
from app.core.exceptions import NotFoundError, ValidationError, ClaimExpiredError, ClaimAlreadyUsedError


# Question key mapping for Phase 6 question trees (id -> key)
# Ecommerce: 1-35; POS: 10-44 (35 questions); Payment platform: 50-54
QUESTION_KEY_MAP = {
    1: "ecom_q1",
    2: "ecom_q2",
    3: "ecom_q3",
    4: "ecom_q4",
    5: "ecom_q5",
    6: "ecom_q6",
    7: "ecom_q7",
    8: "ecom_q8",
    9: "ecom_q9",
    10: "ecom_q10",
    11: "ecom_q11",
    12: "ecom_q12",
    13: "ecom_q13",
    14: "ecom_q14",
    15: "ecom_q15",
    16: "ecom_q16",
    17: "ecom_q17",
    18: "ecom_q18",
    19: "ecom_q19",
    20: "ecom_q20",
    21: "ecom_q21",
    22: "ecom_q22",
    23: "ecom_q23",
    24: "ecom_q24",
    25: "ecom_q25",
    26: "ecom_q26",
    27: "ecom_q27",
    28: "ecom_q28",
    29: "ecom_q29",
    30: "ecom_q30",
    31: "ecom_q31",
    32: "ecom_q32",
    33: "ecom_q33",
    34: "ecom_q34",
    35: "ecom_q35",
    10: "terminal_type",
    11: "locations",
    12: "pos_q3",
    13: "pos_q4",
    14: "pos_q5",
    15: "pos_q6",
    16: "pos_q7",
    17: "pos_q8",
    18: "pos_q9",
    19: "pos_q10",
    20: "p2pe",
    21: "pos_q12",
    22: "pos_q13",
    23: "pos_q14",
    24: "pos_q15",
    25: "network_segmentation",
    26: "terminal_connectivity",
    27: "pos_q18",
    28: "pos_q19",
    29: "pos_q20",
    30: "pos_q21",
    31: "pos_q22",
    32: "pos_q23",
    33: "pos_q24",
    34: "pos_q25",
    35: "pos_q26",
    36: "pos_q27",
    37: "pos_q28",
    38: "pos_q29",
    39: "pos_q30",
    40: "pos_q31",
    41: "pos_q32",
    42: "pos_q33",
    43: "pos_q34",
    44: "pos_q35",
    50: "psp_q1",
    51: "psp_q2",
    52: "psp_q3",
    53: "psp_q4",
    54: "psp_q5",
    55: "psp_q6",
    56: "psp_q7",
    57: "psp_q8",
    58: "psp_q9",
    59: "psp_q10",
    60: "psp_q11",
    61: "psp_q12",
    62: "psp_q13",
    63: "psp_q14",
    64: "psp_q15",
    65: "psp_q16",
    66: "psp_q17",
    67: "psp_q18",
    68: "psp_q19",
    69: "psp_q20",
    70: "psp_q21",
    71: "psp_q22",
    72: "psp_q23",
    73: "psp_q24",
    74: "psp_q25",
    75: "psp_q26",
    76: "psp_q27",
    77: "psp_q28",
    78: "psp_q29",
    79: "psp_q30",
}


class AssessmentService:
    """Assessment creation, completion, and claim logic."""

    @staticmethod
    async def create(
        db: AsyncSession,
        environment_type: str,
        user: User | None = None,
        organization_id: int | None = None,
    ) -> Assessment:
        """Create a new assessment. Anonymous if user is None."""
        anonymous_id = str(uuid.uuid4()) if user is None else None
        assessment = Assessment(
            user_id=user.id if user else None,
            organization_id=organization_id,
            environment_type=environment_type,
            anonymous_id=anonymous_id,
            status=AssessmentStatus.IN_PROGRESS.value,
        )
        db.add(assessment)
        await db.flush()
        await db.refresh(assessment)
        return assessment

    @staticmethod
    async def get_or_404(db: AsyncSession, assessment_id: int) -> Assessment:
        """Get assessment or raise 404."""
        result = await db.execute(select(Assessment).where(Assessment.id == assessment_id))
        assessment = result.scalar_one_or_none()
        if not assessment:
            raise NotFoundError("Assessment", assessment_id)
        return assessment

    @staticmethod
    async def get_answers_by_question_key(
        db: AsyncSession,
        assessment_id: int,
        question_id_to_key: dict[int, str],
    ) -> dict[str, str]:
        """Load answers and map to question_key for scope computation."""
        result = await db.execute(
            select(AssessmentAnswer).where(AssessmentAnswer.assessment_id == assessment_id)
        )
        answers_list = result.scalars().all()
        answers_dict = {a.question_id: a.answer_value for a in answers_list}
        return {
            question_id_to_key.get(aid, str(aid)): v
            for aid, v in answers_dict.items()
        }

    @staticmethod
    async def complete(db: AsyncSession, assessment: Assessment) -> ScopeResult:
        """Complete assessment and compute scope result."""
        question_id_to_key = QUESTION_KEY_MAP
        answers = await AssessmentService.get_answers_by_question_key(
            db, assessment.id, question_id_to_key
        )
        scope = ScopeService.compute_scope(assessment.environment_type, answers)
        assessment.scope_result = scope.model_dump()
        assessment.status = AssessmentStatus.COMPLETED.value
        await db.flush()
        return scope

    @staticmethod
    async def claim(
        db: AsyncSession,
        assessment_id: int,
        claim_token: str,
        user: User,
    ) -> Assessment:
        """
        Claim an anonymous assessment. Token is stored in assessment.anonymous_id
        for MVP; in production use assessment_claims table.
        """
        assessment = await AssessmentService.get_or_404(db, assessment_id)
        if assessment.user_id is not None:
            raise ClaimAlreadyUsedError()
        if assessment.anonymous_id != claim_token:
            raise ValidationError("Invalid claim token")
        assessment.user_id = user.id
        assessment.anonymous_id = None  # Consume token
        assessment.claimed_at = datetime.utcnow()
        await db.flush()
        return assessment

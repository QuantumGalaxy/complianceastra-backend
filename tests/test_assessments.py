"""
Technical test cases: Assessment flow (A-1 through A-6)
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_a1_create_assessment(client: AsyncClient):
    """A-1: Create assessment returns 201 with id and environment_type."""
    response = await client.post(
        "/api/assessments",
        json={"environment_type": "ecommerce"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["environment_type"] == "ecommerce"


@pytest.mark.asyncio
async def test_a2_get_questions(client: AsyncClient):
    """A-2: GET questions returns 200 with question list."""
    create = await client.post(
        "/api/assessments",
        json={"environment_type": "ecommerce"},
    )
    aid = create.json()["id"]
    response = await client.get(f"/api/assessments/{aid}/questions")
    assert response.status_code == 200
    data = response.json()
    assert "questions" in data
    assert len(data["questions"]) >= 1


@pytest.mark.asyncio
async def test_a3_submit_answer(client: AsyncClient):
    """A-3: Submit answer returns 200."""
    create = await client.post(
        "/api/assessments",
        json={"environment_type": "ecommerce"},
    )
    aid = create.json()["id"]
    questions = await client.get(f"/api/assessments/{aid}/questions")
    qid = questions.json()["questions"][0]["id"]
    response = await client.post(
        f"/api/assessments/{aid}/answer",
        json={"question_id": qid, "answer_value": "redirect"},
    )
    assert response.status_code == 200
    assert response.json().get("ok") is True


@pytest.mark.asyncio
async def test_a4_complete_assessment(client: AsyncClient):
    """A-4: Complete assessment returns 200 with scope_result."""
    create = await client.post(
        "/api/assessments",
        json={"environment_type": "ecommerce"},
    )
    aid = create.json()["id"]
    questions = await client.get(f"/api/assessments/{aid}/questions")
    for q in questions.json()["questions"]:
        val = q["options"][0]["value"] if q.get("options") else "no"
        await client.post(
            f"/api/assessments/{aid}/answer",
            json={"question_id": q["id"], "answer_value": val},
        )
    response = await client.post(f"/api/assessments/{aid}/complete")
    assert response.status_code == 200
    data = response.json()
    assert "scope_result" in data
    assert "summary" in data["scope_result"]
    assert "scope_level" in data["scope_result"]


@pytest.mark.asyncio
async def test_a5_get_assessment_after_complete(client: AsyncClient):
    """A-6: GET assessment after complete returns status completed."""
    create = await client.post(
        "/api/assessments",
        json={"environment_type": "ecommerce"},
    )
    aid = create.json()["id"]
    questions = await client.get(f"/api/assessments/{aid}/questions")
    for q in questions.json()["questions"]:
        val = q["options"][0]["value"] if q.get("options") else "no"
        await client.post(
            f"/api/assessments/{aid}/answer",
            json={"question_id": q["id"], "answer_value": val},
        )
    await client.post(f"/api/assessments/{aid}/complete")
    response = await client.get(f"/api/assessments/{aid}")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"

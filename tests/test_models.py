"""Unit tests for Pydantic models."""
import pytest
from pydantic import ValidationError


def test_agent_type_enum():
    """AgentType enum should accept valid values."""
    from app.models.agent import AgentType
    assert AgentType.NLP == "nlp"
    assert AgentType.REASONING == "reasoning"
    assert AgentType.SYNTHESIS == "synthesis"


def test_agent_creation():
    """Agent model should validate required fields."""
    from app.models.agent import Agent
    a = Agent(id="agent-001", name="Test Agent", type="nlp", status="idle")
    assert a.id == "agent-001"
    assert a.type.value == "nlp"


def test_agent_missing_id():
    """Agent model should reject missing id."""
    from app.models.agent import Agent
    with pytest.raises(ValidationError):
        Agent(name="Test", type="nlp", status="idle")


def test_agent_invalid_type():
    """Agent model should reject invalid type."""
    from app.models.agent import Agent
    with pytest.raises(ValidationError):
        Agent(id="a1", name="Test", type="invalid_type", status="idle")


def test_response_model():
    """ZQM_AIResponse model should validate structure."""
    from app.models.response import ZQM_AIResponse
    r = ZQM_AIResponse(status="success", data={"key": "value"})
    assert r.status == "success"
    assert r.data["key"] == "value"


def test_health_status_model():
    """HealthStatus model should validate structure."""
    from app.models.response import HealthStatus
    h = HealthStatus(status="healthy", version="2.0.0")
    assert h.status == "healthy"
    assert h.version == "2.0.0"

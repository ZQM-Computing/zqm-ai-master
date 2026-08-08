"""Unit tests for Pydantic models."""
import pytest
from pydantic import ValidationError


def test_agent_type_enum():
    """AgentType enum should accept valid values."""
    from app.models.agent import AgentType
    assert AgentType.NLP == "nlp"
    assert AgentType.REASONING == "reasoning"
    assert AgentType.SYNTHESIS == "synthesis"
    assert AgentType.QUANTUM == "quantum"
    assert AgentType.GARDEN == "garden"


def test_agent_creation():
    """Agent model should validate required fields."""
    from app.models.agent import Agent, AgentStatus
    a = Agent(
        agent_id="agent-001",
        name="Test Agent",
        agent_type="nlp",
        status=AgentStatus.IDLE,
    )
    assert a.agent_id == "agent-001"
    assert a.agent_type.value == "nlp"
    assert a.status == AgentStatus.IDLE
    assert a.is_available is True


def test_agent_missing_agent_id():
    """Agent model should reject missing agent_id."""
    from app.models.agent import Agent
    with pytest.raises(ValidationError):
        Agent(name="Test", agent_type="nlp")


def test_agent_invalid_type():
    """Agent model should reject invalid agent_type."""
    from app.models.agent import Agent
    with pytest.raises(ValidationError):
        Agent(agent_id="a1", name="Test", agent_type="invalid_type")


def test_response_model():
    """ZQM_AIResponse model should validate structure."""
    from app.models.response import ZQM_AIResponse
    r = ZQM_AIResponse(success=True, data={"key": "value"})
    assert r.success is True
    assert r.data["key"] == "value"


def test_health_status_model():
    """HealthStatus model should validate structure."""
    from app.models.response import HealthStatus
    h = HealthStatus(status="healthy", version="2.0.0")
    assert h.status == "healthy"
    assert h.version == "2.0.0"

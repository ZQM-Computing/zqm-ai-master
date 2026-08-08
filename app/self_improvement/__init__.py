"""Self-improvement package."""
from app.self_improvement.ab_testing import ABTest, ABTestResult
from app.self_improvement.feedback import collect_feedback, summarize_feedback
from app.self_improvement.regression import PerformanceRegressionDetector
from app.self_improvement.training_data_generation import (
    generate_training_data_from_feedback,
)
from app.self_improvement.triggers import AutomaticFineTuningTrigger

__all__ = [
    "ABTest",
    "ABTestResult",
    "AutomaticFineTuningTrigger",
    "PerformanceRegressionDetector",
    "collect_feedback",
    "generate_training_data_from_feedback",
    "summarize_feedback",
]

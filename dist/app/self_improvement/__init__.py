"""Self-improvement package."""
from app.self_improvement.feedback import collect_feedback, summarize_feedback
from app.self_improvement.training_data_generation import generate_training_data_from_feedback
from app.self_improvement.ab_testing import ABTest, ABTestResult
from app.self_improvement.triggers import AutomaticFineTuningTrigger
from app.self_improvement.regression import PerformanceRegressionDetector

__all__ = [
    "collect_feedback",
    "summarize_feedback",
    "generate_training_data_from_feedback",
    "ABTest",
    "ABTestResult",
    "AutomaticFineTuningTrigger",
    "PerformanceRegressionDetector",
]

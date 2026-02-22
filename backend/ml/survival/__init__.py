"""
Survival Analysis Module - Cox Proportional Hazards for equipment failure prediction.

Provides:
- SurvivalDataPrep: Prepare survival datasets with censoring
- SurvivalModel: Cox PH model implementation
- SurvivalTrainer: Training pipeline with model registration
"""

from .data_prep import SurvivalDataPrep
from .model import SurvivalModel
from .train import SurvivalTrainer

__all__ = ["SurvivalDataPrep", "SurvivalModel", "SurvivalTrainer"]

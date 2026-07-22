"""Prompt templates for the BuilderDNA LLM layer."""

from llm.prompts.trend import build_trend_prompt
from llm.prompts.pain import build_pain_cluster_naming_prompt
from llm.prompts.opportunity import build_opportunity_prompt, build_critic_prompt

__all__ = [
    "build_trend_prompt",
    "build_pain_cluster_naming_prompt",
    "build_opportunity_prompt",
    "build_critic_prompt",
]

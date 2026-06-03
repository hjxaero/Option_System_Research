"""Pure option-chain construction and query interfaces."""

from option_platform.option_chain.builder import build_option_chain
from option_platform.option_chain.chain import OptionChain
from option_platform.option_chain.strategy_candidates import (
    build_strategy_candidate_quality_report,
    build_strategy_candidates,
    prepare_strategy_candidates_for_storage,
)

__all__ = [
    "OptionChain",
    "build_option_chain",
    "build_strategy_candidate_quality_report",
    "build_strategy_candidates",
    "prepare_strategy_candidates_for_storage",
]

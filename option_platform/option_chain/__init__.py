"""Pure option-chain construction and query interfaces."""

from option_platform.option_chain.builder import build_option_chain
from option_platform.option_chain.chain import OptionChain

__all__ = ["OptionChain", "build_option_chain"]

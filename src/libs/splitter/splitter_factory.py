"""Factory for creating splitter instances."""

from typing import Dict, Type
from . import BaseSplitter, SplitterSettings
from .recursive_splitter import RecursiveCharacterSplitter


class SplitterFactory:
    """Factory class for creating Splitter instances.
    
    Provides centralized creation of splitters based on configuration,
    supporting multiple splitting strategies and extensibility through
    the register_strategy method.
    """

    _strategies: Dict[str, Type[BaseSplitter]] = {
        "recursive": RecursiveCharacterSplitter,
    }

    @classmethod
    def create(cls, settings: SplitterSettings) -> BaseSplitter:
        """Create a splitter instance based on the strategy in settings.
        
        Args:
            settings: SplitterSettings with desired strategy
            
        Returns:
            Configured splitter instance
            
        Raises:
            ValueError: If the specified strategy is not supported
        """
        strategy_name = settings.strategy.lower()
        strategy_cls = cls._strategies.get(strategy_name)

        if not strategy_cls:
            available = ", ".join(cls._strategies.keys())
            raise ValueError(
                f"Unsupported splitting strategy: {strategy_name}. "
                f"Available strategies: {available}"
            )

        return strategy_cls(settings)

    @classmethod
    def register_strategy(cls, name: str, strategy_cls: Type[BaseSplitter]):
        """Register a custom splitter strategy.
        
        Args:
            name: Name identifier for the strategy (case-insensitive)
            strategy_cls: Class implementing BaseSplitter interface
            
        Example:
            class CustomSplitter(BaseSplitter):
                def split(self, text, source, metadata=None):
                    ...
            
            SplitterFactory.register_strategy("custom", CustomSplitter)
            settings = SplitterSettings(strategy="custom", chunk_size=500)
            splitter = SplitterFactory.create(settings)
        """
        cls._strategies[name.lower()] = strategy_cls

    @classmethod
    def list_strategies(cls) -> list[str]:
        """List all available splitting strategies.
        
        Returns:
            Sorted list of strategy names
        """
        return sorted(cls._strategies.keys())

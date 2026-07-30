"""Public-data source adapters."""

from sourcevahti.adapters.eurostat import EurostatAdapter
from sourcevahti.adapters.finnish_cancer_registry import FinnishCancerRegistryAdapter
from sourcevahti.adapters.nordcan import NordcanAdapter
from sourcevahti.adapters.who_gho import WhoGhoAdapter

__all__ = [
    "EurostatAdapter",
    "FinnishCancerRegistryAdapter",
    "NordcanAdapter",
    "WhoGhoAdapter",
]

from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseAdapter(ABC):
    @abstractmethod
    def fetch(self, **kwargs) -> List[Dict[str, Any]]:
        """Fetch raw data from the source."""
        pass
        
    @abstractmethod
    def normalize(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Normalize raw data into the standard document mapping."""
        pass

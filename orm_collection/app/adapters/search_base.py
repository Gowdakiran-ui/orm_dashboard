from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Optional

class BaseSearchAdapter(ABC):
    @abstractmethod
    def search(self, keyword: str, cursor: Optional[str] = None, **kwargs) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Executes a search using the keyword and optional cursor.
        Returns a tuple: (list of raw results, new_cursor_value)
        """
        pass
        
    @abstractmethod
    def normalize(self, raw_data: Dict[str, Any], source_id: str, **kwargs) -> Dict[str, Any]:
        """
        Normalizes a single raw search result into the standard document mapping.
        """
        pass

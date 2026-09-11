"""Base interface for Text-to-Speech engines."""

from abc import ABC, abstractmethod
from typing import List, Tuple
import numpy as np


class BaseTTSEngine(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the engine."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Checks if the engine is ready and models are present."""
        pass

    @abstractmethod
    def get_available_voices(self) -> List[str]:
        """Returns list of voice identifiers supported by this engine."""
        pass

    @abstractmethod
    def synthesize(self, text: str, voice: str, speed: float) -> Tuple[np.ndarray, int]:
        """
        Synthesizes text into audio.
        Returns: (numpy_audio_samples_float32, sample_rate)
        """
        pass

"""LLM setup using GPT4ALL for local model"""

import os
from typing import Optional

from langchain_community.llms import GPT4All


class LLMProvider:
    """GPT4All-backed LLM for local inference."""

    def __init__(
        self, model_path: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 2048
    ) -> None:
        """Load model from model_path (or MODEL_PATH env); raise if file missing."""
        if model_path is None:
            model_path = os.getenv("MODEL_PATH", "local_models/Meta-Llama-3-8B-Instruct.Q4_0.gguf")
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found at: {model_path}")
        self.model_path = model_path
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.llm = None
        self._initialize_llm()

    def _initialize_llm(self):
        try:
            self.llm = GPT4All(
                model=self.model_path,
                verbose=False,
                n_predict=self.max_tokens,
                temp=self.temperature,
            )
            if hasattr(self.llm, "n_ctx"):
                self.llm.n_ctx = self.max_tokens
            if hasattr(self.llm, "temperature"):
                self.llm.temperature = self.temperature
        except Exception:
            self.llm = GPT4All(
                model=self.model_path,
                verbose=False,
                n_predict=self.max_tokens,
                temp=self.temperature,
            )

    def get_llm(self):
        """Return the underlying LangChain LLM instance."""
        return self.llm

    def generate(self, prompt: str, stop: Optional[list] = None) -> str:
        """Run the model on the prompt; return generated text."""
        return self.llm(prompt, stop=stop)

    def __call__(self, prompt: str, stop: Optional[list] = None) -> str:
        """Same as generate(prompt, stop)."""
        return self.generate(prompt, stop=stop)

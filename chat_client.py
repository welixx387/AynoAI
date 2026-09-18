# chat_client.py
# Тонкая обёртка над локальным Ollama API (http://localhost:11434).
# Ollama не требует API-ключей — она просто крутит модель у тебя на компьютере.

import json
from typing import Dict, Iterator, List

import requests


class OllamaClient:
    """Клиент для общения с локальным сервером Ollama через его REST API."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.1:8b"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def is_available(self) -> bool:
        """Проверяет, отвечает ли Ollama вообще (сервис запущен и слушает порт)."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return resp.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def list_models(self) -> List[str]:
        """Возвращает список моделей, уже загруженных через `ollama pull`."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            return [item["name"] for item in data.get("models", [])]
        except requests.exceptions.RequestException:
            return []

    def chat_stream(self, messages: List[Dict[str, str]], temperature: float = 0.8) -> Iterator[str]:
        """
        Отправляет историю диалога в Ollama и возвращает генератор кусочков ответа
        (стриминг) — это то, что st.write_stream() умеет печатать "по мере поступления".

        messages: список вида [{"role": "system"|"user"|"assistant", "content": "..."}]
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature},
        }

        try:
            with requests.post(
                f"{self.base_url}/api/chat", json=payload, stream=True, timeout=120
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line.decode("utf-8"))
                    if chunk.get("done"):
                        break
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content

        except requests.exceptions.ConnectionError:
            yield (
                "\n\n⚠️ Не удалось подключиться к Ollama на "
                f"`{self.base_url}`. Убедись, что Ollama запущена "
                "(команда `ollama serve` или открытое приложение Ollama)."
            )
        except requests.exceptions.HTTPError as e:
            yield (
                f"\n\n⚠️ Ollama вернула ошибку: {e}. "
                f"Возможно, модель `{self.model}` не загружена — "
                f"выполни `ollama pull {self.model}`."
            )
        except requests.exceptions.RequestException as e:
            yield f"\n\n⚠️ Ошибка запроса к Ollama: {e}"

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.8) -> str:
        """Нестриминговая версия — просто дожидается полного ответа и возвращает строку."""
        return "".join(self.chat_stream(messages, temperature))

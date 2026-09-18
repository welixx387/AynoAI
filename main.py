# main.py
# Полноценный веб-сайт на FastAPI: раздаёт фронтенд из папки static/ и
# предоставляет API, которое общается с Ollama и хранит историю диалогов
# в SQLite (chat_history.db).
#
# Запуск (из папки проекта):
#   uvicorn main:app --host 0.0.0.0 --port 8000
#
# --host 0.0.0.0 нужен, чтобы сайт был доступен не только с этого компьютера,
# но и с телефона/другого устройства в той же локальной сети.

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
from chat_client import OllamaClient
from personality import (
    CRISIS_RESPONSE,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    PERSONA_NAME,
    SYSTEM_PROMPT,
    contains_crisis_signal,
)

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title=PERSONA_NAME)
client = OllamaClient(model=DEFAULT_MODEL)

db.init_db()


class NewConversation(BaseModel):
    title: str = "Новый диалог"


class RenameConversation(BaseModel):
    title: str


class NewMessage(BaseModel):
    content: str
    model: Optional[str] = None
    temperature: float = DEFAULT_TEMPERATURE


def _make_title(text: str, limit: int = 40) -> str:
    text = " ".join(text.strip().split())
    return text[:limit] + ("…" if len(text) > limit else "")


# --- Статус и список моделей ---

@app.get("/api/status")
def api_status():
    return {
        "persona": PERSONA_NAME,
        "ollama_available": client.is_available(),
        "default_model": DEFAULT_MODEL,
    }


@app.get("/api/models")
def api_models():
    return {"models": client.list_models()}


# --- Диалоги ---

@app.get("/api/conversations")
def api_list_conversations():
    return db.list_conversations()


@app.post("/api/conversations")
def api_create_conversation(payload: NewConversation):
    return db.create_conversation(payload.title)


@app.get("/api/conversations/{conv_id}")
def api_get_conversation(conv_id: int):
    conv = db.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Диалог не найден")
    conv["messages"] = db.get_messages(conv_id)
    return conv


@app.patch("/api/conversations/{conv_id}")
def api_rename_conversation(conv_id: int, payload: RenameConversation):
    if not db.get_conversation(conv_id):
        raise HTTPException(status_code=404, detail="Диалог не найден")
    db.rename_conversation(conv_id, payload.title)
    return {"ok": True}


@app.delete("/api/conversations/{conv_id}")
def api_delete_conversation(conv_id: int):
    if not db.get_conversation(conv_id):
        raise HTTPException(status_code=404, detail="Диалог не найден")
    db.delete_conversation(conv_id)
    return {"ok": True}


# --- Сообщения (стриминг ответа модели) ---

@app.post("/api/conversations/{conv_id}/messages")
def api_send_message(conv_id: int, payload: NewMessage):
    conv = db.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Диалог не найден")

    user_text = payload.content.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="Пустое сообщение")

    db.add_message(conv_id, "user", user_text)

    # Если это первое сообщение в диалоге — используем его как заголовок
    history = db.get_messages(conv_id)
    if len(history) == 1:
        db.rename_conversation(conv_id, _make_title(user_text))

    if contains_crisis_signal(user_text):
        db.add_message(conv_id, "assistant", CRISIS_RESPONSE)

        def crisis_stream():
            yield CRISIS_RESPONSE

        return StreamingResponse(crisis_stream(), media_type="text/plain; charset=utf-8")

    if payload.model:
        client.model = payload.model

    api_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + [
        {"role": m["role"], "content": m["content"]} for m in history
    ]

    def generate():
        full_response = ""
        for chunk in client.chat_stream(api_messages, payload.temperature):
            full_response += chunk
            yield chunk
        db.add_message(conv_id, "assistant", full_response)

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


# Раздаём фронтенд (index.html, style.css, app.js) как статику.
# Должно быть смонтировано ПОСЛЕ всех /api/... маршрутов.
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

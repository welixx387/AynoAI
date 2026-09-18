# app.py
# Веб-интерфейс чат-бота на Streamlit.
# Запуск: streamlit run app.py

import streamlit as st

from chat_client import OllamaClient
from personality import (
    CRISIS_RESPONSE,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    PERSONA_NAME,
    SYSTEM_PROMPT,
    contains_crisis_signal,
)

st.set_page_config(page_title=PERSONA_NAME, page_icon="🎭", layout="centered")

# --- Инициализация состояния сессии (сохраняется, пока открыта вкладка браузера) ---
if "messages" not in st.session_state:
    # Храним только user/assistant-сообщения. Системный промт добавляем отдельно
    # при каждом запросе, чтобы его не было видно в истории на экране.
    st.session_state.messages = []

if "client" not in st.session_state:
    st.session_state.client = OllamaClient(model=DEFAULT_MODEL)

client: OllamaClient = st.session_state.client

# --- Боковая панель: настройки ---
with st.sidebar:
    st.header("⚙️ Настройки")

    available_models = client.list_models()
    if available_models:
        default_index = (
            available_models.index(DEFAULT_MODEL) if DEFAULT_MODEL in available_models else 0
        )
        selected_model = st.selectbox("Модель", available_models, index=default_index)
    else:
        st.warning(
            "Ollama не отвечает или ни одна модель не загружена.\n\n"
            "Проверь, что сервис Ollama запущен и выполнена команда "
            f"`ollama pull {DEFAULT_MODEL}`."
        )
        selected_model = st.text_input("Модель (ввести вручную)", value=DEFAULT_MODEL)

    client.model = selected_model

    temperature = st.slider(
        "Температура (креативность ответов)", min_value=0.0, max_value=1.5,
        value=DEFAULT_TEMPERATURE, step=0.05,
    )

    st.divider()
    if st.button("🗑️ Очистить историю диалога"):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    status_text = "🟢 подключена" if client.is_available() else "🔴 недоступна"
    st.caption(f"Статус Ollama: {status_text}")
    st.caption(f"Адрес: {client.base_url}")

# --- Основной экран ---
st.title(f"🎭 {PERSONA_NAME}")
st.caption(
    "Ролевой ИИ-чат-бот с настраиваемой личностью. Работает полностью локально "
    "через Ollama — без API-ключей и без отправки данных в интернет."
)

# Отрисовываем всю накопленную историю диалога
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Поле ввода внизу экрана
user_input = st.chat_input("Напиши сообщение...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    if contains_crisis_signal(user_input):
        # Защитный слой: при признаках кризиса не идём к модели вообще,
        # а сразу показываем заранее подготовленный ответ с реальной помощью.
        with st.chat_message("assistant"):
            st.markdown(CRISIS_RESPONSE)
        st.session_state.messages.append({"role": "assistant", "content": CRISIS_RESPONSE})
    else:
        # Системный промт добавляется первым сообщением, но не сохраняется
        # в session_state.messages — иначе он бы отображался на экране.
        api_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + st.session_state.messages

        with st.chat_message("assistant"):
            full_response = st.write_stream(client.chat_stream(api_messages, temperature))

        st.session_state.messages.append({"role": "assistant", "content": full_response})

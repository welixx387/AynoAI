// app.js — логика фронтенда: диалоги, стриминг ответов, настройки.
// Никаких внешних библиотек — чистый JS, чтобы не тянуть Node.js/сборку.

const messagesEl = document.getElementById("messages");
const emptyStateEl = document.getElementById("empty-state");
const conversationListEl = document.getElementById("conversation-list");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");
const newChatBtn = document.getElementById("new-chat-btn");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");

const sidebar = document.getElementById("sidebar");
const sidebarOverlay = document.getElementById("sidebar-overlay");
const menuToggle = document.getElementById("menu-toggle");
const sidebarClose = document.getElementById("sidebar-close");

const settingsBtn = document.getElementById("settings-btn");
const settingsPanel = document.getElementById("settings-panel");
const settingsClose = document.getElementById("settings-close");
const modelSelect = document.getElementById("model-select");
const tempSlider = document.getElementById("temp-slider");
const tempValue = document.getElementById("temp-value");

let conversations = [];
let currentConversationId = null;
let selectedModel = null;
let temperature = 0.8;
let isStreaming = false;

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail || `Ошибка запроса: ${response.status}`);
  }
  return response.json();
}

// --- Статус подключения к Ollama ---

async function loadStatus() {
  try {
    const status = await api("/api/status");
    statusDot.className = "status-dot " + (status.ollama_available ? "online" : "offline");
    statusText.textContent = status.ollama_available
      ? "Ollama подключена"
      : "Ollama недоступна — проверь, что сервис запущен";
  } catch {
    statusDot.className = "status-dot offline";
    statusText.textContent = "Сервер недоступен";
  }
}

// --- Модели ---

async function loadModels() {
  try {
    const data = await api("/api/models");
    modelSelect.innerHTML = "";
    if (!data.models || data.models.length === 0) {
      const opt = document.createElement("option");
      opt.textContent = "нет загруженных моделей";
      modelSelect.appendChild(opt);
      return;
    }
    data.models.forEach((name) => {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      modelSelect.appendChild(opt);
    });
    selectedModel = data.models[0];
    modelSelect.value = selectedModel;
  } catch {
    // тихо игнорируем — статус-бар уже покажет, что Ollama недоступна
  }
}

modelSelect.addEventListener("change", () => {
  selectedModel = modelSelect.value;
});

tempSlider.addEventListener("input", () => {
  temperature = parseFloat(tempSlider.value);
  tempValue.textContent = temperature.toFixed(2);
});

// --- Список диалогов ---

async function loadConversations() {
  conversations = await api("/api/conversations");
  renderConversationList();
}

function renderConversationList() {
  conversationListEl.innerHTML = "";
  conversations.forEach((conv) => {
    const item = document.createElement("div");
    item.className = "conversation-item" + (conv.id === currentConversationId ? " active" : "");

    const title = document.createElement("span");
    title.className = "title";
    title.textContent = conv.title || "Новый диалог";
    item.appendChild(title);

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "delete-btn";
    deleteBtn.textContent = "✕";
    deleteBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteConversation(conv.id);
    });
    item.appendChild(deleteBtn);

    item.addEventListener("click", () => selectConversation(conv.id));
    conversationListEl.appendChild(item);
  });
}

async function selectConversation(id) {
  currentConversationId = id;
  renderConversationList();
  closeSidebarOnMobile();

  const conv = await api(`/api/conversations/${id}`);
  renderMessages(conv.messages);
}

async function createNewConversation() {
  const conv = await api("/api/conversations", {
    method: "POST",
    body: JSON.stringify({ title: "Новый диалог" }),
  });
  conversations.unshift(conv);
  currentConversationId = conv.id;
  renderConversationList();
  renderMessages([]);
  closeSidebarOnMobile();
  chatInput.focus();
}

async function deleteConversation(id) {
  if (!confirm("Удалить этот диалог без возможности восстановления?")) return;
  await api(`/api/conversations/${id}`, { method: "DELETE" });
  conversations = conversations.filter((c) => c.id !== id);
  if (currentConversationId === id) {
    currentConversationId = null;
    renderMessages([]);
  }
  renderConversationList();
}

newChatBtn.addEventListener("click", createNewConversation);

// --- Рендер сообщений ---

function renderMessages(messages) {
  messagesEl.innerHTML = "";
  if (!messages || messages.length === 0) {
    messagesEl.appendChild(emptyStateEl);
    return;
  }
  messages.forEach((m) => appendMessageBubble(m.role, m.content));
  scrollToBottom();
}

function appendMessageBubble(role, content) {
  if (emptyStateEl.parentElement === messagesEl) {
    messagesEl.removeChild(emptyStateEl);
  }
  const row = document.createElement("div");
  row.className = "message-row " + role;

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = content;

  row.appendChild(bubble);
  messagesEl.appendChild(row);
  return bubble;
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// --- Отправка сообщения и стриминг ответа ---

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text || isStreaming) return;

  chatInput.value = "";
  chatInput.style.height = "auto";
  await sendMessage(text);
});

chatInput.addEventListener("input", () => {
  chatInput.style.height = "auto";
  chatInput.style.height = Math.min(chatInput.scrollHeight, 160) + "px";
});

chatInput.addEventListener("keydown", (e) => {
  const isEnter = e.key === "Enter" || e.code === "Enter" || e.keyCode === 13;
  if (isEnter && !e.shiftKey) {
    e.preventDefault();
    chatForm.requestSubmit();
  }
});

async function sendMessage(text) {
  isStreaming = true;
  sendBtn.disabled = true;

  if (!currentConversationId) {
    const conv = await api("/api/conversations", {
      method: "POST",
      body: JSON.stringify({ title: "Новый диалог" }),
    });
    currentConversationId = conv.id;
    conversations.unshift(conv);
    renderConversationList();
  }

  appendMessageBubble("user", text);
  scrollToBottom();

  const assistantBubble = appendMessageBubble("assistant", "");
  assistantBubble.classList.add("streaming");
  scrollToBottom();

  try {
    const response = await fetch(`/api/conversations/${currentConversationId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: text, model: selectedModel, temperature }),
    });

    if (!response.ok || !response.body) {
      const detail = await response.json().catch(() => ({}));
      assistantBubble.textContent = detail.detail || "Ошибка запроса к серверу.";
    } else {
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let full = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        full += decoder.decode(value, { stream: true });
        assistantBubble.textContent = full;
        scrollToBottom();
      }
    }
  } catch (err) {
    assistantBubble.textContent = "⚠️ Не удалось получить ответ: " + err.message;
  } finally {
    assistantBubble.classList.remove("streaming");
    isStreaming = false;
    sendBtn.disabled = false;
  }

  // Обновляем список диалогов — могло смениться авто-название
  loadConversations();
}

// --- Сайдбар (мобильная версия) ---

function openSidebar() {
  sidebar.classList.add("open");
  sidebarOverlay.classList.add("open");
}

function closeSidebar() {
  sidebar.classList.remove("open");
  sidebarOverlay.classList.remove("open");
}

function closeSidebarOnMobile() {
  if (window.innerWidth <= 768) closeSidebar();
}

menuToggle.addEventListener("click", openSidebar);
sidebarClose.addEventListener("click", closeSidebar);
sidebarOverlay.addEventListener("click", closeSidebar);

// --- Настройки ---

settingsBtn.addEventListener("click", () => settingsPanel.classList.remove("hidden"));
settingsClose.addEventListener("click", () => settingsPanel.classList.add("hidden"));
settingsPanel.addEventListener("click", (e) => {
  if (e.target === settingsPanel) settingsPanel.classList.add("hidden");
});

// --- Инициализация ---

(async function init() {
  await Promise.all([loadStatus(), loadModels(), loadConversations()]);
  if (conversations.length > 0) {
    await selectConversation(conversations[0].id);
  }
  setInterval(loadStatus, 15000);
})();

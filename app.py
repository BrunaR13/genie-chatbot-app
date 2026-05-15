from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional, Any
from contextlib import asynccontextmanager
import os

from server.genie import list_genie_spaces, ask_genie, get_current_user
from server.database import (
    init_database,
    get_user_conversations,
    create_conversation,
    update_conversation,
    get_conversation,
    add_message,
    delete_conversation
)

# Import settings
from settings import APP_NAME, APP_DESCRIPTION, BRAND_COLORS, MAX_TABLE_ROWS, MAX_CHART_ROWS, POWERED_BY


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("App started. Database will be initialized on first user request.")
    yield


app = FastAPI(title=APP_NAME, lifespan=lifespan)


def get_user_token(request: Request) -> Optional[str]:
    """Extract user OAuth token from request headers."""
    return request.headers.get("x-forwarded-access-token")


class ChatRequest(BaseModel):
    space_id: str
    question: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    status: str
    question: str
    sql: Optional[str] = None
    description: Optional[str] = None
    columns: list[str] = []
    data: list = []
    row_count: int = 0
    text_response: Optional[str] = None
    error: Optional[str] = None


class GenieSpace(BaseModel):
    space_id: str
    title: str
    description: Optional[str] = None


class UserInfo(BaseModel):
    email: str
    name: Optional[str] = None


@app.get("/api/me", response_model=UserInfo)
async def get_me(request: Request):
    try:
        user_token = get_user_token(request)
        user = get_current_user(user_token)
        return UserInfo(**user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/genies", response_model=list[GenieSpace])
async def get_genies(request: Request):
    try:
        user_token = get_user_token(request)
        spaces = list_genie_spaces(user_token)
        return spaces
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: Request, chat_request: ChatRequest):
    try:
        user_token = get_user_token(request)
        result = ask_genie(
            space_id=chat_request.space_id,
            question=chat_request.question,
            conversation_id=chat_request.conversation_id,
            user_token=user_token
        )
        return ChatResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ Database Initialization ============
_db_initialized = False


@app.post("/api/init-db")
async def initialize_database(request: Request):
    global _db_initialized
    try:
        user_token = get_user_token(request)
        init_database(user_token)
        _db_initialized = True
        return {"success": True, "message": "Database initialized successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def ensure_db_initialized(user_token: str):
    global _db_initialized
    if not _db_initialized:
        try:
            init_database(user_token)
            _db_initialized = True
        except Exception as e:
            print(f"Warning: Could not initialize database: {e}")


# ============ Conversation History APIs ============
class ConversationCreate(BaseModel):
    key: str
    space_id: str
    title: str


class ConversationUpdate(BaseModel):
    genie_conversation_id: Optional[str] = None
    title: Optional[str] = None


class MessageCreate(BaseModel):
    conversation_key: str
    message_type: str
    content: Optional[str] = None
    data: Optional[dict] = None


class ConversationResponse(BaseModel):
    key: str
    genie_conversation_id: Optional[str] = None
    space_id: str
    title: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    messages: Optional[list] = None


@app.get("/api/conversations", response_model=list[ConversationResponse])
async def list_conversations(request: Request):
    try:
        user_token = get_user_token(request)
        await ensure_db_initialized(user_token)
        user = get_current_user(user_token)
        conversations = get_user_conversations(user["email"], user_token)
        return conversations
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/conversations", response_model=ConversationResponse)
async def create_new_conversation(request: Request, conv: ConversationCreate):
    try:
        user_token = get_user_token(request)
        user = get_current_user(user_token)
        result = create_conversation(user["email"], conv.key, conv.space_id, conv.title, user_token)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/conversations/{key}", response_model=ConversationResponse)
async def get_conversation_details(key: str, request: Request):
    try:
        user_token = get_user_token(request)
        conv = get_conversation(key, user_token)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conv
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/conversations/{key}")
async def update_conversation_details(key: str, update: ConversationUpdate, request: Request):
    try:
        user_token = get_user_token(request)
        update_conversation(key, update.genie_conversation_id, update.title, user_token)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/conversations/{key}")
async def delete_conversation_endpoint(key: str, request: Request):
    try:
        user_token = get_user_token(request)
        user = get_current_user(user_token)
        deleted = delete_conversation(key, user["email"], user_token)
        if not deleted:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/messages")
async def add_message_endpoint(msg: MessageCreate, request: Request):
    try:
        user_token = get_user_token(request)
        add_message(msg.conversation_key, msg.message_type, msg.content, msg.data, user_token)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ Frontend HTML ============
def get_frontend_html():
    """Generate frontend HTML with settings applied."""
    # Build powered by badge
    powered_by_badge = ""
    if POWERED_BY:
        powered_by_badge = f'''<div class="flex items-center gap-2 px-3 py-1.5 bg-brand-light rounded-full">
                        <span class="text-xs font-medium text-brand-primary">Powered by</span>
                        <span class="text-xs font-bold text-brand-secondary">{POWERED_BY}</span>
                    </div>'''

    # HTML template with placeholders (regular string, not f-string)
    html = '''<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{APP_NAME}}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <script>
        const APP_NAME = "{{APP_NAME}}";
        const MAX_TABLE_ROWS = {{MAX_TABLE_ROWS}};
        const MAX_CHART_ROWS = {{MAX_CHART_ROWS}};
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        brand: {
                            primary: '{{BRAND_PRIMARY}}',
                            secondary: '{{BRAND_SECONDARY}}',
                            accent: '{{BRAND_ACCENT}}',
                            background: '{{BRAND_BACKGROUND}}',
                            light: '{{BRAND_LIGHT}}'
                        }
                    },
                    fontFamily: { sans: ['Inter', 'sans-serif'] }
                }
            }
        }
    </script>
    <style>
        body { font-family: 'Inter', sans-serif; }
        @keyframes sparkle { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.5; transform: scale(1.2); } }
        .sparkle { animation: sparkle 2s ease-in-out infinite; }
        .sparkle-delay-1 { animation-delay: 0.3s; }
        .sparkle-delay-2 { animation-delay: 0.6s; }
        @keyframes pulse-glow { 0%, 100% { box-shadow: 0 0 5px rgba(66, 108, 169, 0.3); } 50% { box-shadow: 0 0 20px rgba(66, 108, 169, 0.6); } }
        .loading-glow { animation: pulse-glow 1.5s ease-in-out infinite; }
        @keyframes bounce { 0%, 80%, 100% { transform: translateY(0); } 40% { transform: translateY(-6px); } }
        .typing-dot { animation: bounce 1.4s ease-in-out infinite; }
        .typing-dot:nth-child(2) { animation-delay: 0.2s; }
        .typing-dot:nth-child(3) { animation-delay: 0.4s; }
        .message-user { background: linear-gradient(135deg, #002855 0%, #426ca9 100%); color: white; border-radius: 20px 20px 4px 20px; }
        .message-genie { background: white; border: 1px solid #e5e7eb; border-radius: 20px 20px 20px 4px; box-shadow: 0 2px 8px rgba(0, 40, 85, 0.08); }
        .conversation-item { transition: all 0.2s ease; border-left: 3px solid transparent; }
        .conversation-item:hover { background-color: #e8f0f8; border-left-color: #426ca9; }
        .conversation-item.active { background-color: #e8f0f8; border-left-color: #002855; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: #f5f5f5; }
        ::-webkit-scrollbar-thumb { background: #426ca9; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #002855; }
        .data-table { border-collapse: separate; border-spacing: 0; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0, 40, 85, 0.1); }
        .data-table th { background: linear-gradient(135deg, #002855 0%, #1b3157 100%); color: white; font-weight: 600; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.05em; }
        .data-table tr:nth-child(even) { background-color: #f8fafc; }
        .data-table tr:hover { background-color: #e8f0f8; }
        .sql-code { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 8px; font-family: 'Monaco', 'Menlo', monospace; }
        @keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-5px); } }
        .genie-float { animation: float 3s ease-in-out infinite; }
        .prose strong { font-weight: 600; color: #002855; }
        .prose code { background-color: #e8f0f8; padding: 0.125rem 0.375rem; border-radius: 0.25rem; font-size: 0.875em; color: #002855; }
        .prose ul, .prose ol { margin: 0.5rem 0; padding-left: 1.5rem; }
        .prose li { margin: 0.25rem 0; }
        .prose ul { list-style-type: disc; }
        .prose ol { list-style-type: decimal; }
        .prose p { margin: 0.5rem 0; }
        .prose a { color: #426ca9; text-decoration: underline; }
    </style>
</head>
<body class="bg-brand-background">
    <div id="app" class="flex h-screen">
        <div class="w-80 bg-white border-r border-gray-200 flex flex-col shadow-lg">
            <div class="p-5 border-b border-gray-100 bg-gradient-to-r from-brand-primary to-brand-secondary">
                <div class="flex items-center gap-3 mb-4">
                    <div class="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center genie-float">
                        <svg class="w-6 h-6 text-white" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12 2L9.19 8.63L2 9.24L7.46 13.97L5.82 21L12 17.27L18.18 21L16.54 13.97L22 9.24L14.81 8.63L12 2Z"/>
                        </svg>
                    </div>
                    <div>
                        <h1 class="text-white font-bold text-lg">{{APP_NAME}}</h1>
                        <p class="text-white/70 text-xs">{{APP_DESCRIPTION}}</p>
                    </div>
                    <div class="ml-auto flex gap-1">
                        <span class="w-2 h-2 bg-brand-accent rounded-full sparkle"></span>
                        <span class="w-1.5 h-1.5 bg-white/60 rounded-full sparkle sparkle-delay-1"></span>
                        <span class="w-1 h-1 bg-brand-accent/60 rounded-full sparkle sparkle-delay-2"></span>
                    </div>
                </div>
                <button id="new-chat-btn" class="w-full bg-white text-brand-primary px-4 py-2.5 rounded-xl hover:bg-brand-light transition-all duration-200 flex items-center justify-center gap-2 font-medium shadow-md">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                    Nova Conversa
                </button>
            </div>
            <div class="flex-1 overflow-y-auto p-3" id="history-list">
                <p class="text-sm text-gray-400 text-center py-8">
                    <svg class="w-12 h-12 mx-auto mb-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path>
                    </svg>
                    Nenhuma conversa ainda
                </p>
            </div>
            <div class="p-4 border-t border-gray-100 bg-gray-50">
                <div class="flex items-center gap-3">
                    <div class="w-9 h-9 bg-brand-primary rounded-full flex items-center justify-center">
                        <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path></svg>
                    </div>
                    <div class="flex-1 min-w-0">
                        <p id="user-name" class="text-sm font-medium text-brand-primary truncate">Carregando...</p>
                        <p class="text-xs text-gray-400">Conectado</p>
                    </div>
                    <div class="w-2 h-2 bg-brand-accent rounded-full"></div>
                </div>
            </div>
        </div>
        <div class="flex-1 flex flex-col bg-gradient-to-b from-brand-background to-white">
            <div class="bg-white border-b border-gray-100 p-4 shadow-sm">
                <div class="flex items-center justify-between mb-3">
                    <div class="flex items-center gap-3">
                        <div class="w-8 h-8 bg-gradient-to-br from-brand-primary to-brand-secondary rounded-lg flex items-center justify-center">
                            <svg class="w-4 h-4 text-white" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L9.19 8.63L2 9.24L7.46 13.97L5.82 21L12 17.27L18.18 21L16.54 13.97L22 9.24L14.81 8.63L12 2Z"/></svg>
                        </div>
                        <div>
                            <h2 class="font-semibold text-brand-primary">Assistente de Dados</h2>
                            <p id="conversation-title" class="text-xs text-gray-400"></p>
                        </div>
                    </div>
                    {{POWERED_BY_BADGE}}
                </div>
                <div class="flex items-center gap-3 bg-brand-background rounded-xl p-3">
                    <div class="flex items-center gap-2">
                        <svg class="w-5 h-5 text-brand-secondary" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
                        <label class="text-sm font-medium text-brand-primary">Fonte de Dados:</label>
                    </div>
                    <select id="genie-select" class="flex-1 bg-white border border-gray-200 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-secondary focus:border-transparent transition-all">
                        <option value="">Selecione uma fonte...</option>
                    </select>
                </div>
                <p id="genie-description" class="text-xs text-gray-500 mt-2 pl-1"></p>
            </div>
            <div id="messages" class="flex-1 overflow-y-auto p-6 space-y-4">
                <div class="flex flex-col items-center justify-center h-full text-center">
                    <div class="w-20 h-20 bg-gradient-to-br from-brand-primary to-brand-secondary rounded-2xl flex items-center justify-center mb-4 genie-float shadow-lg">
                        <svg class="w-10 h-10 text-white" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L9.19 8.63L2 9.24L7.46 13.97L5.82 21L12 17.27L18.18 21L16.54 13.97L22 9.24L14.81 8.63L12 2Z"/></svg>
                    </div>
                    <h3 class="text-xl font-semibold text-brand-primary mb-2">Olá! Sou o Genie</h3>
                    <p class="text-gray-500 max-w-md">Selecione uma fonte de dados acima e faça perguntas em linguagem natural.</p>
                    <div class="flex gap-2 mt-4">
                        <span class="px-3 py-1 bg-brand-light text-brand-secondary text-xs rounded-full">SQL Automático</span>
                        <span class="px-3 py-1 bg-brand-light text-brand-secondary text-xs rounded-full">Visualização de Dados</span>
                        <span class="px-3 py-1 bg-brand-light text-brand-secondary text-xs rounded-full">Histórico Salvo</span>
                    </div>
                </div>
            </div>
            <div class="bg-white border-t border-gray-100 p-4 shadow-lg">
                <form id="chat-form" class="flex gap-3">
                    <div class="flex-1 relative">
                        <input type="text" id="question-input" placeholder="Faça uma pergunta sobre seus dados..." class="w-full border border-gray-200 rounded-xl px-5 py-3 pr-12 focus:outline-none focus:ring-2 focus:ring-brand-secondary focus:border-transparent transition-all text-sm" disabled>
                    </div>
                    <button type="submit" id="send-button" class="bg-gradient-to-r from-brand-primary to-brand-secondary text-white px-6 py-3 rounded-xl hover:shadow-lg hover:scale-105 disabled:from-gray-300 disabled:to-gray-400 disabled:cursor-not-allowed disabled:hover:scale-100 transition-all duration-200 flex items-center gap-2 font-medium" disabled>
                        <span>Enviar</span>
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"></path></svg>
                    </button>
                </form>
            </div>
        </div>
    </div>
    <script>
        let genies = [];
        let selectedGenie = null;
        let conversationId = null;
        let currentConversationKey = null;
        let isLoading = false;
        let currentUser = null;
        let conversations = {};

        const genieSelect = document.getElementById('genie-select');
        const genieDescription = document.getElementById('genie-description');
        const messagesContainer = document.getElementById('messages');
        const chatForm = document.getElementById('chat-form');
        const questionInput = document.getElementById('question-input');
        const sendButton = document.getElementById('send-button');
        const userName = document.getElementById('user-name');
        const historyList = document.getElementById('history-list');
        const newChatBtn = document.getElementById('new-chat-btn');
        const conversationTitle = document.getElementById('conversation-title');

        async function loadConversations() {
            try {
                const response = await fetch('/api/conversations');
                if (response.ok) {
                    const data = await response.json();
                    conversations = {};
                    data.forEach(conv => {
                        conversations[conv.key] = { id: conv.genie_conversation_id, spaceId: conv.space_id, title: conv.title, messages: [], createdAt: conv.created_at };
                    });
                }
            } catch (e) { console.error('Failed to load conversations:', e); conversations = {}; }
            renderHistoryList();
        }

        async function saveConversationToBackend(key, spaceId, title) {
            try { await fetch('/api/conversations', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key, space_id: spaceId, title }) }); }
            catch (e) { console.error('Failed to save conversation:', e); }
        }

        async function updateConversationInBackend(key, genieConversationId, title) {
            try { await fetch(`/api/conversations/${key}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ genie_conversation_id: genieConversationId, title: title }) }); }
            catch (e) { console.error('Failed to update conversation:', e); }
        }

        async function saveMessageToBackend(conversationKey, messageType, content, data) {
            try { await fetch('/api/messages', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ conversation_key: conversationKey, message_type: messageType, content: content, data: data }) }); }
            catch (e) { console.error('Failed to save message:', e); }
        }

        function renderHistoryList() {
            const sortedKeys = Object.keys(conversations).sort((a, b) => new Date(conversations[b].createdAt) - new Date(conversations[a].createdAt));
            if (sortedKeys.length === 0) {
                historyList.innerHTML = `<div class="text-center py-8"><svg class="w-12 h-12 mx-auto mb-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path></svg><p class="text-sm text-gray-400">Nenhuma conversa ainda</p></div>`;
                return;
            }
            historyList.innerHTML = sortedKeys.map(key => {
                const conv = conversations[key];
                const isActive = key === currentConversationKey;
                const genie = genies.find(g => g.space_id === conv.spaceId);
                const genieName = genie ? genie.title : 'Fonte de Dados';
                const date = new Date(conv.createdAt).toLocaleDateString('pt-BR');
                return `<div class="conversation-item ${isActive ? 'active' : ''} p-3 rounded-lg cursor-pointer mb-2 group" onclick="loadConversation('${key}')"><div class="flex items-start gap-3"><div class="w-8 h-8 bg-brand-light rounded-lg flex items-center justify-center flex-shrink-0"><svg class="w-4 h-4 text-brand-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path></svg></div><div class="flex-1 min-w-0"><p class="text-sm font-medium text-brand-primary truncate">${escapeHtml(conv.title)}</p><p class="text-xs text-gray-400 mt-0.5">${genieName}</p><p class="text-xs text-gray-300">${date}</p></div><button onclick="event.stopPropagation(); deleteConversation('${key}')" class="opacity-0 group-hover:opacity-100 text-gray-300 hover:text-red-500 p-1 transition-all"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg></button></div></div>`;
            }).join('');
        }

        function startNewConversation() {
            currentConversationKey = null; conversationId = null; conversationTitle.textContent = '';
            if (selectedGenie) {
                messagesContainer.innerHTML = `<div class="flex flex-col items-center justify-center h-full text-center"><div class="w-16 h-16 bg-gradient-to-br from-brand-primary to-brand-secondary rounded-2xl flex items-center justify-center mb-4 genie-float shadow-lg"><svg class="w-8 h-8 text-white" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L9.19 8.63L2 9.24L7.46 13.97L5.82 21L12 17.27L18.18 21L16.54 13.97L22 9.24L14.81 8.63L12 2Z"/></svg></div><h3 class="text-lg font-semibold text-brand-primary mb-2">Pronto para ajudar!</h3><p class="text-gray-500 text-sm max-w-md mb-4">Você está conectado a <strong class="text-brand-secondary">${escapeHtml(selectedGenie.title)}</strong>. Faça perguntas em linguagem natural.</p></div>`;
            } else {
                messagesContainer.innerHTML = `<div class="flex flex-col items-center justify-center h-full text-center"><div class="w-20 h-20 bg-gradient-to-br from-brand-primary to-brand-secondary rounded-2xl flex items-center justify-center mb-4 genie-float shadow-lg"><svg class="w-10 h-10 text-white" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L9.19 8.63L2 9.24L7.46 13.97L5.82 21L12 17.27L18.18 21L16.54 13.97L22 9.24L14.81 8.63L12 2Z"/></svg></div><h3 class="text-xl font-semibold text-brand-primary mb-2">Olá! Sou o Genie</h3><p class="text-gray-500 max-w-md">Selecione uma fonte de dados acima e faça perguntas em linguagem natural.</p></div>`;
            }
            renderHistoryList();
        }

        async function loadConversation(key) {
            try {
                const response = await fetch(`/api/conversations/${key}`);
                if (!response.ok) return;
                const conv = await response.json();
                currentConversationKey = key; conversationId = conv.genie_conversation_id; conversationTitle.textContent = conv.title;
                conversations[key] = { id: conv.genie_conversation_id, spaceId: conv.space_id, title: conv.title, messages: conv.messages || [], createdAt: conv.created_at };
                const genie = genies.find(g => g.space_id === conv.space_id);
                if (genie) { genieSelect.value = conv.space_id; selectedGenie = genie; genieDescription.textContent = genie.description || ''; questionInput.disabled = false; sendButton.disabled = false; }
                messagesContainer.innerHTML = '';
                (conv.messages || []).forEach(msg => { if (msg.type === 'user') { addMessageToDOM('user', msg.content); } else if (msg.type === 'genie') { addGenieResponseToDOM(msg.data); } });
                renderHistoryList();
            } catch (e) { console.error('Failed to load conversation:', e); }
        }

        async function deleteConversation(key) {
            if (confirm('Excluir esta conversa?')) {
                try {
                    const response = await fetch(`/api/conversations/${key}`, { method: 'DELETE' });
                    if (response.ok) { delete conversations[key]; if (currentConversationKey === key) { startNewConversation(); } renderHistoryList(); }
                } catch (e) { console.error('Failed to delete conversation:', e); }
            }
        }

        async function createConversation(spaceId, firstQuestion) {
            const key = 'conv-' + Date.now();
            const title = firstQuestion.substring(0, 50) + (firstQuestion.length > 50 ? '...' : '');
            conversations[key] = { id: null, spaceId: spaceId, title: title, messages: [], createdAt: new Date().toISOString() };
            currentConversationKey = key;
            await saveConversationToBackend(key, spaceId, title);
            renderHistoryList();
            return key;
        }

        async function addMessageToConversation(type, content, data = null) {
            if (!currentConversationKey || !conversations[currentConversationKey]) return;
            conversations[currentConversationKey].messages.push({ type, content, data, timestamp: new Date().toISOString() });
            await saveMessageToBackend(currentConversationKey, type, content, data);
        }

        async function updateConversationId(convId) {
            if (currentConversationKey && conversations[currentConversationKey]) {
                conversations[currentConversationKey].id = convId; conversationId = convId;
                await updateConversationInBackend(currentConversationKey, convId, null);
            }
        }

        async function loadUserInfo() {
            try { const response = await fetch('/api/me'); currentUser = await response.json(); userName.textContent = currentUser.name || currentUser.email; userName.title = currentUser.email; }
            catch (error) { console.error('Failed to load user info:', error); userName.textContent = 'Guest'; }
        }

        async function loadGenies() {
            try {
                const response = await fetch('/api/genies'); genies = await response.json();
                genieSelect.innerHTML = '<option value="">Selecione um Genie...</option>';
                genies.forEach(genie => { const option = document.createElement('option'); option.value = genie.space_id; option.textContent = genie.title; genieSelect.appendChild(option); });
                renderHistoryList();
            } catch (error) { console.error('Failed to load genies:', error); genieSelect.innerHTML = '<option value="">Erro ao carregar genies</option>'; }
        }

        genieSelect.addEventListener('change', (e) => {
            const spaceId = e.target.value; selectedGenie = genies.find(g => g.space_id === spaceId);
            if (selectedGenie) { genieDescription.textContent = selectedGenie.description || ''; questionInput.disabled = false; sendButton.disabled = false; startNewConversation(); }
            else { genieDescription.textContent = ''; questionInput.disabled = true; sendButton.disabled = true; }
        });

        newChatBtn.addEventListener('click', () => { startNewConversation(); });

        chatForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const question = questionInput.value.trim();
            if (!question || !selectedGenie || isLoading) return;
            questionInput.value = ''; isLoading = true; sendButton.disabled = true; questionInput.disabled = true;
            if (!currentConversationKey) { await createConversation(selectedGenie.space_id, question); conversationTitle.textContent = conversations[currentConversationKey].title; }
            const initialMsg = messagesContainer.querySelector('.text-center'); if (initialMsg) initialMsg.remove();
            addMessageToDOM('user', question); await addMessageToConversation('user', question);
            const loadingId = addMessageToDOM('loading', 'Pensando');
            try {
                const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ space_id: selectedGenie.space_id, question: question, conversation_id: conversationId }) });
                const data = await response.json();
                document.getElementById(loadingId)?.remove();
                if (!response.ok) { addMessageToDOM('error', `Erro: ${data.detail || 'Algo deu errado'}`); return; }
                await updateConversationId(data.conversation_id);
                addGenieResponseToDOM(data); await addMessageToConversation('genie', null, data);
            } catch (error) { document.getElementById(loadingId)?.remove(); addMessageToDOM('error', `Erro: ${error.message}`); }
            finally { isLoading = false; sendButton.disabled = false; questionInput.disabled = false; questionInput.focus(); }
        });

        function addMessageToDOM(type, content) {
            const id = 'msg-' + Date.now(); const div = document.createElement('div'); div.id = id;
            if (type === 'user') { div.className = 'flex justify-end mb-4'; div.innerHTML = `<div class="message-user px-5 py-3 max-w-2xl"><p class="text-sm">${escapeHtml(content)}</p></div>`; }
            else if (type === 'loading') { div.className = 'flex justify-start mb-4'; div.innerHTML = `<div class="flex items-start gap-3"><div class="w-8 h-8 bg-gradient-to-br from-brand-primary to-brand-secondary rounded-lg flex items-center justify-center flex-shrink-0 loading-glow"><svg class="w-4 h-4 text-white" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L9.19 8.63L2 9.24L7.46 13.97L5.82 21L12 17.27L18.18 21L16.54 13.97L22 9.24L14.81 8.63L12 2Z"/></svg></div><div class="message-genie px-5 py-3"><div class="flex items-center gap-2"><span class="text-sm text-gray-500">Analisando</span><div class="flex gap-1"><span class="w-2 h-2 bg-brand-secondary rounded-full typing-dot"></span><span class="w-2 h-2 bg-brand-secondary rounded-full typing-dot"></span><span class="w-2 h-2 bg-brand-secondary rounded-full typing-dot"></span></div></div></div></div>`; }
            else if (type === 'error') { div.className = 'flex justify-start mb-4'; div.innerHTML = `<div class="flex items-start gap-3"><div class="w-8 h-8 bg-red-500 rounded-lg flex items-center justify-center flex-shrink-0"><svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg></div><div class="bg-red-50 border border-red-200 rounded-2xl px-5 py-3"><p class="text-sm text-red-700">${escapeHtml(content)}</p></div></div>`; }
            messagesContainer.appendChild(div); messagesContainer.scrollTop = messagesContainer.scrollHeight; return id;
        }

        function formatNumber(num) {
            if (num === null || num === undefined || num === '') return '-';
            const n = parseFloat(num); if (isNaN(n)) return String(num);
            if (Number.isInteger(n) && Math.abs(n) < 1000000) return n.toLocaleString('pt-BR');
            return n.toLocaleString('pt-BR', { maximumFractionDigits: 2 });
        }

        function parseMarkdown(text) {
            if (!text) return '';
            if (typeof marked !== 'undefined' && marked.parse) { try { marked.setOptions({ breaks: true, gfm: true }); return marked.parse(text); } catch (e) { console.error('Marked parsing error:', e); } }
            return escapeHtml(text).split('\\n').join('<br>');
        }

        const chartColors = ['{{BRAND_PRIMARY}}', '{{BRAND_SECONDARY}}', '{{BRAND_ACCENT}}', '#f9cc54', '#d23b3b', '#1b3157', '#5a8fd4', '#3dd9a3', '#ffdd78', '#e85c5c'];
        let chartCounter = 0; let chartInstances = {};

        function hasNumericColumns(columns, data) {
            if (!columns || columns.length < 2 || !data || data.length === 0) return false;
            for (let i = 1; i < columns.length; i++) { let numericCount = 0; for (let row of data.slice(0, 5)) { const val = parseFloat(row[i]); if (!isNaN(val)) numericCount++; } if (numericCount > 0) return true; }
            return false;
        }

        function detectChartType(columns, data) {
            if (!data || data.length === 0) return 'bar';
            if (data.length <= 6 && columns.length === 2) return 'doughnut';
            if (data.length > 10) return 'line';
            return 'bar';
        }

        function createChart(canvasId, columns, data) {
            try {
                const canvas = document.getElementById(canvasId); if (!canvas) return false;
                if (!data || data.length === 0 || !columns || columns.length < 2) return false;
                if (chartInstances[canvasId]) chartInstances[canvasId].destroy();
                const chartType = detectChartType(columns, data);
                const labels = data.map(row => { const label = String(row[0] || ''); return label.length > 20 ? label.substring(0, 20) + '...' : label; });
                const datasets = [];
                for (let i = 1; i < columns.length; i++) {
                    const values = data.map(row => { const val = parseFloat(row[i]); return isNaN(val) ? 0 : val; });
                    if (values.some(v => v !== 0)) { datasets.push({ label: columns[i], data: values, backgroundColor: chartType === 'doughnut' ? chartColors.slice(0, data.length) : chartColors[(i - 1) % chartColors.length] + '99', borderColor: chartColors[(i - 1) % chartColors.length], borderWidth: chartType === 'line' ? 2 : 1, fill: chartType !== 'line', tension: 0.3 }); }
                }
                if (datasets.length === 0) return false;
                chartInstances[canvasId] = new Chart(canvas, { type: chartType, data: { labels, datasets }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { font: { family: 'Inter', size: 11 }, color: '#002855' } } }, scales: chartType !== 'doughnut' ? { x: { ticks: { font: { family: 'Inter', size: 10 }, color: '#666', maxRotation: 45 }, grid: { color: '#f0f0f0' } }, y: { ticks: { font: { family: 'Inter', size: 10 }, color: '#666', callback: (value) => formatNumber(value) }, grid: { color: '#f0f0f0' }, beginAtZero: true } } : {} } });
                return true;
            } catch (error) { console.error('Error creating chart:', error); return false; }
        }

        function addGenieResponseToDOM(data) {
            const div = document.createElement('div'); div.className = 'flex justify-start mb-4';
            let contentHtml = ''; const chartId = 'chart-' + (++chartCounter);
            if (data.text_response) { contentHtml += `<div class="prose prose-sm text-gray-700 leading-relaxed max-w-none">${parseMarkdown(data.text_response)}</div>`; }
            else if (data.description) { contentHtml += `<div class="prose prose-sm text-gray-700 leading-relaxed max-w-none">${parseMarkdown(data.description)}</div>`; }
            const canShowChart = data.columns && data.columns.length >= 2 && data.data && data.data.length > 0 && data.data.length <= MAX_CHART_ROWS && hasNumericColumns(data.columns, data.data);
            if (canShowChart) { contentHtml += `<div class="mt-4 bg-white rounded-lg border border-gray-200 p-4" id="${chartId}-container"><div class="flex items-center justify-between mb-3"><span class="text-xs font-medium text-gray-500 flex items-center gap-1"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>Visualização</span></div><div class="h-64"><canvas id="${chartId}"></canvas></div></div>`; }
            if (data.sql) { contentHtml += `<details class="mt-4 group"><summary class="cursor-pointer text-xs font-medium text-brand-secondary hover:text-brand-primary flex items-center gap-2 transition-colors"><svg class="w-4 h-4 transition-transform group-open:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>Ver consulta SQL</summary><div class="mt-2 sql-code p-4 overflow-x-auto"><code class="text-xs text-gray-300 whitespace-pre-wrap">${escapeHtml(data.sql)}</code></div></details>`; }
            if (data.columns && data.columns.length > 0 && data.data && data.data.length > 0) {
                const rowCount = data.row_count || data.data.length;
                contentHtml += `<details class="mt-4 group" ${!canShowChart ? 'open' : ''}><summary class="cursor-pointer text-xs font-medium text-brand-secondary hover:text-brand-primary flex items-center gap-2 transition-colors"><svg class="w-4 h-4 transition-transform group-open:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>Ver dados (${rowCount} registro${rowCount !== 1 ? 's' : ''})</summary><div class="mt-2 overflow-x-auto rounded-lg border border-gray-200"><table class="data-table w-full text-sm"><thead><tr>${data.columns.map(col => `<th class="px-4 py-3 text-left">${escapeHtml(col)}</th>`).join('')}</tr></thead><tbody class="text-gray-600">${data.data.slice(0, MAX_TABLE_ROWS).map((row, idx) => `<tr class="${idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}">${row.map(cell => `<td class="px-4 py-2.5 border-t border-gray-100">${formatNumber(cell)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>${rowCount > MAX_TABLE_ROWS ? `<p class="text-xs text-gray-400 mt-2">Exibindo ${MAX_TABLE_ROWS} de ${rowCount} registros</p>` : ''}</details>`;
            }
            if (data.error) { contentHtml += `<div class="mt-3 bg-red-50 border border-red-200 rounded-lg px-4 py-3"><p class="text-sm text-red-600 flex items-center gap-2"><svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>${escapeHtml(data.error)}</p></div>`; }
            div.innerHTML = `<div class="flex items-start gap-3 max-w-4xl"><div class="w-8 h-8 bg-gradient-to-br from-brand-primary to-brand-secondary rounded-lg flex items-center justify-center flex-shrink-0"><svg class="w-4 h-4 text-white" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L9.19 8.63L2 9.24L7.46 13.97L5.82 21L12 17.27L18.18 21L16.54 13.97L22 9.24L14.81 8.63L12 2Z"/></svg></div><div class="message-genie px-5 py-4 flex-1">${contentHtml || '<p class="text-sm text-gray-500">Sem resposta disponível</p>'}</div></div>`;
            messagesContainer.appendChild(div); messagesContainer.scrollTop = messagesContainer.scrollHeight;
            if (canShowChart) { setTimeout(() => { const success = createChart(chartId, data.columns, data.data); if (!success) { const container = document.getElementById(chartId + '-container'); if (container) container.style.display = 'none'; } }, 100); }
        }

        function escapeHtml(text) { const div = document.createElement('div'); div.textContent = text; return div.innerHTML; }

        loadConversations(); loadUserInfo(); loadGenies();
    </script>
</body>
</html>'''

    # Replace placeholders with actual values
    html = html.replace('{{APP_NAME}}', APP_NAME)
    html = html.replace('{{APP_DESCRIPTION}}', APP_DESCRIPTION)
    html = html.replace('{{MAX_TABLE_ROWS}}', str(MAX_TABLE_ROWS))
    html = html.replace('{{MAX_CHART_ROWS}}', str(MAX_CHART_ROWS))
    html = html.replace('{{BRAND_PRIMARY}}', BRAND_COLORS["primary"])
    html = html.replace('{{BRAND_SECONDARY}}', BRAND_COLORS["secondary"])
    html = html.replace('{{BRAND_ACCENT}}', BRAND_COLORS["accent"])
    html = html.replace('{{BRAND_BACKGROUND}}', BRAND_COLORS["background"])
    html = html.replace('{{BRAND_LIGHT}}', BRAND_COLORS["light"])
    html = html.replace('{{POWERED_BY_BADGE}}', powered_by_badge)

    return html


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    return get_frontend_html()


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    return HTMLResponse(content=get_frontend_html())

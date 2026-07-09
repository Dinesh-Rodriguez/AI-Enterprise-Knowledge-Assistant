import React, { useEffect, useMemo, useState } from "react";
import { Bot, ChevronLeft, FileUp, FolderPlus, LogIn, Send, Sparkles, Trash2 } from "lucide-react";
import client, { getAuthHeaders } from "./api/client";

const emptyAuth = { username: "", email: "", password: "" };

export default function App() {
  const [authMode, setAuthMode] = useState("login");
  const [authForm, setAuthForm] = useState(emptyAuth);
  const [tokenReady, setTokenReady] = useState(Boolean(localStorage.getItem("access_token")));
  const [workspaces, setWorkspaces] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [workspaceName, setWorkspaceName] = useState("");
  const [selectedWorkspace, setSelectedWorkspace] = useState(null);
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState([]);
  const [uploadFile, setUploadFile] = useState(null);
  const [focusedDocument, setFocusedDocument] = useState(null);
  const [focusedPage, setFocusedPage] = useState("");
  const [focusedChunkId, setFocusedChunkId] = useState(null);
  const [selectedCitationKey, setSelectedCitationKey] = useState("");
  const [streamError, setStreamError] = useState("");
  const [uploadState, setUploadState] = useState({ busy: false, error: "" });
  const [workspaceSettings, setWorkspaceSettings] = useState(null);
  const [workspaceMembers, setWorkspaceMembers] = useState([]);
  const [settingsDraft, setSettingsDraft] = useState({ llm_provider: "local", embedding_provider: "local", llm_model: "", embedding_model: "" });
  const [workspaceMessage, setWorkspaceMessage] = useState("");
  const [workspaceActionState, setWorkspaceActionState] = useState({ busy: false, error: "" });
  const [documentActionState, setDocumentActionState] = useState({ busy: false, error: "" });
  const [conversationState, setConversationState] = useState({ busy: false, error: "" });
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [intelligenceOutput, setIntelligenceOutput] = useState("");
  const [authError, setAuthError] = useState("");
  const [currentUsername, setCurrentUsername] = useState(localStorage.getItem("username") || "");

  useEffect(() => {
    if (tokenReady) {
      loadAll();
    }
  }, [tokenReady]);

  useEffect(() => {
    if (selectedWorkspace) {
      loadWorkspaceData(selectedWorkspace);
      loadWorkspaceMeta(selectedWorkspace);
    }
  }, [selectedWorkspace]);

  useEffect(() => {
    if (!tokenReady) return undefined;
    const timer = setInterval(() => {
      loadAll();
    }, 5000);
    return () => clearInterval(timer);
  }, [tokenReady, selectedWorkspace]);

  async function loadAll() {
    try {
      const [ws, docs, convs] = await Promise.all([
        client.get("/workspaces/"),
        client.get("/documents/"),
        client.get("/conversations/"),
      ]);
      setWorkspaces(ws.data);
      setDocuments(docs.data);
      setConversations(convs.data);
      if (!selectedWorkspace && ws.data.length) {
        setSelectedWorkspace(ws.data[0].id);
      }
    } catch (error) {
      console.error(error);
    }
  }

  async function loadWorkspaceData(workspaceId, preferredConversationId = null) {
    const [docs, convs] = await Promise.all([
      client.get("/documents/", { params: { workspace: workspaceId } }),
      client.get("/conversations/", { params: { workspace: workspaceId } }),
    ]);
    setDocuments(docs.data);
    setConversations(convs.data);
    const nextConversationId = preferredConversationId || selectedConversation;
    if (!convs.data.some((conv) => conv.id === nextConversationId)) {
      setSelectedConversation(convs.data[0]?.id || null);
    } else if (preferredConversationId) {
      setSelectedConversation(preferredConversationId);
    }
  }

  async function loadWorkspaceMeta(workspaceId) {
    const [settings, members] = await Promise.all([
      client.get(`/workspaces/${workspaceId}/config/`),
      client.get(`/workspaces/${workspaceId}/members/`),
    ]);
    setWorkspaceSettings(settings.data);
    setWorkspaceMembers(members.data);
    setSettingsDraft(settings.data);
  }

  async function submitAuth(event) {
    event.preventDefault();
    setAuthError("");
    if (authMode === "register") {
      try {
        await client.post("/auth/register/", authForm);
      } catch (error) {
        setAuthError(formatApiError(error));
        return;
      }
    }
    try {
      const { data } = await client.post("/auth/login/", {
        username: authForm.username,
        password: authForm.password,
      });
      localStorage.setItem("access_token", data.access);
      localStorage.setItem("refresh_token", data.refresh);
      localStorage.setItem("username", authForm.username);
      setCurrentUsername(authForm.username);
      setTokenReady(true);
    } catch (error) {
      setAuthError(formatApiError(error));
    }
  }

  function logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("username");
    setTokenReady(false);
    setSelectedWorkspace(null);
    setSelectedConversation(null);
    setWorkspaces([]);
    setDocuments([]);
    setConversations([]);
    setWorkspaceSettings(null);
    setWorkspaceMembers([]);
    setWorkspaceMessage("");
    setConversationState({ busy: false, error: "" });
    setUploadState({ busy: false, error: "" });
    setAuthForm(emptyAuth);
    setCurrentUsername("");
    setQuestion("");
    setAnswer("");
    setCitations([]);
    setSelectedCitationKey("");
    setStreamError("");
    setIntelligenceOutput("");
  }

  async function createWorkspace(event) {
    event.preventDefault();
    await client.post("/workspaces/", { name: workspaceName, description: "" });
    setWorkspaceName("");
    loadAll();
  }

  async function deleteWorkspace(workspaceId) {
    setWorkspaceActionState({ busy: true, error: "" });
    try {
      await client.delete(`/workspaces/${workspaceId}/`);
      const { data } = await client.get("/workspaces/");
      setWorkspaces(data);
      const stillSelected = data.some((workspace) => workspace.id === selectedWorkspace);
      if (!stillSelected) {
        const nextWorkspaceId = data[0]?.id || null;
        setSelectedWorkspace(nextWorkspaceId);
        setSelectedConversation(null);
        setDocuments([]);
        setConversations([]);
        setWorkspaceSettings(null);
        setWorkspaceMembers([]);
        setFocusedDocument(null);
        setFocusedPage("");
        setFocusedChunkId(null);
      }
      setWorkspaceMessage("Workspace deleted.");
      await loadAll();
      setWorkspaceActionState({ busy: false, error: "" });
    } catch (error) {
      setWorkspaceActionState({ busy: false, error: formatApiError(error) });
    }
  }

  async function saveWorkspaceSettings() {
    if (!selectedWorkspace) return;
    setWorkspaceMessage("");
    try {
      const { data } = await client.patch(`/workspaces/${selectedWorkspace}/config/`, settingsDraft);
      setWorkspaceSettings(data);
      setSettingsDraft(data);
      setWorkspaceMessage("Workspace AI saved.");
    } catch (error) {
      setWorkspaceMessage(formatApiError(error));
    }
  }

  async function uploadDocument(event) {
    event.preventDefault();
    if (!uploadFile || !selectedWorkspace) return;
    setUploadState({ busy: true, error: "" });
    const form = new FormData();
    form.append("workspace", selectedWorkspace);
    form.append("title", uploadFile.name);
    form.append("file", uploadFile);
    try {
      await client.post("/documents/", form, { headers: { "Content-Type": "multipart/form-data" } });
      setUploadFile(null);
      await loadAll();
    } catch (error) {
      setUploadState({
        busy: false,
        error: error?.response?.data?.detail || "Upload failed.",
      });
      return;
    }
    setUploadState({ busy: false, error: "" });
  }

  async function deleteDocument(docId) {
    setDocumentActionState({ busy: true, error: "" });
    try {
      await client.delete(`/documents/${docId}/`);
      if (focusedDocument?.id === docId) {
        setFocusedDocument(null);
        setFocusedPage("");
        setFocusedChunkId(null);
      }
      if (selectedWorkspace) {
        await loadWorkspaceData(selectedWorkspace);
      }
      await loadAll();
      setDocumentActionState({ busy: false, error: "" });
    } catch (error) {
      setDocumentActionState({ busy: false, error: formatApiError(error) });
    }
  }

  async function retryDocument(docId) {
    await client.post(`/documents/${docId}/retry/`);
    await loadAll();
  }

  async function runIntelligence(action, docId, otherDocumentId = "") {
    let path = `/documents/${docId}/${action}/`;
    const payload = {};
    if (action === "compare") payload.other_document_id = otherDocumentId;
    const { data } = await client.post(path, payload);
    setIntelligenceOutput(data.summary || data.notes || data.comparison || "");
  }

  async function createConversation() {
    if (!selectedWorkspace) return;
    setConversationState({ busy: true, error: "" });
    try {
      const { data } = await client.post("/conversations/", {
        workspace: selectedWorkspace,
        title: "New conversation",
      });
      await loadWorkspaceData(selectedWorkspace, data.id);
      setConversationState({ busy: false, error: "" });
    } catch (error) {
      setConversationState({ busy: false, error: formatApiError(error) });
    }
  }

  async function deleteConversationById(conversationId) {
    if (!conversationId) return;
    setConversationState({ busy: true, error: "" });
    try {
      await client.delete(`/conversations/${conversationId}/`);
      const { data } = await client.get("/conversations/", { params: { workspace: selectedWorkspace } });
      setConversations(data);
      setSelectedConversation(data[0]?.id || null);
      setAnswer("");
      setQuestion("");
      setCitations([]);
      setStreamError("");
      setConversationState({ busy: false, error: "" });
    } catch (error) {
      setConversationState({ busy: false, error: formatApiError(error) });
    }
  }

  async function deleteConversation() {
    await deleteConversationById(selectedConversation);
  }

  function openDeleteTarget(target) {
    setDeleteTarget(target);
  }

  function closeDeleteTarget() {
    setDeleteTarget(null);
  }

  async function confirmDeleteTarget() {
    if (!deleteTarget) return;
    const target = deleteTarget;
    closeDeleteTarget();
    if (target.kind === "workspace") {
      await deleteWorkspace(target.id);
    } else if (target.kind === "document") {
      await deleteDocument(target.id);
    } else if (target.kind === "conversation") {
      await deleteConversationById(target.id);
    }
  }

  async function ask() {
    if (!selectedConversation || !question.trim()) return;
    setAnswer("");
    setCitations([]);
    setStreamError("");
    try {
      const response = await fetch(`${client.defaults.baseURL}/conversations/${selectedConversation}/stream_ask/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({ question }),
      });
      if (!response.ok || !response.body) {
        setStreamError(`Ask failed (${response.status}).`);
        return;
      }
      setQuestion("");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";
        for (const part of parts) {
          const event = parseSseEvent(part);
          if (event.name === "citations") setCitations(JSON.parse(event.data));
          if (event.name === "token") setAnswer((current) => current + JSON.parse(event.data).text);
          if (event.name === "error") setStreamError(JSON.parse(event.data).detail);
        }
      }
      const refreshed = await client.get("/conversations/");
      setConversations(refreshed.data);
    } catch (error) {
      setStreamError(formatApiError(error));
    }
  }

  async function openCitation(citation) {
    const key = `${citation.document_id}:${citation.page_number || "all"}:${citation.chunk_id || "0"}`;
    setSelectedCitationKey(key);
    try {
      const { data } = await client.get(`/documents/${citation.document_id}/focus/`, {
        params: citation.page_number ? { page: citation.page_number } : {},
      });
      setFocusedDocument(data);
      setFocusedPage(String(citation.page_number || ""));
      setFocusedChunkId(citation.chunk_id || null);
      window.requestAnimationFrame(() => {
        document.getElementById("focus-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    } catch (error) {
      setStreamError(formatApiError(error));
    }
  }

  const conversationMessages = useMemo(
    () => conversations.find((c) => c.id === selectedConversation)?.messages || [],
    [conversations, selectedConversation],
  );

  if (!tokenReady) {
    return (
      <div className="shell auth-shell">
        <form className="panel auth-panel" onSubmit={submitAuth}>
          <div className="brand">
            <Bot size={18} />
            <span>AI Enterprise Knowledge Assistant</span>
          </div>
          <h1>{authMode === "login" ? "Sign in" : "Create account"}</h1>
          <div className="stack">
            <input placeholder="Username" value={authForm.username} onChange={(e) => setAuthForm({ ...authForm, username: e.target.value })} />
            {authMode === "register" && (
              <input placeholder="Email" value={authForm.email} onChange={(e) => setAuthForm({ ...authForm, email: e.target.value })} />
            )}
            <input type="password" placeholder="Password" value={authForm.password} onChange={(e) => setAuthForm({ ...authForm, password: e.target.value })} />
          </div>
          <div className="hint">Password must be at least 8 characters.</div>
          {authError && <div className="message error">{authError}</div>}
          <button className="primary" type="submit">
            <LogIn size={16} />
            {authMode === "login" ? "Login" : "Register"}
          </button>
          <button type="button" className="ghost" onClick={() => setAuthMode(authMode === "login" ? "register" : "login")}>
            {authMode === "login" ? "Need an account?" : "Already have an account?"}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="shell app-shell">
      <aside className="sidebar">
        <div className="brand">
          <Sparkles size={18} />
          <span>Knowledge Assistant</span>
        </div>
        <div className="section">
          <h2>Workspaces</h2>
          <form onSubmit={createWorkspace} className="inline-form">
            <input placeholder="New workspace" value={workspaceName} onChange={(e) => setWorkspaceName(e.target.value)} />
            <button className="icon-button" type="submit" title="Create workspace"><FolderPlus size={16} /></button>
          </form>
          <div className="list">
            {workspaces.map((workspace) => (
              <div key={workspace.id} className="workspace-row">
                <button
                  type="button"
                  className={selectedWorkspace === workspace.id ? "list-item active workspace-select" : "list-item workspace-select"}
                  onClick={() => setSelectedWorkspace(workspace.id)}
                >
                  {workspace.name}
                </button>
                <button
                  className="icon-button danger"
                  type="button"
                  onClick={() => openDeleteTarget({ kind: "workspace", id: workspace.id, label: workspace.name })}
                  title="Delete workspace"
                  disabled={workspaceActionState.busy}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
          {workspaceActionState.error && <div className="message error">{workspaceActionState.error}</div>}
        </div>
        <div className="section">
          <h2>Documents</h2>
          <form onSubmit={uploadDocument} className="upload-form">
            <input type="file" onChange={(e) => setUploadFile(e.target.files?.[0] || null)} />
            <button className="primary" type="submit"><FileUp size={16} />Upload</button>
          </form>
          {uploadState.busy && <div className="message muted">Uploading and indexing...</div>}
          {uploadState.error && <div className="message error">{uploadState.error}</div>}
          <div className="list">
            {documents.filter((doc) => !selectedWorkspace || doc.workspace === selectedWorkspace).map((doc) => (
              <div key={doc.id} className="doc-card">
                <button
                  className="list-item muted doc-row"
                  onClick={async () => {
                    const { data } = await client.get(`/documents/${doc.id}/focus/`);
                    setFocusedDocument(data);
                    setFocusedPage("");
                    setFocusedChunkId(null);
                  }}
                >
                  <span>{doc.title}</span>
                  <span className={`status-pill status-${doc.status}`}>{doc.status}</span>
                </button>
                <div className="doc-actions">
                  <button type="button" className="ghost small" onClick={() => retryDocument(doc.id)}>Retry</button>
                  <button type="button" className="ghost small" onClick={() => runIntelligence("summarize", doc.id)}>Summarize</button>
                  <button type="button" className="ghost small" onClick={() => runIntelligence("meeting_notes", doc.id)}>Notes</button>
                  <button type="button" className="ghost small danger-text" onClick={() => openDeleteTarget({ kind: "document", id: doc.id, label: doc.title })} disabled={documentActionState.busy}>
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
          {documentActionState.error && <div className="message error">{documentActionState.error}</div>}
        </div>
        <div className="section">
          <h2>Workspace AI</h2>
          <div className="settings-grid">
            <select value={settingsDraft.llm_provider} onChange={(e) => setSettingsDraft({ ...settingsDraft, llm_provider: e.target.value })}>
              <option value="local">Local</option>
              <option value="openai">OpenAI</option>
              <option value="gemini">Gemini</option>
              <option value="ollama">Ollama</option>
            </select>
            <select value={settingsDraft.embedding_provider} onChange={(e) => setSettingsDraft({ ...settingsDraft, embedding_provider: e.target.value })}>
              <option value="local">Local</option>
              <option value="openai">OpenAI</option>
              <option value="gemini">Gemini</option>
              <option value="ollama">Ollama</option>
            </select>
            <input value={settingsDraft.llm_model} onChange={(e) => setSettingsDraft({ ...settingsDraft, llm_model: e.target.value })} placeholder="LLM model" />
            <input value={settingsDraft.embedding_model} onChange={(e) => setSettingsDraft({ ...settingsDraft, embedding_model: e.target.value })} placeholder="Embedding model" />
          </div>
          <button className="primary" type="button" onClick={saveWorkspaceSettings}>Save settings</button>
          {workspaceMessage && <div className={workspaceMessage.includes("saved") ? "message muted" : "message error"}>{workspaceMessage}</div>}
          {workspaceActionState.error && <div className="message error">{workspaceActionState.error}</div>}
          <div className="list">
            {workspaceMembers.map((member) => (
              <div key={member.id} className="message muted">
                {member.username || `User ${member.user}`} - {member.role}
              </div>
            ))}
          </div>
        </div>
        <div className="sidebar-footer">
          <div className="user-row">
            <div className="user-label">Signed in as</div>
            <div className="user-name">{currentUsername || "Unknown user"}</div>
          </div>
          <button className="ghost" type="button" onClick={logout}>
            Logout
          </button>
        </div>
      </aside>

      <main className="content">
        <header className="topbar">
          <div>
            <h1>Ask AI</h1>
            <p>Answers with citations from indexed company content.</p>
          </div>
          <div className="topbar-actions">
            <button className="primary" onClick={createConversation} disabled={conversationState.busy || !selectedWorkspace}>
              New conversation
            </button>
          </div>
        </header>

        <section className="grid">
          <div className="panel conversation-panel">
            <div className="panel-header">
              <h2>Conversation</h2>
              <div className="conversation-controls">
                <select value={selectedConversation || ""} onChange={(e) => setSelectedConversation(Number(e.target.value))}>
                  <option value="">Select</option>
                  {conversations.map((conv) => (
                    <option key={conv.id} value={conv.id}>{conv.title || `Conversation ${conv.id}`}</option>
                  ))}
                </select>
                <button className="icon-button danger" type="button" onClick={() => openDeleteTarget({ kind: "conversation", id: selectedConversation, label: "this conversation" })} disabled={!selectedConversation} title="Delete conversation">
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
            <div className="messages">
              {conversationMessages.map((message) => (
                <div key={message.id} className={`message ${message.role}`}>
                  {message.content}
                </div>
              ))}
              {answer && <div className="message assistant">{answer}</div>}
            </div>
            <div className="chatbar">
              <textarea rows="3" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask about policies, docs, procedures..." />
              <button className="primary" onClick={ask} disabled={!selectedConversation || !question.trim()}>
                <Send size={16} />
                Ask
              </button>
            </div>
            {conversationState.error && <div className="message error">{conversationState.error}</div>}
            {streamError && <div className="message error">{streamError}</div>}
          </div>

          <div className="panel citations-panel">
            <h2>Citations</h2>
            <div className="list">
              {!citations.length && <div className="message muted">Ask a question to see source citations here.</div>}
              {citations.map((citation, index) => (
                <button
                  key={index}
                  type="button"
                  className={
                    selectedCitationKey === `${citation.document_id}:${citation.page_number || "all"}:${citation.chunk_id || "0"}`
                      ? "citation active"
                      : "citation"
                  }
                  onClick={() => openCitation(citation)}
                >
                  <strong>{citation.label}</strong>
                  <span>Page {citation.page_number}</span>
                </button>
              ))}
            </div>
          </div>
        </section>

        {focusedDocument && (
          <section className="panel focus-panel" id="focus-panel">
            <div className="panel-header">
              <button className="ghost" onClick={() => { setFocusedDocument(null); setFocusedChunkId(null); }}>
                <ChevronLeft size={16} />
                Back
              </button>
              <div className="panel-title-row">
                <div>
                  <h2>{focusedDocument.title}</h2>
                  <p>Page {focusedPage || "all"}</p>
                </div>
                <button
                  className="icon-button danger"
                  type="button"
                  onClick={() => openDeleteTarget({ kind: "document", id: focusedDocument.id, label: focusedDocument.title })}
                  disabled={documentActionState.busy}
                  title="Delete document"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
            <div className="list">
              {focusedDocument.chunks.map((chunk) => (
                <div
                  key={chunk.id}
                  className={
                    chunk.id === focusedChunkId || chunk.page_number.toString() === focusedPage
                      ? "message highlight"
                      : "message"
                  }
                >
                  {chunk.content}
                </div>
              ))}
              {!focusedDocument.chunks.length && (
                <div className="message muted">Select a citation to load the page text.</div>
              )}
            </div>
          </section>
        )}

        {intelligenceOutput && (
          <section className="panel">
            <h2>Document intelligence</h2>
            <div className="message">{intelligenceOutput}</div>
          </section>
        )}
      </main>

      {deleteTarget && (
        <div className="modal-backdrop" role="presentation" onClick={closeDeleteTarget}>
          <div className="modal" role="dialog" aria-modal="true" aria-labelledby="delete-title" onClick={(event) => event.stopPropagation()}>
            <h3 id="delete-title">Delete {deleteTarget.kind}</h3>
            <p>
              Remove <strong>{deleteTarget.label}</strong>?
            </p>
            <div className="modal-actions">
              <button type="button" className="ghost" onClick={closeDeleteTarget}>
                Cancel
              </button>
              <button type="button" className="icon-button danger modal-delete" onClick={confirmDeleteTarget}>
                <Trash2 size={16} />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function parseSseEvent(chunk) {
  const lines = chunk.split("\n");
  const name = lines.find((line) => line.startsWith("event:"))?.replace("event: ", "") || "";
  const data = lines.find((line) => line.startsWith("data:"))?.replace("data: ", "") || "";
  return { name, data };
}

function formatApiError(error) {
  const data = error?.response?.data;
  if (!data) return error?.message || "Request failed.";
  if (typeof data === "string") return data;
  const values = Object.values(data).flat().filter(Boolean);
  if (values.length) return values.join(" ");
  return "Request failed.";
}

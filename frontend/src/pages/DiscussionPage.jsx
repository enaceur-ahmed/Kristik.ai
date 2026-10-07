/**
 * Discussion page — ChatGPT-style chat about a selected dataset.
 *
 * Two columns: conversation history (left) + message thread (right).
 * Answers are produced by POST /api/conversations/{id}/messages
 * (RAG over the selected dataset; deterministic in demo mode).
 * Streaming (SSE) is NOT implemented — responses arrive in full.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '../api/client'

const EXAMPLE_QUESTIONS = [
  'Which columns have the most missing values?',
  'Summarize the quality issues',
  'What cleaning steps do you recommend?',
  'How many rows have missing revenue?',
]

const GROUP_LABELS = ['Today', 'Yesterday', 'Previous 7 days', 'Older']

function groupConversations(items) {
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const startOfYesterday = startOfToday - 86400000
  const startOfWeek = startOfToday - 7 * 86400000
  const groups = [[], [], [], []]
  for (const c of items) {
    const t = new Date(c.updated_at).getTime()
    if (t >= startOfToday) groups[0].push(c)
    else if (t >= startOfYesterday) groups[1].push(c)
    else if (t >= startOfWeek) groups[2].push(c)
    else groups[3].push(c)
  }
  return GROUP_LABELS.map((label, i) => ({ label, items: groups[i] })).filter(g => g.items.length)
}

function relativeDate(iso) {
  const t = new Date(iso).getTime()
  const now = Date.now()
  const diff = now - t
  if (diff < 60000) return 'just now'
  if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago'
  if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago'
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function formatDateTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

/* ---------------- message bubble ---------------- */
function MessageBubble({ msg, loading }) {
  const isUser = msg.role === 'user'
  const [sourcesOpen, setSourcesOpen] = useState(false)
  return (
    <div className={isUser ? 'chat-msg chat-msg-user' : 'chat-msg chat-msg-assistant'}>
      <div className={isUser ? 'bubble bubble-user' : 'bubble bubble-assistant'}>
        {isUser
          ? <div className="bubble-text">{msg.content}</div>
          : <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>}
        {!isUser && msg.sources && msg.sources.length > 0 && (
          <div className="sources-block">
            <button
              className="sources-toggle"
              onClick={() => setSourcesOpen(o => !o)}
            >
              {sourcesOpen ? '▾' : '▸'} Sources ({msg.sources.length})
            </button>
            {sourcesOpen && (
              <ul className="sources-list">
                {msg.sources.map((s, i) => (
                  <li key={i}>
                    <span className="sources-type">{s.type}</span>
                    {' '}{s.label}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        {!isUser && msg.llm_fallback && (
          <div className="alert alert-warning chat-fallback">
            ⚠ LLM unavailable — deterministic answer from the retrieved
            data{msg.llm_error ? ` (${msg.llm_error.split(':')[0]})` : ''}
          </div>
        )}
      </div>
    </div>
  )
}

/* ---------------- main page ---------------- */
export default function DiscussionPage() {
  const { conversationId } = useParams()
  const navigate = useNavigate()

  const [conversations, setConversations] = useState([])
  const [datasets, setDatasets] = useState([])
  const [messages, setMessages] = useState([])
  const [activeId, setActiveId] = useState(conversationId || null)
  const [datasetId, setDatasetId] = useState(null)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const threadRef = useRef(null)
  const taRef = useRef(null)

  /* ---- load conversations + datasets ---- */
  const refreshConversations = useCallback(async () => {
    try {
      const res = await api.listConversations()
      setConversations(res.items || [])
    } catch (e) { /* ignore */ }
  }, [])

  useEffect(() => {
    refreshConversations()
    api.listDatasets().then(res => setDatasets(res.items || [])).catch(() => {})
  }, [refreshConversations])

  /* ---- load a conversation's messages ---- */
  const loadConversation = useCallback(async (id) => {
    if (!id) { setMessages([]); return }
    try {
      const detail = await api.getConversation(id)
      setMessages(detail.messages || [])
      setDatasetId(detail.dataset_id || null)
    } catch (e) {
      setError('Could not load conversation.')
    }
  }, [])

  useEffect(() => {
    if (conversationId && conversationId !== activeId) {
      setActiveId(conversationId)
    }
  }, [conversationId, activeId])

  useEffect(() => {
    loadConversation(activeId)
  }, [activeId, loadConversation])

  /* ---- auto-scroll ---- */
  useEffect(() => {
    const el = threadRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, loading])

  /* ---- auto-growing textarea ---- */
  const autosize = () => {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 180) + 'px'
  }
  useEffect(autosize, [input])

  const groups = useMemo(() => groupConversations(conversations), [conversations])

  /* ---- actions ---- */
  const newChat = () => {
    setActiveId(null)
    setMessages([])
    navigate('/discussion')
  }

  const openChat = (id) => {
    setActiveId(id)
    if (id !== conversationId) navigate(`/discussion/${id}`)
  }

  const renameChat = async (id, e) => {
    e.stopPropagation()
    const conv = conversations.find(c => c.id === id)
    const title = window.prompt('Rename conversation', conv?.title || '')
    if (!title) return
    try {
      await api.updateConversation(id, { title })
      refreshConversations()
    } catch (err) { setError(String(err.message || err)) }
  }

  const deleteChat = async (id, e) => {
    e.stopPropagation()
    const conv = conversations.find(c => c.id === id)
    if (!window.confirm(`Delete conversation "${conv?.title || 'Untitled'}"? This cannot be undone.`)) return
    try {
      await api.deleteConversation(id)
      refreshConversations()
      if (id === activeId) newChat()
    } catch (err) { setError(String(err.message || err)) }
  }

  const send = async (text) => {
    const content = (text ?? input).trim()
    if (!content || loading) return
    setError('')

    let convId = activeId
    if (!convId) {
      // create the conversation lazily on the first message;
      // title = first ~50 chars of the user message (no LLM call)
      const conv = await api.createConversation({
        title: content.slice(0, 50),
        dataset_id: datasetId,
      })
      convId = conv.id
      setActiveId(convId)
      navigate(`/discussion/${convId}`)
    }

    const userMsg = { id: 'local-' + Date.now(), role: 'user', content }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const reply = await api.sendMessage(convId, { content, dataset_id: datasetId })
      setMessages(prev => [...prev.filter(m => m.id !== userMsg.id), userMsg, reply])
      refreshConversations()
    } catch (err) {
      setMessages(prev => prev.filter(m => m.id !== userMsg.id))
      setError(String(err.message || err))
    } finally {
      setLoading(false)
    }
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  /* ---- render ---- */
  return (
    <div className="discussion">
      {/* -------- left: conversation history -------- */}
      <aside className="discussion-side">
        <button className="btn btn-primary btn-new-chat" onClick={newChat}>
          ＋ New chat
        </button>
        <div className="discussion-list">
          {groups.length === 0 && (
            <div className="discussion-empty-side">No conversations yet</div>
          )}
          {groups.map(g => (
            <div key={g.label} className="chat-group">
              <div className="chat-group-label">{g.label}</div>
              {g.items.map(c => (
                <div
                  key={c.id}
                  className={'chat-item' + (c.id === activeId ? ' active' : '')}
                  onClick={() => openChat(c.id)}
                  title={c.title}
                >
                  <div className="chat-item-body">
                    <div className="chat-item-title">{c.title}</div>
                    <div className="chat-item-meta">
                      {relativeDate(c.updated_at)}
                      {c.message_count ? ` · ${c.message_count} msgs` : ''}
                    </div>
                  </div>
                  <div className="chat-item-actions">
                    <button className="icon-btn" title="Rename" onClick={(e) => renameChat(c.id, e)}>✎</button>
                    <button className="icon-btn icon-btn-danger" title="Delete" onClick={(e) => deleteChat(c.id, e)}>🗑</button>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </aside>

      {/* -------- right: thread + input -------- */}
      <div className="discussion-main">
        {error && <div className="alert alert-error" onClick={() => setError('')}>{error}</div>}

        <div className="chat-thread" ref={threadRef}>
          {messages.length === 0 ? (
            <div className="chat-empty">
              <h2>Ask anything about your data</h2>
              <p className="chat-empty-sub">
                Select a dataset below, or chat generally about data engineering.
                Answers are grounded in the real data — never invented.
              </p>
              <div className="chat-examples">
                {EXAMPLE_QUESTIONS.map(q => (
                  <button key={q} className="chat-example" onClick={() => send(q)}>
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="chat-messages">
              {messages.map(m => <MessageBubble key={m.id} msg={m} />)}
              {loading && (
                <div className="chat-msg chat-msg-assistant">
                  <div className="bubble bubble-assistant typing">
                    <span className="dot" />
                    <span className="dot" />
                    <span className="dot" />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="chat-input-wrap">
          <div className="chat-input-bar">
            <select
              className="chat-dataset-select"
              value={datasetId || ''}
              onChange={e => setDatasetId(e.target.value || null)}
              title="Dataset to talk about"
            >
              <option value="">No dataset (general chat)</option>
              {datasets.map(d => (
                <option key={d.id} value={d.id}>
                  {d.name} · {d.file_type.toUpperCase()} · {d.row_count ?? '?'}×{d.column_count ?? '?'} · {formatDateTime(d.created_at)}
                </option>
              ))}
            </select>
            <textarea
              ref={taRef}
              className="chat-textarea"
              placeholder="Ask about the data…  (Enter to send, Shift+Enter for newline)"
              rows={1}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={onKeyDown}
            />
            <button
              className="btn btn-primary chat-send"
              onClick={() => send()}
              disabled={loading || !input.trim()}
              title="Send"
            >
              ➤
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

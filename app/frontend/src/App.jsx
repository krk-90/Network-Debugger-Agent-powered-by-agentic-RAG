import { useEffect, useMemo, useState } from 'react'
import { Activity, ChevronDown, Copy, LogOut, Menu, Network, Plus, Search, Send, Shield, Sparkles, Wifi, X } from 'lucide-react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const modes = ['Network Debugger', 'Quick Diagnosis', 'Deep Investigation', 'Security Analysis', 'Incident Analysis']

function App() {
  const [token, setToken] = useState(() => localStorage.getItem('nd_token') || '')
  const [user, setUser] = useState(null)
  const [login, setLogin] = useState({ email: '', password: '' })
  const [authMode, setAuthMode] = useState('login')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [mode, setMode] = useState(modes[0])
  const [drawer, setDrawer] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [context, setContext] = useState({ target: '', environment: 'Production', live: true, knowledge: true })

  useEffect(() => { if (token) fetchMe() }, [token])

  async function fetchMe() {
    try { const r = await fetch(`${API}/auth/me`, { headers: { Authorization: `Bearer ${token}` } }); if (!r.ok) throw Error(); setUser(await r.json()) }
    catch { localStorage.removeItem('nd_token'); setToken(''); setUser(null) }
  }

  async function authenticate(e) {
    e.preventDefault(); setError('')
    try {
      const path = authMode === 'login' ? '/auth/login' : '/auth/signup'
      const r = await fetch(`${API}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(login) })
      const data = await r.json()
      if (!r.ok) throw Error(data.detail || 'Authentication failed')
      if (data.access_token) { localStorage.setItem('nd_token', data.access_token); setToken(data.access_token) }
      else setError(data.message || 'Check your email to confirm your account.')
    } catch (e) { setError(e.message) }
  }

  async function diagnose() {
    const q = input.trim(); if (!q || loading) return
    const display = q
    setInput(''); setLoading(true); setError('')
    setMessages(m => [...m, { role: 'user', text: display }, { role: 'assistant', pending: true }])
    const enriched = `Mode: ${mode}\nTarget: ${context.target || 'not specified'}\nEnvironment: ${context.environment}\nLive diagnostics: ${context.live}\nKnowledge base: ${context.knowledge}\nUser request: ${display}`
    try {
      const r = await fetch(`${API}/`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ query: enriched }) })
      const data = await r.json(); if (!r.ok) throw Error(data.detail || 'Diagnosis failed')
      const result = data.results || data
      setMessages(m => [...m.slice(0, -1), { role: 'assistant', result }])
    } catch (e) { setMessages(m => [...m.slice(0, -1), { role: 'assistant', text: `I couldn't complete the diagnosis: ${e.message}` }]) }
    finally { setLoading(false) }
  }

  function newChat() { setMessages([]); setError('') }
  function logout() { localStorage.removeItem('nd_token'); setToken(''); setUser(null); newChat() }
  function share() { navigator.clipboard?.writeText(messages.map(m => `${m.role}: ${m.text || JSON.stringify(m.result || '')}`).join('\n\n')); setError('Conversation copied to clipboard. No access token was included.') }

  if (!token || !user) return <Auth mode={authMode} setMode={setAuthMode} values={login} setValues={setLogin} submit={authenticate} error={error} />

  return <div className="app">
    <aside className={`sidebar ${drawer ? 'open' : ''}`}>
      <div className="brand"><div className="logo"><Network size={20}/></div><div><b>Network Debugger</b><span>Agentic RAG</span></div><button className="icon-btn mobile" onClick={() => setDrawer(false)}><X/></button></div>
      <button className="new-chat" onClick={newChat}><Plus size={18}/> New investigation</button>
      <div className="side-section"><small>WORKSPACE</small><button className="side-active"><Sparkles size={16}/> AI Diagnostics</button><button><Search size={16}/> History</button><button><Shield size={16}/> Security</button></div>
      <div className="side-section"><small>MODE</small>{modes.map(x => <button key={x} className={mode === x ? 'mode-active' : ''} onClick={() => setMode(x)}><Activity size={15}/>{x}</button>)}</div>
      <div className="profile"><div className="avatar">{user.email?.[0]?.toUpperCase()}</div><div><b>{user.email}</b><span>Authenticated</span></div><button className="icon-btn" onClick={logout}><LogOut size={16}/></button></div>
    </aside>
    {drawer && <div className="backdrop" onClick={() => setDrawer(false)}/>} 
    <main className="main">
      <header><button className="icon-btn" onClick={() => setDrawer(true)}><Menu/></button><div className="header-title"><b>Network Debugger AI</b><span>{mode}</span></div><button className="share" onClick={share}><Copy size={15}/> Share</button></header>
      <section className="workspace">
        <div className="chat">
          {messages.length === 0 ? <Welcome mode={mode} setInput={setInput}/> : messages.map((m,i) => <Message key={i} message={m}/>) }
          {loading && <div className="typing"><span/><span/><span/> Agent is investigating…</div>}
        </div>
        <div className="context-panel"><div className="panel-head"><b>Investigation context</b><Wifi size={16}/></div><label>Target / domain / IP<input value={context.target} onChange={e=>setContext({...context,target:e.target.value})} placeholder="e.g. api.example.com"/></label><label>Environment<select value={context.environment} onChange={e=>setContext({...context,environment:e.target.value})}><option>Production</option><option>Staging</option><option>Development</option></select></label><label className="check"><input type="checkbox" checked={context.live} onChange={e=>setContext({...context,live:e.target.checked})}/> Use live diagnostics</label><label className="check"><input type="checkbox" checked={context.knowledge} onChange={e=>setContext({...context,knowledge:e.target.checked})}/> Use knowledge base</label><div className="status"><i/> Backend connected<br/><small>Supabase auth • Agentic RAG</small></div></div>
      </section>
      <div className="composer-wrap"><div className="composer"><textarea value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();diagnose()}}} placeholder="Describe a network issue…" rows="1"/><button onClick={diagnose} disabled={!input.trim() || loading}><Send size={18}/></button></div><small>Enter to diagnose • Shift+Enter for a new line</small></div>
      {error && <div className="toast">{error}</div>}
    </main>
  </div>
}

function Welcome({ mode, setInput }) { const cards=['Why is my API returning intermittent 504s?','Diagnose DNS resolution failures','Check TLS connectivity to my service','Investigate high network latency'] ; return <div className="welcome"><div className="hero-icon"><Network/></div><h1>Network diagnostics, <em>agentic.</em></h1><p>Investigate connectivity issues with live diagnostics, runbooks and your incident knowledge base.</p><div className="quick-grid">{cards.map(c=><button key={c} onClick={()=>setInput(c)}><Sparkles size={15}/>{c}</button>)}</div><div className="mode-pill">Current mode: <b>{mode}</b></div></div> }
function Message({ message }) { if (message.pending) return null; if (message.role==='user') return <div className="msg user-msg"><div className="bubble">{message.text}</div></div>; const result=message.result; return <div className="msg"><div className="agent-mark"><Network size={15}/></div><div className="answer">{message.text ? <p>{message.text}</p> : <Diagnostic result={result}/>}</div></div> }
function Diagnostic({ result }) { const entries = Object.entries(result || {}); return <div className="diagnostic"><div className="diagnosis-title"><span className="ok"><Activity size={16}/></span><div><b>Diagnostic result</b><small>Agent investigation complete</small></div></div>{entries.map(([k,v])=><div className="result-row" key={k}><span>{k.replaceAll('_',' ')}</span><pre>{typeof v==='string'?v:JSON.stringify(v,null,2)}</pre></div>)}</div> }
function Auth({mode,setMode,values,setValues,submit,error}) { return <div className="auth"><div className="auth-card"><div className="logo large"><Network/></div><h1>Network Debugger AI</h1><p>Secure agentic network investigation</p><form onSubmit={submit}><input type="email" placeholder="Email" required value={values.email} onChange={e=>setValues({...values,email:e.target.value})}/><input type="password" placeholder="Password" minLength="6" required value={values.password} onChange={e=>setValues({...values,password:e.target.value})}/><button className="primary">{mode==='login'?'Sign in':'Create account'}</button></form>{error&&<div className="auth-error">{error}</div>}<button className="switch" onClick={()=>setMode(mode==='login'?'signup':'login')}>{mode==='login'?'Need an account? Sign up':'Already have an account? Sign in'}</button></div></div> }

export default App

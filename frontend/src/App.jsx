import { useState, useEffect, useRef, useCallback } from 'react'
import Dashboard from './components/Dashboard'
import OpportunitiesPanel from './components/OpportunitiesPanel'
import OddsTable from './components/OddsTable'
import Calculator from './components/Calculator'
import StatusBar from './components/StatusBar'
import Login from './components/Login'
import { useLang } from './LanguageContext'
import './App.css'

const API_BASE = '/api'

export default function App() {
  const { t, toggle } = useLang()
  const [authToken, setAuthToken] = useState(() => localStorage.getItem('sb_token'))
  const [telegramActive, setTelegramActive] = useState(null) // null = loading
  const [activeTab, setActiveTab] = useState('dashboard')
  const [opportunities, setOpportunities] = useState([])
  const [odds, setOdds] = useState([])
  const [status, setStatus] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [wsConnected, setWsConnected] = useState(false)
  const [filters, setFilters] = useState({ sport: '', type: '', bookmaker: '' })
  const wsRef = useRef(null)
  const reconnectTimer = useRef(null)

  const addAlert = useCallback((msg, type = 'info') => {
    const id = Date.now()
    setAlerts(prev => [...prev.slice(-4), { id, msg, type }])
    setTimeout(() => setAlerts(prev => prev.filter(a => a.id !== id)), 6000)
  }, [])

  const handleLogout = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${authToken}` },
      })
    } catch { /* ignore */ }
    localStorage.removeItem('sb_token')
    setAuthToken(null)
  }, [authToken])

  // Fetch Telegram status once after login
  useEffect(() => {
    if (!authToken) return
    fetch(`${API_BASE}/telegram/status`, { headers: { Authorization: `Bearer ${authToken}` } })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setTelegramActive(d.active))
      .catch(() => {})
  }, [authToken])

  const handleTelegramToggle = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/telegram/toggle`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${authToken}` },
      })
      if (res.ok) {
        const data = await res.json()
        setTelegramActive(data.active)
        addAlert(`Telegram ${data.active ? 'activado' : 'desactivado'}`, data.active ? 'success' : 'info')
      }
    } catch { /* ignore */ }
  }, [authToken, addAlert])

  const connectWS = useCallback(() => {
    if (!authToken) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const wsUrl = `ws://${window.location.host}/ws?token=${authToken}`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setWsConnected(true)
      addAlert(t.wsConnectedAlert, 'success')
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)

        if (msg.type === 'init') {
          setOpportunities(msg.opportunities || [])
          setStatus(msg.status || null)
        } else if (msg.type === 'opportunity') {
          setOpportunities(prev => {
            const exists = prev.find(o => o.event_key === msg.data.event_key && o.market_type === msg.data.market_type)
            if (exists) {
              return prev.map(o =>
                o.event_key === msg.data.event_key && o.market_type === msg.data.market_type
                  ? msg.data : o
              )
            }
            return [msg.data, ...prev]
          })

          if (msg.data.opportunity_type === 'surebet') {
            addAlert(
              `🎯 SUREBET: ${msg.data.home_team} vs ${msg.data.away_team} | ${msg.data.profit_margin > 0 ? '+' : ''}${msg.data.profit_margin.toFixed(2)}%`,
              'surebet'
            )
          }
        } else if (msg.type === 'status') {
          setStatus(msg.data)
        }
      } catch (e) {
        // ignore parse errors
      }
    }

    ws.onclose = () => {
      setWsConnected(false)
      reconnectTimer.current = setTimeout(connectWS, 3000)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [addAlert, t, authToken])

  useEffect(() => {
    connectWS()
    return () => {
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connectWS])

  // Fetch odds when Odds tab is active
  useEffect(() => {
    if (activeTab !== 'odds' || !authToken) return
    const fetchOdds = async () => {
      try {
        const params = new URLSearchParams()
        if (filters.sport) params.set('sport', filters.sport)
        if (filters.bookmaker) params.set('bookmaker', filters.bookmaker)
        const res = await fetch(`${API_BASE}/odds?${params}`, {
          headers: { Authorization: `Bearer ${authToken}` },
        })
        if (res.status === 401) { handleLogout(); return }
        const data = await res.json()
        setOdds(data.odds || [])
      } catch (e) {
        addAlert(t.errorLoadingOdds, 'error')
      }
    }
    fetchOdds()
    const interval = setInterval(fetchOdds, 30000)
    return () => clearInterval(interval)
  }, [activeTab, filters.sport, filters.bookmaker, addAlert, t, authToken, handleLogout])

  const filteredOpportunities = opportunities.filter(o => {
    if (filters.type && o.opportunity_type !== filters.type) return false
    if (filters.sport && o.sport_code !== filters.sport) return false
    if (filters.bookmaker && !o.legs?.some(l => l.bookmaker === filters.bookmaker)) return false
    return true
  })

  const surebets = opportunities.filter(o => o.opportunity_type === 'surebet')
  const nearSurebets = opportunities.filter(o => o.opportunity_type === 'near_surebet')

  // Show login page if not authenticated
  if (!authToken) {
    return <Login onLogin={setAuthToken} />
  }

  return (
    <div className="app">
      {/* Alerts */}
      <div className="alerts-container">
        {alerts.map(alert => (
          <div key={alert.id} className={`alert alert-${alert.type}`}>
            {alert.msg}
          </div>
        ))}
      </div>

      {/* Header */}
      <header className="app-header">
        <div className="header-left">
          <span className="logo">🎯</span>
          <div>
            <h1 className="app-title">{t.appTitle}</h1>
            <p className="app-subtitle">{t.appSubtitle}</p>
          </div>
        </div>
        <div className="header-right">
          <button className="lang-toggle" onClick={toggle}>
            {t.langToggle}
          </button>
          <div className={`ws-indicator ${wsConnected ? 'connected' : 'disconnected'}`}>
            <span className="ws-dot" />
            {wsConnected ? t.wsLive : t.wsDisconnected}
          </div>
          {telegramActive !== null && (
            <button
              className={`tg-toggle ${telegramActive ? 'tg-on' : 'tg-off'}`}
              onClick={handleTelegramToggle}
              title={telegramActive ? 'Telegram ON — click to disable' : 'Telegram OFF — click to enable'}
            >
              <span className="tg-icon">✈</span>
              <span className="tg-label">{telegramActive ? 'ON' : 'OFF'}</span>
            </button>
          )}
          <button className="logout-btn" onClick={handleLogout} title="Sign out">
            ⏻
          </button>
        </div>
      </header>

      {/* Navigation */}
      <nav className="app-nav">
        {[
          { id: 'dashboard',     label: t.navDashboard },
          { id: 'opportunities', label: `${t.navOpportunities} (${filteredOpportunities.length})` },
          { id: 'odds',          label: t.navOdds },
          { id: 'calculator',    label: t.navCalculator },
        ].map(tab => (
          <button
            key={tab.id}
            className={`nav-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* Filters */}
      <div className="filters-bar">
        <select
          className="filter-select"
          value={filters.sport}
          onChange={e => setFilters(f => ({ ...f, sport: e.target.value }))}
        >
          <option value="">{t.allSports}</option>
          <option value="NBA">NBA</option>
          <option value="NFL">NFL</option>
          <option value="MLB">MLB</option>
          <option value="NHL">NHL</option>
          <option value="NCAAB">NCAA Basketball</option>
          <option value="NCAAF">NCAA Football</option>
          <option value="EUROL">EuroLiga</option>
          <option value="SOC">Soccer</option>
        </select>

        <select
          className="filter-select"
          value={filters.bookmaker}
          onChange={e => setFilters(f => ({ ...f, bookmaker: e.target.value }))}
        >
          <option value="">{t.allBookmakers}</option>
          <option value="HDLinea">🟢 HDLinea</option>
          <option value="Betcris">🔴 Betcris</option>
          <option value="JuancitoSport">🟡 JuancitoSport</option>
        </select>

        <select
          className="filter-select"
          value={filters.type}
          onChange={e => setFilters(f => ({ ...f, type: e.target.value }))}
        >
          <option value="">{t.allTypes}</option>
          <option value="surebet">{t.onlySurebets}</option>
          <option value="near_surebet">{t.onlyNearSurebets}</option>
        </select>

        <div className="filter-counts">
          <span className="count-badge surebet">{t.surebetsCount(surebets.length)}</span>
          <span className="count-badge near">{t.nearCount(nearSurebets.length)}</span>
        </div>
      </div>

      {/* Main Content */}
      <main className="app-main">
        {activeTab === 'dashboard' && (
          <Dashboard
            opportunities={filteredOpportunities}
            status={status}
            surebets={surebets}
            nearSurebets={nearSurebets}
          />
        )}
        {activeTab === 'opportunities' && (
          <OpportunitiesPanel opportunities={filteredOpportunities} />
        )}
        {activeTab === 'odds' && (
          <OddsTable odds={odds} />
        )}
        {activeTab === 'calculator' && (
          <Calculator />
        )}
      </main>
    </div>
  )
}

import { useLang } from '../LanguageContext'
import './OddsTable.css'

const BM_COLORS = {
  Betcris: '#e03131',
  JuancitoSport: '#f0b429',
  HDLinea: '#2f9e44',
}

export default function OddsTable({ odds }) {
  const { t } = useLang()

  if (odds.length === 0) {
    return (
      <div className="odds-empty">
        <div className="odds-empty-icon">📊</div>
        <h3>{t.loadingOdds}</h3>
        <p>{t.liveOddsAppear}</p>
      </div>
    )
  }

  const events = {}
  odds.forEach(o => {
    const key = `${o.sport}:${o.home_team}:${o.away_team}`
    if (!events[key]) {
      events[key] = { sport: o.sport, league: o.league, home_team: o.home_team, away_team: o.away_team, event_date: o.event_date, odds: [] }
    }
    events[key].odds.push(o)
  })

  const eventList = Object.values(events).slice(0, 100)

  return (
    <div className="odds-panel">
      <div className="odds-summary">
        <span>{t.oddsFromBookmakers(odds.length, new Set(odds.map(o => o.bookmaker)).size)}</span>
      </div>
      <div className="odds-events">
        {eventList.map((ev, i) => <EventRow key={i} event={ev} />)}
      </div>
    </div>
  )
}

function EventRow({ event }) {
  const { t } = useLang()
  const bookmakers = [...new Set(event.odds.map(o => o.bookmaker))]

  const getBestOdds = (outcome) => {
    const filtered = event.odds.filter(o => o.outcome === outcome)
    return filtered.length ? Math.max(...filtered.map(o => o.odds)) : null
  }

  const bestHome = getBestOdds('home')
  const bestAway = getBestOdds('away')

  return (
    <div className="event-row-card">
      <div className="event-row-header">
        <div className="event-teams">
          <span className="ev-sport">{event.sport}</span>
          <span className="ev-name">{event.home_team} <span>vs</span> {event.away_team}</span>
          <span className="ev-league">{event.league}</span>
        </div>
        {event.event_date && (
          <span className="ev-date">{new Date(event.event_date).toLocaleDateString('es-DO')}</span>
        )}
      </div>

      <div className="odds-grid-header">
        <span>{t.colBm}</span>
        <span>{t.colHome} ({event.home_team})</span>
        <span>{t.colAway} ({event.away_team})</span>
      </div>

      {bookmakers.map(bm => {
        const homeOdds = event.odds.find(o => o.bookmaker === bm && o.outcome === 'home')
        const awayOdds = event.odds.find(o => o.bookmaker === bm && o.outcome === 'away')
        return (
          <div key={bm} className="odds-grid-row">
            <span className="odds-bm-name" style={{ color: BM_COLORS[bm] || 'var(--text-primary)' }}>{bm}</span>
            <span className={`odds-val ${homeOdds?.odds === bestHome ? 'best-odds' : ''}`}>
              {homeOdds ? homeOdds.odds.toFixed(3) : '—'}
            </span>
            <span className={`odds-val ${awayOdds?.odds === bestAway ? 'best-odds' : ''}`}>
              {awayOdds ? awayOdds.odds.toFixed(3) : '—'}
            </span>
          </div>
        )
      })}

      <div className="odds-best-row">
        <span className="best-label">{t.bestAvailable}</span>
        <span className="best-val">{bestHome ? bestHome.toFixed(3) : '—'}</span>
        <span className="best-val">{bestAway ? bestAway.toFixed(3) : '—'}</span>
      </div>
    </div>
  )
}

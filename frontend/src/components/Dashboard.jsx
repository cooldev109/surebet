import { useMemo } from 'react'
import { useLang } from '../LanguageContext'
import './Dashboard.css'

const SPORTS_LABELS = {
  NBA: '🏀 NBA', NFL: '🏈 NFL', MLB: '⚾ MLB', NHL: '🏒 NHL',
  NCAAB: '🏀 NCAA-B', NCAAF: '🏈 NCAA-F', EUROL: '🏀 EuroLiga',
  SOC: '⚽ Soccer', EURO: '⚽ EuroCopa', UCL: '⚽ Champions',
}

export default function Dashboard({ opportunities, status, surebets, nearSurebets }) {
  const { t } = useLang()
  const bestSurebet = useMemo(() => surebets.sort((a, b) => b.profit_margin - a.profit_margin)[0] || null, [surebets])
  const sportBreakdown = useMemo(() => {
    const map = {}
    opportunities.forEach(o => { map[o.sport_code] = (map[o.sport_code] || 0) + 1 })
    return Object.entries(map).sort((a, b) => b[1] - a[1])
  }, [opportunities])
  const bookmakerBreakdown = useMemo(() => {
    const map = {}
    opportunities.forEach(o => { o.legs?.forEach(leg => { map[leg.bookmaker] = (map[leg.bookmaker] || 0) + 1 }) })
    return Object.entries(map).sort((a, b) => b[1] - a[1])
  }, [opportunities])

  return (
    <div className="dashboard">
      <div className="stats-grid">
        <StatCard label={t.activeSurebets} value={surebets.length} color="green" icon="🎯" sub={t.activeSurebetsSub} />
        <StatCard label={t.nearSurebets} value={nearSurebets.length} color="yellow" icon="⚡" sub={t.nearSurebetsSub} />
        <StatCard label={t.totalOdds} value={status?.total_odds ?? 0} color="blue" icon="📊" sub={t.totalOddsSub} />
        <StatCard
          label={t.bestMargin}
          value={bestSurebet ? `+${bestSurebet.profit_margin.toFixed(2)}%` : '—'}
          color={bestSurebet ? 'green' : 'dim'} icon="💰"
          sub={bestSurebet ? `${bestSurebet.home_team} vs ${bestSurebet.away_team}` : t.noActiveSurebets}
        />
      </div>

      <div className="dashboard-grid">
        <div className="dash-card">
          <h3 className="dash-card-title">{t.bestOpportunities}</h3>
          {opportunities.length === 0 ? (
            <div className="empty-state"><p>{t.monitoringOdds}</p><small>{t.opportunitiesWillAppear}</small></div>
          ) : (
            <div className="opportunities-mini">
              {opportunities.slice(0, 6).map((opp, i) => <MiniOpportunityCard key={i} opp={opp} />)}
            </div>
          )}
        </div>

        <div className="dash-card">
          <h3 className="dash-card-title">{t.opportunitiesBySport}</h3>
          {sportBreakdown.length === 0 ? <div className="empty-state"><p>{t.noDataYet}</p></div> : (
            <div className="breakdown-list">
              {sportBreakdown.map(([sport, count]) => (
                <div key={sport} className="breakdown-item">
                  <span className="breakdown-label">{SPORTS_LABELS[sport] || sport}</span>
                  <div className="breakdown-bar-wrap">
                    <div className="breakdown-bar" style={{ width: `${(count / opportunities.length) * 100}%` }} />
                  </div>
                  <span className="breakdown-count">{count}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="dash-card">
          <h3 className="dash-card-title">{t.bookmakersPanel}</h3>
          <div className="bookmaker-grid">
            {[
              { name: 'Betcris',       url: 'betcris.do',           icon: '🔴' },
              { name: 'JuancitoSport', url: 'juancitosport.com.do', icon: '🟡' },
              { name: 'HDLinea',       url: 'hdlinea.com.do',        icon: '🟢' },
            ].map(bm => (
              <div key={bm.name} className="bookmaker-card">
                <span className="bm-icon">{bm.icon}</span>
                <div>
                  <div className="bm-name">{bm.name}</div>
                  <div className="bm-url">{bm.url}</div>
                  <div className="bm-count">
                    {bookmakerBreakdown.find(([n]) => n === bm.name)?.[1] || 0} {t.activeLegs}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="dash-card">
          <h3 className="dash-card-title">{t.systemStatus}</h3>
          <div className="status-list">
            <StatusItem label={t.lastScrape} value={
              status?.last_scrape ? new Date(status.last_scrape).toLocaleTimeString('es-DO') : t.starting
            } />
            <StatusItem label={t.intervalLabel} value={t.intervalValue} />
            <StatusItem label={t.monitoredBookmakers} value="3" />
            <StatusItem label={t.activeSports} value="10" />
            {status?.errors?.length > 0 && (
              <div className="status-errors">
                <span className="status-error-title">{t.errorsLabel}</span>
                {status.errors.map((err, i) => <div key={i} className="status-error-item">{err}</div>)}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function StatCard({ label, value, color, icon, sub }) {
  return (
    <div className={`stat-card stat-${color}`}>
      <div className="stat-top"><span className="stat-icon">{icon}</span><span className="stat-value">{value}</span></div>
      <div className="stat-label">{label}</div>
      <div className="stat-sub">{sub}</div>
    </div>
  )
}

function MiniOpportunityCard({ opp }) {
  const isSure = opp.opportunity_type === 'surebet'
  const legs = opp.legs || []
  return (
    <div className={`mini-opp ${isSure ? 'mini-sure' : 'mini-near'}`}>
      <div className="mini-opp-header">
        <span className={`mini-badge ${isSure ? 'badge-sure' : 'badge-near'}`}>{isSure ? '🎯 SUREBET' : '⚡ NEAR'}</span>
        <span className={`mini-margin ${isSure ? 'margin-pos' : 'margin-neg'}`}>
          {opp.profit_margin > 0 ? '+' : ''}{opp.profit_margin.toFixed(3)}%
        </span>
      </div>
      <div className="mini-event">{opp.home_team} <span>vs</span> {opp.away_team}</div>
      <div className="mini-meta"><span>{opp.league}</span><span>{legs.map(l => l.bookmaker).join(' + ')}</span></div>
    </div>
  )
}

function StatusItem({ label, value }) {
  return (
    <div className="status-item">
      <span className="status-label">{label}</span>
      <span className="status-value">{value}</span>
    </div>
  )
}

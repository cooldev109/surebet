import { useState } from 'react'
import { useLang } from '../LanguageContext'
import './OpportunitiesPanel.css'

const SPORT_EMOJI = {
  NBA: '🏀', NFL: '🏈', MLB: '⚾', NHL: '🏒',
  NCAAB: '🏀', NCAAF: '🏈', EUROL: '🏀', SOC: '⚽', EURO: '⚽', UCL: '⚽',
}

export default function OpportunitiesPanel({ opportunities }) {
  const { t } = useLang()
  const [selected, setSelected] = useState(null)
  const [bankroll, setBankroll] = useState(1000)

  const handleSelect = (opp) => setSelected(prev => prev?.event_key === opp.event_key ? null : opp)

  if (opportunities.length === 0) {
    return (
      <div className="opp-empty">
        <div className="opp-empty-icon">🔍</div>
        <h3>{t.searchingOpportunities}</h3>
        <p>{t.monitoringRealTime}</p>
        <p>{t.arbitrageWillAppear}</p>
      </div>
    )
  }

  return (
    <div className="opp-panel">
      <div className="opp-list">
        {opportunities.map((opp, i) => (
          <OpportunityCard
            key={`${opp.event_key}-${i}`}
            opp={opp}
            isSelected={selected?.event_key === opp.event_key}
            onClick={() => handleSelect(opp)}
          />
        ))}
      </div>
      {selected && (
        <div className="opp-detail-panel">
          <OpportunityDetail opp={selected} bankroll={bankroll} setBankroll={setBankroll} />
        </div>
      )}
    </div>
  )
}

function OpportunityCard({ opp, isSelected, onClick }) {
  const { t } = useLang()
  const isSure = opp.opportunity_type === 'surebet'
  const emoji = SPORT_EMOJI[opp.sport_code] || '🎽'
  const legs = opp.legs || []

  return (
    <div className={`opp-card ${isSure ? 'opp-sure' : 'opp-near'} ${isSelected ? 'opp-selected' : ''}`} onClick={onClick}>
      <div className="opp-card-header">
        <div className="opp-badge-group">
          <span className={`opp-type-badge ${isSure ? 'type-sure' : 'type-near'}`}>
            {isSure ? '🎯 SUREBET' : '⚡ NEAR SUREBET'}
          </span>
          <span className="opp-sport-badge">{emoji} {opp.sport_code}</span>
        </div>
        <span className={`opp-margin ${isSure ? 'margin-green' : 'margin-yellow'}`}>
          {opp.profit_margin > 0 ? '+' : ''}{opp.profit_margin.toFixed(4)}%
        </span>
      </div>
      <div className="opp-event-name">
        <span className="opp-home">{opp.home_team}</span>
        <span className="opp-vs">vs</span>
        <span className="opp-away">{opp.away_team}</span>
      </div>
      <div className="opp-league">{opp.league}</div>
      <div className="opp-legs-summary">
        {legs.map((leg, i) => (
          <div key={i} className="opp-leg-chip">
            <span className="leg-bm">{leg.bookmaker}</span>
            <span className="leg-outcome">{leg.outcome}</span>
            <span className="leg-odds">{leg.odds.toFixed(3)}</span>
          </div>
        ))}
      </div>
      <div className="opp-footer">
        <span className="opp-ip">{t.totalProbShort} {(opp.total_implied_prob * 100).toFixed(2)}%</span>
        <span className="opp-click-hint">{t.clickForDetails}</span>
      </div>
    </div>
  )
}

function OpportunityDetail({ opp, bankroll, setBankroll }) {
  const { t } = useLang()
  const isSure = opp.opportunity_type === 'surebet'
  const legs = opp.legs || []

  const stakeDetails = legs.map(leg => ({
    ...leg,
    stake: (bankroll * leg.stake_percent / 100).toFixed(2),
    payout: (bankroll * leg.stake_percent / 100 * leg.odds).toFixed(2),
  }))

  const minPayout = Math.min(...stakeDetails.map(s => parseFloat(s.payout)))
  const profit = (minPayout - bankroll).toFixed(2)
  const roi = ((minPayout - bankroll) / bankroll * 100).toFixed(4)

  return (
    <div className="detail-panel">
      <div className="detail-header">
        <h3>
          <span className={`detail-type ${isSure ? 'type-sure' : 'type-near'}`}>
            {isSure ? '🎯 SUREBET' : '⚡ NEAR SUREBET'}
          </span>
          {' '}{opp.home_team} vs {opp.away_team}
        </h3>
        <div className="detail-meta">
          <span>{opp.league}</span><span>·</span>
          <span>{opp.market_type}</span><span>·</span>
          <span>{opp.sport_code}</span>
        </div>
      </div>

      <div className="detail-metrics">
        <div className="metric">
          <div className="metric-val" style={{ color: isSure ? 'var(--green)' : 'var(--yellow)' }}>
            {opp.profit_margin > 0 ? '+' : ''}{opp.profit_margin.toFixed(4)}%
          </div>
          <div className="metric-label">{t.marginLabel}</div>
        </div>
        <div className="metric">
          <div className="metric-val">{(opp.total_implied_prob * 100).toFixed(3)}%</div>
          <div className="metric-label">{t.totalProbLabel}</div>
        </div>
        <div className="metric">
          <div className="metric-val" style={{ color: 'var(--green)' }}>{isSure ? t.guaranteed : t.high}</div>
          <div className="metric-label">{t.profitability}</div>
        </div>
      </div>

      <div className="bankroll-section">
        <label className="bankroll-label">{t.bankrollLabel}</label>
        <input type="number" className="bankroll-input" value={bankroll}
          onChange={e => setBankroll(Math.max(1, parseFloat(e.target.value) || 0))} min="1" step="100" />
      </div>

      <div className="stakes-section">
        <h4 className="stakes-title">{t.betDistribution}</h4>
        <div className="stakes-table">
          <div className="stakes-head">
            <span>{t.colBookmaker}</span><span>{t.colTeam}</span><span>{t.colOutcome}</span>
            <span>{t.colOdds}</span><span>{t.colBetPct}</span><span>{t.colAmount}</span><span>{t.colPayout}</span>
          </div>
          {stakeDetails.map((leg, i) => (
            <div key={i} className="stakes-row">
              <span className="stake-bm">{leg.bookmaker}</span>
              <span className="stake-team">{leg.team}</span>
              <span className={`stake-outcome outcome-${leg.outcome}`}>{leg.outcome}</span>
              <span className="stake-odds">{leg.odds.toFixed(3)}</span>
              <span className="stake-pct">{leg.stake_percent.toFixed(2)}%</span>
              <span className="stake-amount">RD${leg.stake}</span>
              <span className="stake-payout">RD${leg.payout}</span>
            </div>
          ))}
        </div>
      </div>

      <div className={`profit-summary ${isSure ? 'profit-positive' : 'profit-warn'}`}>
        <div className="profit-row"><span>{t.totalInvested}</span><span>RD${bankroll.toFixed(2)}</span></div>
        <div className="profit-row"><span>{t.minPayout}</span><span>RD${minPayout.toFixed(2)}</span></div>
        <div className="profit-row profit-main">
          <span>{t.netProfit}</span>
          <span style={{ color: parseFloat(profit) > 0 ? 'var(--green)' : 'var(--red)' }}>
            {parseFloat(profit) > 0 ? '+' : ''}RD${profit}
          </span>
        </div>
        <div className="profit-row"><span>{t.roi}</span><span>{parseFloat(roi) > 0 ? '+' : ''}{roi}%</span></div>
      </div>

      {!isSure && (
        <div className="warning-box">
          ⚠️ <strong>Near Surebet:</strong> {t.nearSurebetWarning}
        </div>
      )}
    </div>
  )
}

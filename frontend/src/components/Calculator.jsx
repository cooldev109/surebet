import { useState } from 'react'
import { useLang } from '../LanguageContext'
import './Calculator.css'

export default function Calculator() {
  const { t } = useLang()
  const [mode, setMode] = useState('2way')
  const [oddsA, setOddsA] = useState('')
  const [oddsB, setOddsB] = useState('')
  const [oddsC, setOddsC] = useState('')
  const [bankroll, setBankroll] = useState(1000)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const calculate = async () => {
    if (!oddsA || !oddsB) return
    if (mode === '3way' && !oddsC) return
    setLoading(true)
    try {
      const params = new URLSearchParams({ odds_a: oddsA, odds_b: oddsB, bankroll })
      if (mode === '3way' && oddsC) params.set('odds_c', oddsC)
      const res = await fetch(`/api/calculator?${params}`)
      const data = await res.json()
      setResult(data)
    } catch (e) {
      alert(t.calcError)
    }
    setLoading(false)
  }

  const reset = () => { setOddsA(''); setOddsB(''); setOddsC(''); setResult(null) }

  return (
    <div className="calc-panel">
      <div className="calc-card">
        <h2 className="calc-title">{t.calcTitle}</h2>
        <p className="calc-desc">{t.calcDesc}</p>

        <div className="mode-tabs">
          <button className={`mode-tab ${mode === '2way' ? 'active' : ''}`} onClick={() => { setMode('2way'); setResult(null) }}>
            {t.twoWay}
          </button>
          <button className={`mode-tab ${mode === '3way' ? 'active' : ''}`} onClick={() => { setMode('3way'); setResult(null) }}>
            {t.threeWay}
          </button>
        </div>

        <div className="calc-inputs">
          <div className="calc-input-group">
            <label>{t.oddsALabel}</label>
            <div className="input-wrap">
              <input type="number" className="calc-input" placeholder="2.10" value={oddsA}
                onChange={e => setOddsA(e.target.value)} min="1.01" step="0.01" />
              {oddsA && <span className="implied-prob">P: {(1/parseFloat(oddsA)*100).toFixed(1)}%</span>}
            </div>
          </div>

          {mode === '3way' && (
            <div className="calc-input-group">
              <label>{t.oddsBDrawLabel}</label>
              <div className="input-wrap">
                <input type="number" className="calc-input" placeholder="3.20" value={oddsB}
                  onChange={e => setOddsB(e.target.value)} min="1.01" step="0.01" />
                {oddsB && <span className="implied-prob">P: {(1/parseFloat(oddsB)*100).toFixed(1)}%</span>}
              </div>
            </div>
          )}

          <div className="calc-input-group">
            <label>{mode === '3way' ? t.oddsCLabel : t.oddsBAwayLabel}</label>
            <div className="input-wrap">
              <input type="number" className="calc-input" placeholder="1.85"
                value={mode === '2way' ? oddsB : oddsC}
                onChange={e => mode === '2way' ? setOddsB(e.target.value) : setOddsC(e.target.value)}
                min="1.01" step="0.01" />
              {(mode === '2way' ? oddsB : oddsC) && (
                <span className="implied-prob">
                  P: {(1/parseFloat(mode === '2way' ? oddsB : oddsC)*100).toFixed(1)}%
                </span>
              )}
            </div>
          </div>

          <div className="calc-input-group">
            <label>{t.bankrollLabel}</label>
            <input type="number" className="calc-input" value={bankroll}
              onChange={e => setBankroll(Math.max(1, parseFloat(e.target.value) || 1))} min="1" step="100" />
          </div>
        </div>

        <div className="calc-actions">
          <button className="calc-btn-primary" onClick={calculate} disabled={loading}>
            {loading ? t.calculating : t.calculateBtn}
          </button>
          <button className="calc-btn-secondary" onClick={reset}>{t.clearBtn}</button>
        </div>

        <div className="converter-section">
          <h4>{t.convertTitle}</h4>
          <AmericanConverter />
        </div>
      </div>

      {result && (
        <div className={`calc-result ${result.is_surebet ? 'result-surebet' : 'result-no'}`}>
          <div className="result-header">
            {result.is_surebet
              ? <span className="result-badge badge-yes">{t.surebetConfirmed}</span>
              : <span className="result-badge badge-no">{t.noSurebet}</span>
            }
            <span className="result-ip">{t.totalProbShort} {(result.total_implied_prob * 100).toFixed(4)}%</span>
          </div>

          <div className="result-margin">
            <span>{t.profitMarginLabel}</span>
            <span className={result.profit_margin > 0 ? 'margin-pos' : 'margin-neg'}>
              {result.profit_margin > 0 ? '+' : ''}{result.profit_margin.toFixed(4)}%
            </span>
          </div>

          <div className="result-stakes">
            <h4>{t.optimalBets}</h4>
            <div className="result-stakes-table">
              <div className="rst-head">
                <span>{t.colOutcome}</span>
                <span>{t.colAmountToBet}</span>
                <span>{t.colPctBankroll}</span>
                <span>{t.colPayoutIfWins}</span>
                <span>{t.colNetProfit}</span>
              </div>
              {result.legs?.map((leg, i) => (
                <div key={i} className="rst-row">
                  <span className="rst-outcome">{leg.outcome}</span>
                  <span className="rst-stake">RD${leg.stake.toFixed(2)}</span>
                  <span className="rst-pct">{leg.stake_pct.toFixed(2)}%</span>
                  <span className="rst-payout">RD${leg.payout.toFixed(2)}</span>
                  <span className={`rst-profit ${leg.profit > 0 ? 'p-pos' : 'p-neg'}`}>
                    {leg.profit > 0 ? '+' : ''}RD${leg.profit.toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {!result.is_surebet && (
            <div className="result-tip">
              💡 {t.noSurebetTip((result.total_implied_prob * 100).toFixed(2))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function AmericanConverter() {
  const { t } = useLang()
  const [american, setAmerican] = useState('')
  const [decimal, setDecimal] = useState(null)

  const convert = () => {
    const val = parseInt(american)
    if (isNaN(val)) return
    setDecimal(val > 0 ? (1 + val / 100).toFixed(4) : (1 + 100 / Math.abs(val)).toFixed(4))
  }

  return (
    <div className="converter">
      <div className="converter-input-group">
        <input type="text" className="conv-input" placeholder={t.americanPlaceholder}
          value={american} onChange={e => setAmerican(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && convert()} />
        <button className="conv-btn" onClick={convert}>{t.convertBtn}</button>
      </div>
      {decimal && (
        <div className="conv-result">
          <span>{american} {t.americanWord}</span>
          <span className="conv-arrow">→</span>
          <strong>{decimal} {t.decimalWord}</strong>
          <span className="conv-prob">({(1/parseFloat(decimal)*100).toFixed(2)}% {t.impliedProbWord})</span>
        </div>
      )}
    </div>
  )
}

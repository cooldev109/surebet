import { useLang } from '../LanguageContext'

export default function StatusBar({ status, wsConnected }) {
  const { t } = useLang()
  if (!status) return null

  return (
    <div className="status-bar">
      <span className={`ws-dot ${wsConnected ? 'alive' : 'dead'}`} />
      <span>{status.total_odds} {t.oddsWord}</span>
      <span>·</span>
      <span>{status.total_surebets} {t.surebetsWord}</span>
      {status.last_scrape && (
        <>
          <span>·</span>
          <span>{t.updatedLabel} {new Date(status.last_scrape).toLocaleTimeString()}</span>
        </>
      )}
    </div>
  )
}

import { useEffect, useState } from "react";
import { getAlerts, searchLocations } from "../api/client.js";


function AlertCard({ alert }) {
  return (
    <article className={`alert-card alert-${alert.severity}`}>
      <div className="alert-heading">
        <div>
          <p className="alert-date">{alert.date}</p>
          <h3>{alert.kind === "spike" ? "Activity spike" : "Activity drop"}</h3>
        </div>
        <span className="severity">{alert.severity}</span>
      </div>
      <p>{alert.message}</p>
      <dl className="alert-metrics">
        <div><dt>Observed</dt><dd>{alert.actual_transactions}</dd></div>
        <div><dt>Typical</dt><dd>{alert.expected_transactions}</dd></div>
        <div><dt>Difference</dt><dd>{alert.difference > 0 ? "+" : ""}{alert.difference}</dd></div>
      </dl>
    </article>
  );
}


export default function Alerts() {
  const [state, setState] = useState({ loading: true, data: null, error: "" });
  const [query, setQuery] = useState("");
  const [locations, setLocations] = useState([]);

  useEffect(() => {
    getAlerts()
      .then((data) => setState({ loading: false, data, error: "" }))
      .catch((error) => setState({ loading: false, data: null, error: error.message }));
  }, []);

  async function submitSearch(event) {
    event.preventDefault();
    try {
      const result = await searchLocations(query);
      setLocations(result.results);
    } catch (error) {
      setState((current) => ({ ...current, error: error.message }));
    }
  }

  return (
    <section className="alerts-page" aria-labelledby="alerts-title">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Daily transaction monitoring</p>
          <h1 id="alerts-title">Review alerts</h1>
          <p>Flags use comparable historical weekdays and exclude calendar-explained dates.</p>
        </div>
        <form className="location-search" onSubmit={submitSearch} role="search">
          <label htmlFor="location-query">Find your location</label>
          <div><input id="location-query" value={query} onChange={(event) => setQuery(event.target.value)} /><button>Search</button></div>
        </form>
      </div>

      {locations.map((location) => <p className="location-result" key={location.vendor_id}>{location.name} · {location.address}</p>)}
      {state.loading && <div className="status-panel">Assessing available history…</div>}
      {state.error && <div className="status-panel error">{state.error}</div>}
      {state.data?.status === "not_assessed" && <div className="status-panel"><h2>Not assessed</h2><p>{state.data.message}</p></div>}
      {state.data?.status === "ready" && (
        <>
          <div className="summary-row">
            <span>{state.data.vendor?.name}</span>
            <span>{state.data.assessed_days} days assessed</span>
            <span>{state.data.alerts.length} alerts shown</span>
          </div>
          <div className="alerts-grid">
            {state.data.alerts.length ? state.data.alerts.map((alert) => <AlertCard alert={alert} key={`${alert.date}-${alert.kind}`} />) : <div className="status-panel">No unexplained unusual activity was found.</div>}
          </div>
        </>
      )}
    </section>
  );
}

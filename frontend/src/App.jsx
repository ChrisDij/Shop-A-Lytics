import Alerts from "./pages/Alerts.jsx";


export default function App() {
  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/">Shop-A-Lytics</a>
        <nav aria-label="Primary navigation"><a href="#alerts">Alerts</a></nav>
      </header>
      <main id="alerts"><Alerts /></main>
    </div>
  );
}

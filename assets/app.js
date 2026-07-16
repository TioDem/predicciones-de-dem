async function loadSnapshot() {
  const app = document.getElementById("app");
  try {
    const res = await fetch("data/snapshot.json", { cache: "no-store" });
    if (!res.ok) throw new Error("no se encontró data/snapshot.json todavía");
    const data = await res.json();
    render(data);
  } catch (err) {
    app.innerHTML = `<p class="loading">Todavía no hay snapshot generado. Corre el workflow de GitHub Actions (pestaña Actions → Actualizar predicciones → Run workflow).</p>`;
    console.error(err);
  }
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("es-MX", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

function legRow(leg) {
  const edgeClass = leg.edge > 0 ? "edge-pos" : (leg.edge < 0 ? "edge-neg" : "");
  const edgeText = leg.edge ? `${(leg.edge * 100).toFixed(1)}%` : "—";
  return `
    <div class="leg">
      <div>
        <div class="league-label">${leg.league} · ${fmtDate(leg.date_utc)}</div>
        <div>${leg.match}</div>
        <div class="pick">${leg.market}: ${leg.pick}</div>
      </div>
      <div style="text-align:right">
        <div class="odds">@ ${leg.odds_used}</div>
        <div class="${edgeClass}">value: ${edgeText}</div>
      </div>
    </div>
  `;
}

function parlayCard(title, tagText, parlay) {
  if (!parlay || parlay.status === "no_bet") {
    return `
      <div class="parlay-card no-bet">
        <div class="parlay-title">
          <strong>${title}</strong>
          <span class="tag">No bet</span>
        </div>
        <p style="color:var(--muted); margin:0;">
          No se recomienda apostar hoy: ningún partido cumple el mínimo de confianza/valor.
        </p>
      </div>
    `;
  }

  const legsHtml = parlay.legs.map(legRow).join("");
  return `
    <div class="parlay-card">
      <div class="parlay-title">
        <strong>${title}</strong>
        <span class="tag">${tagText}</span>
      </div>
      ${legsHtml}
      <div class="combined">
        <span>Cuota combinada: <strong>${parlay.combined_odds}</strong></span>
        <span>Prob. combinada modelo: <strong>${(parlay.combined_prob * 100).toFixed(1)}%</strong></span>
      </div>
    </div>
  `;
}

function matchCard(league, m) {
  const odds = m.odds
    ? Object.entries(m.odds).map(([k, v]) => `${k}: ${v}`).join(" · ")
    : "sin cuotas todavía";
  return `
    <div class="match-card">
      <div class="league-label">${league}</div>
      <div class="teams">${m.home_team} vs ${m.away_team}</div>
      <div style="color:var(--muted); font-size:0.8rem;">${fmtDate(m.date_utc)} · ${odds}</div>
    </div>
  `;
}

function render(data) {
  const app = document.getElementById("app");
  const genDate = fmtDate(data.generated_at_utc);

  let html = `
    <p class="meta-row">
      Generado: ${genDate} · motor: ${data.engine_version} · hash: ${data.snapshot_hash}
    </p>

    <section class="block">
      <h2>Apuesta del día</h2>
      ${parlayCard("Parlay seguro", "menor riesgo relativo", data.parlay_seguro)}
      ${parlayCard("Parlay arriesgado", "mayor value", data.parlay_arriesgado)}
      <p style="color:var(--muted); font-size:0.8rem;">
        Estos parlays son apoyo, no una orden — la última decisión es tuya.
      </p>
    </section>
  `;

  const leagues = data.leagues.football || {};
  for (const [key, leagueData] of Object.entries(leagues)) {
    if (!leagueData.matches || leagueData.matches.length === 0) continue;
    html += `
      <section class="block">
        <h2>${leagueData.league_name}</h2>
        ${leagueData.matches.map(m => matchCard(leagueData.league_name, m)).join("")}
      </section>
    `;
  }

  const nba = data.leagues.nba;
  if (nba && nba.matches && nba.matches.length > 0) {
    html += `
      <section class="block">
        <h2>NBA</h2>
        ${nba.matches.map(m => matchCard("NBA", m)).join("")}
      </section>
    `;
  }

  app.innerHTML = html;
}

loadSnapshot();

const $ = (id) => document.getElementById(id);
const LEAF = "TOR";

const TERMS = {
  PTS: "Points. A win is worth 2. An overtime or shootout loss is worth 1. The standings are sorted on this number.",
  "PTS%": "Points percentage: points divided by the maximum available (2 per game). This is how clubs are compared when they have not played the same number of games.",
  RW: "Regulation wins. The first tiebreaker after points. Overtime and shootout wins do not count.",
  ROW: "Regulation plus overtime wins. The second tiebreaker. Shootout wins are excluded.",
  Diff: "Goal differential: goals for minus goals against. A quick read on whether the points total is real.",
  xPTS: "Expected points from goal differential. The points total the scoring margin says the club 'should' have.",
  L10: "Points and record over the last 10 games. A perfect 10-game run is 20 points.",
  GR: "Games remaining. Each one is worth as many as 2 points.",
  Pace: "Current points rate stretched across the full regular-season schedule.",
  Path: "Top three in the division is an automatic berth. Otherwise the club is in the wild-card pool.",
  WC: "Wild card: the two Eastern berths left after the three Atlantic and three Metropolitan qualifiers.",
  Odds: "Share of simulated seasons in which Toronto finishes top three in the Atlantic or grabs a wild card.",
  SOS: "Strength of the remaining schedule: the average points rate of the opponents still left.",
  Series: "Games against Toronto on this regular-season schedule.",
  SO: "Shootout wins. They are worth two points, but they do not count as regulation wins or as ROW.",
  GP: "Games played.",
  "W-L-OT": "Wins, regulation losses, and overtime or shootout losses.",
};

function term(code, label = code) {
  const def = TERMS[code];
  if (!def) return esc(label);
  return `<abbr class="term" tabindex="0" title="${esc(def)}" data-tip="${esc(def)}">${esc(label)}</abbr>`;
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function fmtDate(iso, withTime = false) {
  if (!iso) return "";
  if (!withTime && /^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    const [year, month, day] = iso.split("-").map(Number);
    return new Intl.DateTimeFormat("en-CA", {
      weekday: "short", month: "short", day: "numeric",
    }).format(new Date(year, month - 1, day));
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const opts = withTime
    ? { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/Toronto" }
    : { weekday: "short", month: "short", day: "numeric", timeZone: "America/Toronto" };
  return new Intl.DateTimeFormat("en-CA", opts).format(date);
}

function relativeTime(iso) {
  const date = new Date(iso);
  const mins = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return fmtDate(iso, true);
}

function ptsPct(value) {
  if (value == null || value === "") return "—";
  const text = Number(value).toFixed(3);
  return text.startsWith("0") ? text.slice(1) : text;
}

function signed(value) {
  if (value == null || value === "") return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return "—";
  return `${n > 0 ? "+" : ""}${n}`;
}

function trendBadge(direction, text) {
  if (!direction || direction === "flat") {
    return text ? `<span class="trend flat">${esc(text)}</span>` : "";
  }
  const arrow = direction === "up" ? "▲" : "▼";
  return `<span class="trend ${esc(direction)}">${arrow} ${esc(text || "")}</span>`;
}

function teamCell(team) {
  return `<div class="team-cell">
    <img src="${esc(team.logo)}" alt="" />
    <span>${esc(team.abbr)}</span>
  </div>`;
}

function renderTicker(data) {
  const line = (data.ticker || []).join("   •   ") + "   •   ";
  $("tickerTrack").textContent = line + line;
}

function renderConclusion(data) {
  const out = Boolean(data.eliminated);
  document.body.classList.toggle("season-over", out);
  const banner = $("conclusion");
  if (banner) banner.hidden = !out;
}

function renderHero(data) {
  const narrative = data.narrative || {};
  const meters = data.meters || {};
  const primary = meters.primary || {};
  const third = meters.third || data.magicNumber || {};
  const odds = data.playoffOdds || {};
  $("statusKicker").textContent = narrative.kicker || "";
  $("headline").textContent = narrative.headline || "";
  $("blurb").textContent = narrative.blurb || "";
  $("primaryLabel").textContent = primary.label || "Points back of the cut line";
  $("primaryGiant").textContent = primary.value ?? "—";
  $("primarySub").textContent = primary.sub || "";
  const heat = primary.heat ?? 0;
  $("heatName").textContent = primary.heatLabel || "Points rate";
  $("heatValue").textContent = primary.heatText || `${heat}`;
  $("heatFill").style.width = `${Math.max(0, Math.min(100, heat))}%`;
  $("heroChips").innerHTML = (data.chips || [])
    .map((chip) => `<div class="chip"><span>${esc(chip.label)}</span><strong>${esc(chip.value)}</strong></div>`)
    .join("");
  const pct = odds.percent;
  $("oddsGiant").textContent = pct == null ? "—" : `${pct}%`;
  $("oddsLine").textContent = odds.sims
    ? `${Number(odds.sims).toLocaleString("en-CA")} sims · ${data.seasonGames || "—"} game schedule`
    : "";
  $("oddsNote").textContent = odds.note || "";
  const oddsCard = document.querySelector(".hero-score.odds");
  if (oddsCard) {
    oddsCard.classList.remove("longshot", "toss-up", "live");
    if (pct == null) {
      /* leave the default treatment */
    } else if (pct < 25) {
      oddsCard.classList.add("longshot");
    } else if (pct < 45) {
      oddsCard.classList.add("toss-up");
    } else {
      oddsCard.classList.add("live");
    }
  }
  $("magicLabel").textContent = third.label || "Magic number to clinch";
  $("magicGiant").textContent = third.value ?? "—";
  $("magicLine").textContent = third.sub || "";
  $("magicNote").textContent = third.note || "";
  $("updatePill").textContent = `Updated ${relativeTime(data.generatedAt)}`;
  $("seasonPill").textContent = data.eliminated
    ? `${data.season} season over`
    : `${data.season} East`;
  if (data.legend) {
    $("legendIn").textContent = data.legend.in || "In a playoff spot";
    $("legendOut").textContent = data.legend.out || "Outside";
  }
}

function renderKpis(data) {
  $("kpis").innerHTML = (data.kpis || []).map((kpi) => `
    <article class="kpi">
      <div class="label">${kpi.stat ? term(kpi.stat, kpi.label) : esc(kpi.label)}</div>
      <div class="value">${esc(kpi.value)}</div>
      <div class="hint">${esc(kpi.hint || "")}</div>
    </article>
  `).join("");
}

function renderTrends(data) {
  const preview = data.mode === "preview";
  $("trendBlurb").textContent = preview
    ? `Where Toronto stood at the end of ${data.timeframe}, which is the hole this season has to climb out of.`
    : "The gaps that decide April, and whether the points are coming at home or on the road.";
  $("trends").innerHTML = (data.trends || []).map((card) => `
    <article class="trend-card ${esc(card.direction || "flat")}">
      <div class="label">${card.stat ? term(card.stat, card.label) : esc(card.label)}</div>
      <div class="value">${esc(card.value)} ${trendBadge(card.direction, "")}</div>
      <div class="hint">${esc(card.detail || "")}</div>
    </article>
  `).join("");
}

function renderPaths(data) {
  $("paths").innerHTML = ["division", "wildcard"].map((key) => {
    const path = (data.paths || {})[key] || {};
    return `<article class="path-card${path.in ? " in-path" : ""}">
      <h4>${esc(path.title || "")}</h4>
      <div class="path-num">${esc(path.value || "—")}</div>
      <p class="meta">${esc(path.detail || "")}</p>
    </article>`;
  }).join("");
}

function headerRow(labels) {
  return `<tr>${labels.map((label) => `<th>${label}</th>`).join("")}</tr>`;
}

function renderConference(data) {
  const preview = data.mode === "preview";
  $("tableBlurb").textContent = data.tableBlurb || "";
  const head = preview
    ? ["#", "Team", term("Path", "Path"), term("W-L-OT", "W-L-OT"), term("PTS"), term("PTS%"), term("RW"), term("Diff", "Diff"), term("Series", "vs TOR")]
    : ["#", "Team", term("Path", "Path"), term("GP"), term("W-L-OT", "W-L-OT"), term("PTS"), term("PTS%"), term("RW"), term("Diff", "Diff"), term("L10"), term("GR")];
  document.querySelector("#conferenceTable thead").innerHTML = headerRow(head);
  document.querySelector("#conferenceTable tbody").innerHTML = (data.conference || []).map((team) => {
    const classes = [
      team.inField ? "row-in" : "",
      team.isLeafs ? "row-jays" : "",
      team.isCut ? "row-cut" : "",
    ].filter(Boolean).join(" ");
    const cut = team.isCut ? `<div class="cut-note">Last berth</div>` : "";
    const tail = preview
      ? `<td>${team.isLeafs ? "—" : esc(team.vsLeafs ?? 0)}</td>`
      : `<td>${esc(team.l10 || "—")}</td><td>${esc(team.gr ?? "—")}</td>`;
    return `<tr class="${classes}">
      <td>${esc(team.rank)}${cut}</td>
      <td>${teamCell(team)}${team.isLeafs ? " ★" : ""}</td>
      <td>${esc(team.path)}</td>
      ${preview ? "" : `<td>${esc(team.gp)}</td>`}
      <td>${esc(team.record)}</td>
      <td>${esc(team.points)}</td>
      <td>${esc(ptsPct(team.pointPct))}</td>
      <td>${esc(team.rw)}</td>
      <td>${esc(signed(team.diff))}</td>
      ${tail}
    </tr>`;
  }).join("");
}

function renderAtlantic(data) {
  const preview = data.mode === "preview";
  const head = preview
    ? ["#", "Team", term("W-L-OT", "W-L-OT"), term("PTS"), term("RW"), "Home", "Road", term("Series", "vs TOR")]
    : ["#", "Team", term("GP"), term("W-L-OT", "W-L-OT"), term("PTS"), term("PTS%"), term("RW"), term("GR")];
  document.querySelector("#atlanticTable thead").innerHTML = headerRow(head);
  document.querySelector("#atlanticTable tbody").innerHTML = (data.atlantic || []).map((team) => {
    const classes = [
      team.divisionRank <= 3 ? "row-in" : "",
      team.isLeafs ? "row-jays" : "",
      team.divisionCut ? "row-cut" : "",
    ].filter(Boolean).join(" ");
    const cut = team.divisionCut ? `<div class="cut-note">Auto berth</div>` : "";
    const tail = preview
      ? `<td>${esc(team.home)}</td><td>${esc(team.road)}</td><td>${team.isLeafs ? "—" : esc(team.vsLeafs ?? 0)}</td>`
      : `<td>${esc(ptsPct(team.pointPct))}</td><td>${esc(team.rw)}</td><td>${esc(team.gr ?? "—")}</td>`;
    const mid = preview
      ? `<td>${esc(team.record)}</td><td>${esc(team.points)}</td><td>${esc(team.rw)}</td>`
      : `<td>${esc(team.gp)}</td><td>${esc(team.record)}</td><td>${esc(team.points)}</td>`;
    return `<tr class="${classes}">
      <td>${esc(team.divisionRank)}${cut}</td>
      <td>${teamCell(team)}</td>
      ${mid}
      ${tail}
    </tr>`;
  }).join("");
}

function renderLeaders(data) {
  $("divLeaders").innerHTML = (data.leaders || []).map((team) => `
    <article class="div-card">
      <img src="${esc(team.logo)}" alt="" />
      <div>
        <strong>${esc(team.name)}</strong>
        <div class="meta">${esc(team.division)} · ${esc(team.record)} · ${esc(team.points)} pts · ${esc(ptsPct(team.pointPct))}</div>
      </div>
    </article>
  `).join("");
}

function metricMax(rows, getter) {
  return Math.max(...rows.map(getter), 0.0001);
}

function compareBlock(rows, block) {
  const max = metricMax(rows, block.get);
  const sorted = [...rows].sort((a, b) => block.get(b) - block.get(a));
  const body = sorted.map((team) => {
    const width = Math.max(8, Math.min(100, Math.round((block.get(team) / max) * 100)));
    return `<div class="compare-row">
      <div class="who"><img src="${esc(team.logo)}" alt="" />${esc(team.abbr)}</div>
      <div class="bar ${team.abbr === LEAF ? "jays" : ""}"><span style="width:${width}%"></span></div>
      <b>${esc(block.format(team))}</b>
    </div>`;
  }).join("");
  return `<div class="compare-block"><header>${block.title}</header>${body}</div>`;
}

function renderCompare(data) {
  $("compareTitle").textContent = data.compareTitle || "Teams in the division";
  const rows = data.compare || [];
  const columns = [
    {
      heading: "The standings",
      blocks: [
        { title: term("PTS"), get: (team) => team.points || 0, format: (team) => team.points },
        { title: term("RW"), get: (team) => team.rw || 0, format: (team) => team.rw },
        { title: term("ROW"), get: (team) => team.row || 0, format: (team) => team.row },
      ],
    },
    {
      heading: "The margins",
      blocks: [
        { title: term("Diff", "Goal diff"), get: (team) => (team.diff || 0) + 200, format: (team) => signed(team.diff) },
        { title: "Home points", get: (team) => team.homePoints || 0, format: (team) => team.homePoints },
        { title: "Road points", get: (team) => team.roadPoints || 0, format: (team) => team.roadPoints },
      ],
    },
  ];
  $("compare").innerHTML = columns.map((col) => `
    <div class="compare-col">
      <h4>${esc(col.heading)}</h4>
      ${col.blocks.map((block) => compareBlock(rows, block)).join("")}
    </div>
  `).join("");
}

function renderSchedule(data) {
  const left = data.remaining || {};
  const sos = left.sos == null ? "—" : ptsPct(left.sos);
  $("gauntletBlurb").textContent =
    `${left.games || 0} games left · ${left.home || 0} home · ${left.away || 0} road · ` +
    `${left.division || 0} against the Atlantic · ${left.backToBacks || 0} back-to-backs · ` +
    `opponent strength ${sos}. Showing the next ${(data.schedule || []).length}.`;
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Toronto", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());
  $("tickets").innerHTML = (data.schedule || []).map((game) => {
    const opp = game.opponent || {};
    const isToday = game.date === today;
    const score = game.final
      ? `${game.awayAbbr} ${game.awayScore} @ ${game.homeAbbr} ${game.homeScore}`
      : game.venue;
    const tags = [
      game.divisionGame ? "Atlantic" : (opp.division || "Interconference"),
      game.backToBack ? "Back-to-back" : "",
      opp.pointPct != null ? `Opp ${ptsPct(opp.pointPct)}` : "",
    ].filter(Boolean).join(" · ");
    return `<article class="ticket${isToday ? " today" : ""}">
      <div class="when">${esc(fmtDate(game.start || game.date, Boolean(game.start)))}</div>
      <h4>${game.isHome ? "vs" : "@"} ${esc(opp.abbr || "TBD")}</h4>
      <div class="pitch">${esc(tags)}</div>
      <div class="ticket-odds"><div class="split-odds">Toronto ${esc(game.leafsWinPct)}%</div></div>
      <div class="venue">${esc(score || "")}</div>
    </article>`;
  }).join("");
}

function renderPreseason(data) {
  const games = data.preseason || [];
  const panel = $("preseasonPanel");
  if (!games.length) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  $("preseason").innerHTML = games.map((game) => {
    const opp = game.opponent || {};
    const score = game.final
      ? `${game.result || ""} ${game.isHome ? game.homeScore : game.awayScore}–${game.isHome ? game.awayScore : game.homeScore}`
      : "Does not count";
    return `<article class="ticket">
      <div class="when">${esc(fmtDate(game.start || game.date, Boolean(game.start)))}</div>
      <h4>${game.isHome ? "vs" : "@"} ${esc(opp.abbr || "")}</h4>
      <div class="pitch">Exhibition</div>
      <div class="venue">${esc(score)}</div>
    </article>`;
  }).join("");
}

function renderRooting(data) {
  $("rooting").innerHTML = (data.rooting || []).map((game) => `
    <article class="root-card">
      <div class="root-head">
        <span class="tag leafs">${esc(game.interest || "Leafs game")}</span>
      </div>
      <strong>${esc(game.awayAbbr)} @ ${esc(game.homeAbbr)}</strong>
      <div class="meta">${esc(fmtDate(game.start || game.date, Boolean(game.start)))}${game.backToBack ? " · second of a back-to-back" : ""}</div>
      <div class="score">${esc(game.awayAbbr)} ${esc(game.awayWinPct)}% · ${esc(game.homeAbbr)} ${esc(game.homeWinPct)}%</div>
      <p>${esc(game.note || "")}</p>
    </article>
  `).join("");
}

function renderResults(data) {
  $("recentBlurb").textContent = data.recentBlurb || "";
  const games = data.recent || [];
  if (!games.length) {
    $("results").innerHTML = `<li><span></span><span>Regular-season results land here after opening night.</span><strong></strong></li>`;
    return;
  }
  $("results").innerHTML = games.slice().reverse().map((game) => {
    const opp = game.opponent || {};
    const us = game.isHome ? game.homeScore : game.awayScore;
    const them = game.isHome ? game.awayScore : game.homeScore;
    const mark = game.result || "•";
    return `<li>
      <span class="badge ${esc(mark)}">${esc(mark === "OTL" ? "OT" : mark)}</span>
      <span>${game.isHome ? "vs" : "@"} ${esc(opp.abbr)} · ${esc(fmtDate(game.date))}</span>
      <strong>${esc(us)}–${esc(them)}</strong>
    </li>`;
  }).join("");
}

function renderTiebreak(data) {
  const box = data.tiebreak || {};
  $("tiebreak").innerHTML = `
    <div class="kpis" style="margin:0">
      <article class="kpi"><div class="label">${term("RW")}</div><div class="value">${esc(box.rw ?? "—")}</div><div class="hint">Regulation wins</div></article>
      <article class="kpi"><div class="label">${term("ROW")}</div><div class="value">${esc(box.row ?? "—")}</div><div class="hint">${esc(box.otWins ?? 0)} overtime wins inside that</div></article>
      <article class="kpi"><div class="label">OT losses</div><div class="value">${esc(box.otl ?? "—")}</div><div class="hint">One point each</div></article>
      <article class="kpi"><div class="label">SO wins</div><div class="value">${esc(box.soWins ?? "—")}</div><div class="hint">Points, but not a tiebreaker win</div></article>
    </div>
    <p class="lede">${esc(box.detail || "")}</p>
  `;
}

function skaterCard(player) {
  const points = player.points == null ? "—" : player.points;
  const line = player.gp
    ? `${player.position || ""} · ${player.gp} GP · ${player.goals}G ${player.assists}A · ${signed(player.plusMinus)} · ${player.toi} TOI`
    : `${player.position || ""} · no Toronto games in this sample`;
  return `<article class="player">
    <img src="${esc(player.headshot)}" alt="" onerror="this.style.opacity='0.25'" />
    <div>
      <strong>${esc(player.name)}</strong>
      <div class="meta">${esc(line)}</div>
    </div>
    <div class="statline"><span class="statline-value">${esc(points)}</span><span class="statline-label">${term("PTS")}</span></div>
  </article>`;
}

function renderPlayers(data) {
  const players = data.players || {};
  const note = players.label || "";
  $("forwardBlurb").textContent = note || "Current roster.";
  $("goalieBlurb").textContent = note
    ? `${note} Save percentage first.`
    : "Save percentage first. Goals-against average second.";
  $("forwards").innerHTML = (players.forwards || []).map(skaterCard).join("")
    || `<p class="meta">Roster numbers will show up once the NHL posts them.</p>`;
  $("defense").innerHTML = (players.defense || []).map(skaterCard).join("");
  $("goalies").innerHTML = (players.goalies || []).map((player) => {
    const record = player.gp
      ? `${player.wins ?? 0}-${player.losses ?? 0}-${player.otl ?? 0} · ${player.gp} GP · ${player.so ?? 0} SO`
      : "No Toronto games in this sample";
    const sv = player.sv == null ? "—" : ptsPct(player.sv);
    const gaa = player.gaa == null ? "" : `${Number(player.gaa).toFixed(2)} GAA`;
    return `<article class="player">
      <img src="${esc(player.headshot)}" alt="" onerror="this.style.opacity='0.25'" />
      <div>
        <strong>${esc(player.name)}</strong>
        <div class="meta">${esc(record)}${gaa ? ` · ${esc(gaa)}` : ""}</div>
      </div>
      <div class="statline"><span class="statline-value">${esc(sv)}</span><span class="statline-label">SV%</span></div>
    </article>`;
  }).join("");
}

function bindTermTips() {
  let tip = document.getElementById("termTip");
  if (!tip) {
    tip = document.createElement("div");
    tip.id = "termTip";
    tip.className = "term-tip";
    tip.setAttribute("role", "tooltip");
    document.body.appendChild(tip);
  }
  document.querySelectorAll("abbr.term").forEach((el) => {
    if (!el.dataset.tip && el.getAttribute("title")) el.dataset.tip = el.getAttribute("title");
    if (el.dataset.tip && !el.getAttribute("aria-label")) {
      el.setAttribute("aria-label", `${el.textContent}: ${el.dataset.tip}`);
    }
    el.removeAttribute("title");
  });
  const place = (el) => {
    const text = el.dataset.tip;
    if (!text) return;
    tip.textContent = text;
    tip.classList.add("show");
    const pad = 12;
    const rect = el.getBoundingClientRect();
    const left = Math.max(pad, Math.min(rect.left + rect.width / 2 - tip.offsetWidth / 2, window.innerWidth - tip.offsetWidth - pad));
    let top = rect.top - tip.offsetHeight - 8;
    if (top < pad) top = Math.min(rect.bottom + 8, window.innerHeight - tip.offsetHeight - pad);
    tip.style.left = `${Math.round(left)}px`;
    tip.style.top = `${Math.round(top)}px`;
  };
  const hide = () => tip.classList.remove("show");
  if (bindTermTips.bound) return;
  bindTermTips.bound = true;
  document.addEventListener("pointerover", (event) => {
    const el = event.target.closest?.("abbr.term");
    if (el) place(el);
  });
  document.addEventListener("pointerout", (event) => {
    const el = event.target.closest?.("abbr.term");
    if (!el) return;
    if (event.relatedTarget && el.contains(event.relatedTarget)) return;
    hide();
  });
  document.addEventListener("focusin", (event) => {
    const el = event.target.closest?.("abbr.term");
    if (el) place(el);
  });
  document.addEventListener("focusout", hide);
  window.addEventListener("scroll", hide, true);
}

async function boot() {
  try {
    const res = await fetch(`data.json?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error("Could not load data.json");
    const data = await res.json();
    renderTicker(data);
    renderConclusion(data);
    renderHero(data);
    renderKpis(data);
    renderTrends(data);
    renderPaths(data);
    renderConference(data);
    renderAtlantic(data);
    renderLeaders(data);
    renderCompare(data);
    renderSchedule(data);
    renderPreseason(data);
    renderRooting(data);
    renderResults(data);
    renderTiebreak(data);
    renderPlayers(data);
    bindTermTips();
  } catch (err) {
    $("headline").textContent = "Dashboard needs a data refresh";
    $("blurb").textContent = "Run scripts/fetch_playoff_data.py, then reload this page.";
    console.error(err);
  }
}

boot();

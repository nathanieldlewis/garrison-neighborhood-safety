"use strict";
/* Uses the same validated snapshot as app.js; no second network request. */
(() => {
  const $ = id => document.getElementById(id);
  const names = {criminal:"Criminal reports",violent:"Violent crime",vehicle:"Vehicle crime",drugs:"Drugs and equipment",burglary:"Burglary / breaking and entering",vandalism:"Vandalism",theft_fraud:"Other theft and fraud",other:"Other criminal reports"};
  const categories = Object.keys(names).filter(k => k !== "criminal");
  const esc = s => String(s ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const number = n => n.toLocaleString("en-US");
  const estimateNumber = n => n.toLocaleString("en-US", {maximumFractionDigits:1});
  let current = null, exportCSV = null, category = "criminal", initialized = false;
  function day(iso, short=false) {
    return new Intl.DateTimeFormat("en-US",{month:short?"short":"long",day:"numeric",year:"numeric",timeZone:"UTC"}).format(new Date(iso+"T12:00:00Z"));
  }
  function lastDay(end) {
    const d = new Date(end+"T12:00:00Z"); d.setUTCDate(d.getUTCDate()-1);
    return d.toISOString().slice(0,10);
  }
  function range(start,end,short=false) {
    if (!start || !end) return "Dates not yet verified";
    if (end <= start) return "No completed reporting days";
    const last = lastDay(end);
    if (start.slice(0,4) !== last.slice(0,4)) return `${day(start,short)} to ${day(last,short)}`;
    const first = new Intl.DateTimeFormat("en-US",{month:short?"short":"long",day:"numeric",timeZone:"UTC"}).format(new Date(start+"T12:00:00Z"));
    return `${first} to ${day(last,short)}`;
  }
  function stamp(iso) {
    return iso && Number.isFinite(Date.parse(iso)) ? new Intl.DateTimeFormat("en-US",{month:"short",day:"numeric",year:"numeric",hour:"numeric",minute:"2-digit",timeZoneName:"short",timeZone:"America/New_York"}).format(new Date(iso)) : "Not yet verified";
  }
  function sourceDay(iso) {
    return iso && Number.isFinite(Date.parse(iso)) ? new Intl.DateTimeFormat("en-US",{month:"short",day:"numeric",year:"numeric",timeZone:"America/New_York"}).format(new Date(iso)) : "Not yet verified";
  }
  function refresh(live,status) {
    const active = live?.mode === "published";
    const stale = active && Date.now()-Date.parse(live.last_successful_fetch)>36*3600000;
    const failed = status?.state === "error";
    $("refresh-prominent").textContent = active ? stamp(live.last_successful_fetch) : "Not yet verified";
    $("source-prominent").textContent = active ? sourceDay(live.citywide_latest_report_date) : "Not yet verified";
    $("refresh-context").classList.toggle("attention",!active || stale || failed || !!live?.source_activity_warning);
    $("refresh-detail").textContent = failed ? `Latest attempt failed (${stamp(status.last_attempt)}). The last successful snapshot is retained.` : stale ? "Stored snapshot: the last successful refresh is more than 36 hours old." : "Daily refresh target: 6:17 a.m. Eastern. CMPD may publish reports late.";
  }
  function renderPeriod(state) {
    const active = state.live?.mode === "published";
    const p = active ? state.live.periods[state.period] : null;
    document.querySelectorAll("[data-period]").forEach(button=>{
      const key = button.dataset.period, period = active ? state.live.periods[key] : null;
      const label = key === "ytd" ? `${period ? period.start.slice(0,4)+" " : ""}year to date` : `Last ${key} days`;
      button.querySelector("span").textContent = label;
      button.querySelector("small").textContent = period ? range(period.start,period.end_exclusive,true) : "Dates pending";
      button.setAttribute("aria-label",`${label}. ${period ? range(period.start,period.end_exclusive) : "Dates pending"}`);
    });
    $("daily-title").textContent = state.period === "ytd" ? `Reports filed ${p ? p.start.slice(0,4)+" " : ""}year to date` : `Reports in the last ${state.period} completed days`;
    $("period-caption").textContent = "The dates below apply to the totals, category mix, changes and reconciliation. Monthly and annual charts use their own labeled periods.";
    $("selected-dates").textContent = p ? range(p.start,p.end_exclusive) : "Dates not yet verified";
    $("comparison-dates").textContent = p ? range(p.comparison_start,p.comparison_end_exclusive) : "Dates not yet verified";
    $("selected-basis").textContent = !p ? "Awaiting a verified CMPD data snapshot." : !p.current_available ? "Full-period coverage is unavailable. Counts are withheld." : `${p.days} completed calendar days in Eastern Time. Today is excluded; recent reports remain provisional.`;
    $("comparison-basis").textContent = !p ? "Equal-length prior-year dates will appear with the first successful pull." : !p.comparison_available ? "Full prior-year coverage is unavailable. The comparison is withheld." : `${p.days} calendar days ending one year earlier. Based on date reported, not incident date.`;
  }
  const count = (a,key=category) => key === "criminal" ? a.criminal : a.categories[key];
  const projected = (a,key=category) => a.annualized ? (key === "criminal" ? a.annualized.criminal : a.annualized.categories[key]) : null;
  function validAnnual(live) {
    if (live?.mode !== "published" || !Array.isArray(live.annual) || live.annual.length !== 4) return false;
    const endYear = Number(live.report_date_window_end_exclusive.slice(0,4));
    return live.annual.every((a,i)=>{
      const year = endYear-3+i, start = `${year}-01-01`, end = i===3 ? live.report_date_window_end_exclusive : `${year+1}-01-01`;
      const days = Math.round((Date.parse(end)-Date.parse(start))/86400000), yearDays = Math.round((Date.UTC(year+1,0,1)-Date.UTC(year,0,1))/86400000);
      if (a.year!==year || a.start!==start || a.end_exclusive!==end || a.days!==days || a.days_in_year!==yearDays || a.is_partial!==(i===3) || typeof a.available!=="boolean") return false;
      const cats = categories.map(k=>a.categories?.[k]), exc = ["unfounded","noncriminal","unclassified"].map(k=>a.excluded?.[k]);
      if ([a.criminal,a.all_reports,...cats,...exc].some(n=>!Number.isInteger(n)||n<0)) return false;
      if (cats.reduce((n,v)=>n+v,0)!==a.criminal || a.criminal+exc.reduce((n,v)=>n+v,0)!==a.all_reports) return false;
      const eligible = a.is_partial && a.available && days>=30 && !live.source_activity_warning;
      if ((a.annualized!==null)!==eligible) return false;
      return !eligible || Object.keys(names).every(k=>Number.isFinite(projected(a,k)) && Math.abs(projected(a,k)-count(a,k)*yearDays/days)<=0.051);
    });
  }
  function renderAnnual() {
    const live = current;
    const valid = validAnnual(live);
    $("download-annual").disabled = !valid || !live.annual.some(a=>a.available);
    if (!valid) {
      $("annual-title").textContent = "Three completed years, plus this year to date";
      $("annual-chart").innerHTML = `<div class="empty-state"><strong>Annual history is not yet available</strong><p>The expanded CMPD pull must succeed before these years can be shown. Missing years are not treated as zero.</p></div>`;
      $("annual-summary").textContent = ""; $("annual-table").innerHTML = "";
      $("annual-notes").innerHTML = `<p><span>1.06.01</span>Annual totals will be calculated from the same CMPD public feed, not extrapolated from the July 2026 five-year archive.</p>`;
      return;
    }
    const rows = live.annual, full = rows.slice(0,3), ytd = rows[3];
    const maximum = Math.max(1,...rows.filter(a=>a.available).map(a=>Math.max(count(a),projected(a)??0)));
    $("annual-title").textContent = `${full[0].year} to ${full[2].year} actuals, with ${ytd.year} shown separately`;
    $("annual-caption").textContent = `${names[category]} within the same 1,000-foot radius. Three completed calendar years plus current YTD. Not affected by the period buttons above.`;
    $("annual-chart").innerHTML = rows.map(a=>{
      const actual = count(a), estimate = projected(a);
      const period = range(a.start,a.end_exclusive,true);
      return `<div class="annual-row"><div class="annual-year"><strong>${a.year}${a.is_partial?" YTD":""}</strong><small>${esc(period)}</small>${a.is_partial?'<span class="partial-label">PARTIAL YEAR</span>':'<small>Completed year</small>'}</div><div>${!a.available?'<p class="annual-unavailable">Full-period coverage unavailable. No count shown.</p>':`<div class="annual-values"><span><strong>${number(actual)}</strong> reported${a.is_partial?" YTD":""}</span>${estimate!==null?`<span class="estimate-label">≈ ${estimateNumber(estimate)} annualized <b>(estimate)</b></span>`:""}</div><div class="annual-track" role="img" aria-label="${esc(`${a.year}: ${actual} reports${a.is_partial?' year to date':''}${estimate!==null?`; annualized estimate ${estimateNumber(estimate)}, not an actual total`:''}`)}">${estimate!==null?`<div class="annual-estimate" style="width:${estimate/maximum*100}%"></div>`:""}<div class="annual-actual" style="width:${actual/maximum*100}%"></div></div>`}</div></div>`;
    }).join("");
    const first = full[0], last = full[2];
    $("annual-summary").textContent = full.every(a=>a.available) ? `${names[category]}: ${number(count(first))} in ${first.year}, ${number(count(full[1]))} in ${full[1].year}, and ${number(count(last))} in ${last.year}. The ${ytd.year} reported count covers only the displayed YTD dates, not a full year.` : "Some completed years lack full source coverage. Those counts are withheld. A partial-year count should not be compared directly with a full-year total.";
    $("annual-table").innerHTML = `<table><caption class="sr-only">${esc(names[category])}: annual periods, reported counts and estimates</caption><thead><tr><th scope="col">Year</th><th scope="col">Reporting dates</th><th scope="col">Days</th><th scope="col">Reported count</th><th scope="col">Annualized estimate<br>(not actual)</th></tr></thead><tbody>${rows.map(a=>`<tr><th scope="row">${a.year}${a.is_partial?" YTD":""}</th><td>${esc(range(a.start,a.end_exclusive,true))}</td><td>${a.days}</td><td>${a.available?number(count(a)):"Unavailable"}</td><td>${projected(a)!==null?"≈ "+estimateNumber(projected(a)):a.is_partial?"Withheld":"Not applicable"}</td></tr>`).join("")}</tbody></table>`;
    const estimate = projected(ytd);
    const method = estimate!==null ? `${ytd.year} annualized estimate = ${number(count(ytd))} reported ÷ ${ytd.days} elapsed days × ${ytd.days_in_year} days in the year = approximately ${estimateNumber(estimate)} reports. The hatched segment is an extrapolation of the remaining year, not observed reports or a forecast.` : "The YTD run rate is withheld until at least 30 completed days are available, and whenever source coverage is insufficient or the citywide feed appears delayed.";
    $("annual-notes").innerHTML = `<p><span>1.06.01</span>Completed-year bars show actual reported counts for non-overlapping calendar years. The current-year bar is explicitly partial. This series is independent of the historical five-year extract.</p><p><span>1.06.02</span>${esc(method)}</p><p><span>1.06.03</span>Annualization does not adjust for seasonality, reporting delays or enforcement activity. CMPD can revise any period; its newest citywide report date is not a completeness cutoff.</p>`;
  }
  function downloadAnnual() {
    if (!validAnnual(current) || !exportCSV) return;
    const keys = Object.keys(names);
    exportCSV("garrison-annual-reporting.csv",[
      ["Source",current.source.url],["Radius feet",current.scope.radius_feet],["Study center",current.scope.latitude,current.scope.longitude],
      ["Last successful refresh",current.last_successful_fetch],["Date basis","Date reported; Eastern Time; end date inclusive"],
      ["Annualization","YTD actual / elapsed calendar days * days in year. Estimate, not actual or forecast. No seasonality adjustment."],
      ["Year","Partial year","Start","End inclusive","Days","Source coverage available","All reports","Unfounded excluded","Non-criminal excluded","Unclassified excluded",...keys.map(k=>names[k]+" actual"),...keys.map(k=>names[k]+" annualized estimate")],
      ...current.annual.map(a=>[a.year,a.is_partial,a.start,a.days?lastDay(a.end_exclusive):"No completed days",a.days,a.available,a.available?a.all_reports:"Unavailable",...["unfounded","noncriminal","unclassified"].map(k=>a.available?a.excluded[k]:"Unavailable"),...keys.map(k=>a.available?count(a,k):"Unavailable"),...keys.map(k=>projected(a,k)??"Not applicable / withheld")])
    ]);
  }
  function render(state,csv) {
    current = state.live; exportCSV = csv;
    if (!initialized) {
      $("annual-category").addEventListener("change",e=>{category=e.target.value;renderAnnual();});
      $("download-annual").addEventListener("click",downloadAnnual);
      initialized = true;
    }
    renderPeriod(state); renderAnnual();
  }
  window.GarrisonReporting = {render,refresh};
})();

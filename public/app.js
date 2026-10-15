"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const labels = {
    violent: "Violent crime", vehicle: "Vehicle crime", drugs: "Drugs and equipment",
    burglary: "Burglary / breaking and entering", vandalism: "Vandalism",
    theft_fraud: "Other theft and fraud", other: "Other criminal reports"
  };
  const state = { period: "30", live: null, history: null, status: null };
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const fmt = n => Number.isInteger(n) && n >= 0 ? n.toLocaleString("en-US") : "Unavailable";
  const percent = (n, total) => total ? (n / total * 100).toFixed(1) + "%" : "0.0%";
  function day(iso, long = false) {
    if (!iso) return "Not yet verified";
    return new Intl.DateTimeFormat("en-US", {month:long ? "long" : "short", day:"numeric", year:"numeric", timeZone:"UTC"}).format(new Date(iso.slice(0,10) + "T12:00:00Z"));
  }
  function lastDay(end) {
    const d = new Date(end + "T12:00:00Z");
    d.setUTCDate(d.getUTCDate() - 1);
    return d.toISOString().slice(0,10);
  }
  function stamp(iso) {
    if (!iso || !Number.isFinite(Date.parse(iso))) return "Not yet run";
    return new Intl.DateTimeFormat("en-US", {month:"short", day:"numeric", year:"numeric", hour:"numeric", minute:"2-digit", timeZoneName:"short", timeZone:"America/New_York"}).format(new Date(iso));
  }
  function sourceDay(iso) {
    if (!iso) return "Not yet verified";
    return new Intl.DateTimeFormat("en-US", {month:"short", day:"numeric", year:"numeric", timeZone:"America/New_York"}).format(new Date(iso));
  }
  function empty(title, description) {
    return `<div class="empty-state"><span class="empty-symbol" aria-hidden="true"><i></i><i></i><i></i></span><strong>${esc(title)}</strong><p>${esc(description)}</p></div>`;
  }
  function note(number, text) { return `<p><span>${esc(number)}</span>${esc(text)}</p>`; }
  function comparison(current, previous, available) {
    if (!available) return "Prior-year comparison is unavailable.";
    const delta = current - previous;
    const direction = delta > 0 ? "up" : delta < 0 ? "down" : "";
    const change = delta === 0 ? "No change" : `${delta > 0 ? "+" : "−"}${Math.abs(delta)}`;
    const rate = previous >= 5 ? ` (${delta > 0 ? "+" : delta < 0 ? "−" : ""}${Math.abs(delta / previous * 100).toFixed(1)}%)` : "";
    return `<span class="${direction}">${esc(change + rate)}</span> vs. ${fmt(previous)} in the prior-year period`;
  }
  function barRows(rows, denominator, muted = false) {
    const maximum = Math.max(...rows.map(r => r[1]), 1);
    return rows.map(([name, value, special]) => `<div class="bar-row"><div class="bar-head"><span class="bar-name">${esc(name)}</span><span class="bar-number">${fmt(value)} <small>(${percent(value,denominator)})</small></span></div><div class="bar-track" aria-hidden="true"><div class="bar-fill ${muted || special ? "muted" : ""}" style="width:${(value / maximum * 100).toFixed(3)}%"></div></div></div>`).join("");
  }
  function validateLive(data) {
    if (!data || data.schema_version !== 1) throw Error("Unsupported snapshot schema");
    if (data.mode !== "published") return;
    if (!data.last_successful_fetch || !Number.isFinite(Date.parse(data.last_successful_fetch))) throw Error("Missing refresh time");
    for (const key of ["30","90","365","ytd"]) {
      const p = data.periods?.[key];
      if (!p || !/^\d{4}-\d{2}-\d{2}$/.test(p.start) || !/^\d{4}-\d{2}-\d{2}$/.test(p.end_exclusive)) throw Error("Invalid period");
      for (const side of ["current","comparison"]) {
        const v = p[side];
        const cats = Object.keys(labels).map(k => v.categories?.[k]);
        const exc = ["unfounded","noncriminal","unclassified"].map(k => v.excluded?.[k]);
        if ([v.criminal,v.all_reports,...cats,...exc].some(n => !Number.isInteger(n) || n < 0)) throw Error("Invalid count");
        if (cats.reduce((a,b)=>a+b,0) !== v.criminal || v.criminal + exc.reduce((a,b)=>a+b,0) !== v.all_reports) throw Error("Counts do not reconcile");
      }
    }
    if (!Array.isArray(data.monthly) || data.monthly.length !== 12) throw Error("Missing monthly series");
    for (const m of data.monthly) if (!/^\d{4}-\d{2}$/.test(m.month) || !Number.isInteger(m.criminal) || m.criminal < 0) throw Error("Invalid monthly series");
  }
  function renderStatus() {
    const live = state.live;
    const active = live?.mode === "published";
    const age = active ? (Date.now() - Date.parse(live.last_successful_fetch)) / 3600000 : Infinity;
    const stale = active && age > 36;
    const failed = state.status?.state === "error";
    const sourceQuiet = active && live.source_activity_warning;
    $("status-pill").className = "status-pill";
    $("feed-notice").className = "notice";
    if (!active) {
      $("status-pill").textContent = "SETUP: NOT YET LIVE";
      $("notice-title").textContent = "Daily reporting has not been activated.";
      $("notice-text").textContent = failed ? "The first data pull has not succeeded. No current counts are shown. The historical archive is separate and remains dated July 2026." : "Current counts remain blank until a successful CMPD data pull. The July 2026 archive below is historical, not a current safety assessment.";
    } else if (failed || stale) {
      $("status-pill").textContent = "STORED SNAPSHOT: CHECK UPDATE STATUS";
      $("notice-title").textContent = failed ? "The latest update failed. Prior data is retained." : "The latest successful data check is more than 36 hours old.";
      $("notice-text").textContent = `The figures below are from ${stamp(live.last_successful_fetch)}. No zero counts have been substituted. Use the displayed period dates, not today's date, to interpret the snapshot.`;
    } else if (sourceQuiet) {
      $("status-pill").textContent = "DATA CHECKED: SOURCE ACTIVITY GAP";
      $("notice-title").textContent = "The source was checked, but its newest report date is more than three days behind the reporting-window end.";
      $("notice-text").textContent = "Recent low counts may reflect a source delay. A successful download does not confirm that recent reporting is complete.";
    } else {
      $("status-pill").classList.add("ok");
      $("status-pill").textContent = "DATA CHECK COMPLETED";
      $("feed-notice").classList.add("ok");
      $("notice-title").textContent = "The latest available public-source records have been checked.";
      $("notice-text").textContent = "Recent periods remain provisional. CMPD can publish reports late or revise classifications. A daily data check is not a guarantee of complete or real-time coverage.";
    }
    $("last-fetch").textContent = stamp(live?.last_successful_fetch);
    $("latest-source").textContent = sourceDay(live?.citywide_latest_report_date);
  }
  function renderMetrics() {
    const p = state.live?.mode === "published" ? state.live.periods[state.period] : null;
    const ready = p?.current_available;
    const definitions = [["Criminal reports", "criminal"], ["Violent crime", "violent"], ["Vehicle crime", "vehicle"], ["Drugs and equipment", "drugs"]];
    $("metrics").innerHTML = definitions.map(([title,key]) => {
      const current = ready ? key === "criminal" ? p.current.criminal : p.current.categories[key] : null;
      const prev = ready ? key === "criminal" ? p.comparison.criminal : p.comparison.categories[key] : null;
      return `<article class="metric"><div class="metric-label">${esc(title)}</div><div class="metric-value ${ready ? "" : "pending"}">${ready ? fmt(current) : p ? "Unavailable" : "Pending"}</div><div class="metric-comparison">${ready ? comparison(current,prev,p.comparison_available) : p ? "The source does not cover this full window." : "Awaiting the first CMPD data pull"}</div></article>`;
    }).join("");
    $("download-live").disabled = !ready;
    if (!p) {
      $("period-caption").textContent = "Report-date totals will appear after the first successful refresh.";
      $("metrics-notes").innerHTML = note("1.01.01","No current statistics are populated from the historical briefing or from example data.") + note("1.01.02","Once activated, the site checks CMPD data each morning and compares equal-length reporting periods.");
      return;
    }
    $("period-caption").textContent = `${day(p.start)} to ${day(lastDay(p.end_exclusive))} · ${p.days} completed reporting days · Eastern Time`;
    const current = p.current.criminal, previous = p.comparison.criminal;
    const headline = !ready ? "This reporting window is outside the source's observed coverage. Counts are withheld rather than presented as a full period." : !p.comparison_available ? `${fmt(current)} reports in criminal categories were returned. Prior-year coverage is insufficient for a comparison.` : `${fmt(current)} criminal reports versus ${fmt(previous)} in the equal-length prior-year period. These are reported incidents, not a measure of individual risk.`;
    $("metrics-notes").innerHTML = note("1.01.01",headline) + note("1.01.02",`Comparison dates: ${day(p.comparison_start)} to ${day(lastDay(p.comparison_end_exclusive))}. Percent changes are omitted when the prior count is below five.`) + note("1.01.03","Vehicle, violence and drug cards are subsets of criminal reports. Do not add them to the total.");
  }
  function renderCategories() {
    const p = state.live?.mode === "published" ? state.live.periods[state.period] : null;
    if (!p?.current_available) {
      $("category-chart").innerHTML = empty(p ? "Full-period coverage is unavailable" : "Category counts are not yet available",p ? "The source does not cover the full selected reporting period." : "This chart will use the daily public feed, not the five-year archive.");
      $("category-title").textContent = "Which categories account for the reports?";
      $("category-notes").innerHTML = note("1.02.01","Each report is assigned to one category using its highest NIBRS code. Counts will reconcile to the criminal-report total.");
      return;
    }
    const rows = Object.entries(labels).map(([key,name])=>[name,p.current.categories[key]]).sort((a,b)=>b[1]-a[1]);
    const total = p.current.criminal;
    $("category-title").textContent = total ? `${rows[0][0]} accounts for ${percent(rows[0][1],total)} of criminal reports` : "No reports in criminal categories were returned for this period";
    $("category-chart").innerHTML = total ? barRows(rows,total) : empty("Zero criminal-category reports in the returned records","This does not establish that no crimes occurred or that all recent reports have been published.");
    $("category-notes").innerHTML = note("1.02.01",`The seven categories total ${fmt(total)} criminal reports. Bar lengths are scaled to the largest category; labels show shares of all criminal reports.`) + note("1.02.02","Drug counts include equipment violations and may reflect enforcement activity as well as underlying offenses.");
  }
  function renderMonthly() {
    const monthly = state.live?.mode === "published" ? state.live.monthly : [];
    if (!monthly.length || !monthly.some(m=>m.available)) {
      $("monthly-chart").innerHTML = empty("Monthly history is not yet available","The first successful pull will populate completed calendar months. No trend has been inferred from overlapping five-year totals.");
      $("monthly-notes").innerHTML = note("1.03.01","Completed months are shown separately from the selected 30-, 90- or 365-day window. Late reports can revise earlier months.");
      return;
    }
    const maximum = Math.max(5, ...monthly.filter(m=>m.available).map(m=>m.criminal));
    const step = Math.max(1, Math.ceil(maximum / 5)), top = step * 5;
    const W=520,H=248,left=33,right=8,plotTop=17,bottom=200,plotW=W-left-right,barStep=plotW/12,barW=barStep*.62;
    let svg = `<svg class="monthly-svg" viewBox="0 0 ${W} ${H}" role="img" aria-labelledby="monthly-svg-title"><title id="monthly-svg-title">Criminal reports by completed month</title>`;
    for(let i=0;i<=5;i++) { const value=step*i,y=bottom-(bottom-plotTop)*value/top; svg += `<line class="grid-line" x1="${left}" x2="${W-right}" y1="${y}" y2="${y}"/><text class="axis-text" x="${left-7}" y="${y+3}" text-anchor="end">${value}</text>`; }
    monthly.forEach((m,i)=>{const x=left+i*barStep+(barStep-barW)/2;const height=m.available?(bottom-plotTop)*m.criminal/top:0;const y=bottom-height;const label=new Intl.DateTimeFormat("en-US",{month:"short",year:"2-digit",timeZone:"UTC"}).format(new Date(m.month+"-15T12:00:00Z"));svg += `<g><title>${esc(label)}: ${m.available ? fmt(m.criminal)+" criminal reports" : "Unavailable"}</title><rect class="monthly-bar" x="${x}" y="${y}" width="${barW}" height="${height}"/><text class="month-value" x="${x+barW/2}" y="${Math.max(10,y-5)}" text-anchor="middle">${m.available?fmt(m.criminal):"n/a"}</text><text class="axis-text" transform="translate(${x+barW/2},215) rotate(-35)" text-anchor="end">${esc(label)}</text></g>`;});
    svg += "</svg>";
    $("monthly-chart").innerHTML = svg;
    $("monthly-notes").innerHTML = note("1.03.01","These are report-date counts for twelve completed calendar months. Recent months may still be revised as CMPD records are updated.") + note("1.03.02","Month-to-month differences can reflect reporting and enforcement patterns. They do not, by themselves, establish a change in personal risk.");
  }
  function renderReconciliation() {
    const p=state.live?.mode==="published" ? state.live.periods[state.period] : null;
    const values=p?.current_available ? [p.current.all_reports,p.current.criminal,p.current.excluded.unfounded,p.current.excluded.noncriminal,p.current.excluded.unclassified] : null;
    const names=["All reports","Criminal reports","Unfounded","Non-criminal","Unclassified"];
    $("reconciliation").innerHTML=names.map((name,i)=>`<div class="recon-value"><strong>${values?fmt(values[i]):"···"}</strong><span>${esc(name)}</span></div>`).join("");
  }
  function renderHistory() {
    const h=state.history;
    if(!h || !Array.isArray(h.rows) || h.rows.reduce((s,r)=>s+r.current,0)!==893 || h.rows.reduce((s,r)=>s+r.prior,0)!==870) {
      $("history-chart").innerHTML=empty("Archive table could not be loaded","Use the Association's original historical records rather than inferring missing values.");
      $("overlap-chart").innerHTML="";
      $("download-history").disabled=true;
      return;
    }
    const rows=[...h.rows].sort((a,b)=>b.current-a.current).slice(0,8).map(r=>[r.category,r.current,r.category.includes("Non-Criminal")]);
    $("history-chart").innerHTML=barRows(rows,h.current_total);
    $("overlap-chart").innerHTML=`<div class="overlap-row"><div class="overlap-label"><span>July 8, 2020 to July 7, 2025</span><strong>870</strong></div><div class="overlap-bar" style="width:${870/893*100}%"></div><small>Earlier five-year window</small></div><div class="overlap-row"><div class="overlap-label"><span>July 8, 2021 to July 7, 2026</span><strong>893</strong></div><div class="overlap-bar current" style="width:100%"></div><small>Later five-year window</small></div><div class="overlap-note"><strong>+23</strong><p>Net difference between the two windows.<br>Not an annual trend or an annual percentage increase.</p></div>`;
    $("history-table").innerHTML=h.rows.map(r=>`<tr><th scope="row">${esc(r.category)}</th><td>${fmt(r.prior)}</td><td>${fmt(r.current)}</td><td>${r.change>0?"+":""}${r.change}</td></tr>`).join("");
  }
  function renderDaily() { renderStatus();renderMetrics();renderCategories();renderMonthly();renderReconciliation(); }
  function downloadCSV(filename, rows) {
    const cell = value => {
      let s=String(value ?? "");
      if (typeof value === "string" && /^[=+\-@\t\r]/.test(s)) s="'"+s;
      return '"'+s.replaceAll('"','""')+'"';
    };
    const blob=new Blob(["\uFEFF"+rows.map(row=>row.map(cell).join(",")).join("\r\n")],{type:"text/csv;charset=utf-8"});
    const url=URL.createObjectURL(blob), a=document.createElement("a");a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  async function initialize() {
    document.querySelectorAll("[data-period]").forEach(button=>button.addEventListener("click",()=>{state.period=button.dataset.period;document.querySelectorAll("[data-period]").forEach(b=>b.setAttribute("aria-pressed",String(b===button)));renderDaily();}));
    $("print").addEventListener("click",()=>window.print());
    $("download-history").addEventListener("click",()=>{const h=state.history;if(!h)return;downloadCSV("garrison-historical-cmpd-table-2026-07-08.csv",[["Source",h.source],["Earlier period",h.prior_start,h.prior_end],["Later period",h.current_start,h.current_end],["Category","Prior","Current","Change"],...h.rows.map(r=>[r.category,r.prior,r.current,r.change]),["TOTAL",h.prior_total,h.current_total,h.current_total-h.prior_total]]);});
    $("download-live").addEventListener("click",()=>{const p=state.live?.periods[state.period];if(!p?.current_available)return;downloadCSV(`garrison-${state.period}-day-summary.csv`,[["Source",state.live.source.url],["Last successful fetch",state.live.last_successful_fetch],["Date basis","Date reported; Eastern Time"],["Current start",p.start],["Current end inclusive",lastDay(p.end_exclusive)],["Comparison start",p.comparison_start],["Comparison end inclusive",lastDay(p.comparison_end_exclusive)],["Comparison available",String(p.comparison_available)],["Measure","Current","Comparison"],["Criminal reports",p.current.criminal,p.comparison_available?p.comparison.criminal:"Unavailable"],...Object.entries(labels).map(([k,v])=>[v,p.current.categories[k],p.comparison_available?p.comparison.categories[k]:"Unavailable"]),["All reports",p.current.all_reports],["Excluded: unfounded",p.current.excluded.unfounded],["Excluded: non-criminal",p.current.excluded.noncriminal],["Excluded: unclassified",p.current.excluded.unclassified]]);});
    renderDaily();
    try {
      let data;
      if(window.GARRISON_EMBEDDED) data=window.GARRISON_EMBEDDED;
      else {
        const load=async name=>{const response=await fetch(`data/${name}.json`,{cache:"no-store"});if(!response.ok)throw Error("Data file unavailable");return response.json();};
        const results=await Promise.allSettled([load("latest"),load("status"),load("history")]);
        data={live:results[0].status==="fulfilled"?results[0].value:null,status:results[1].status==="fulfilled"?results[1].value:{state:"error"},history:results[2].status==="fulfilled"?results[2].value:null};
      }
      state.history=data.history;
      renderHistory();
      validateLive(data.live);
      state.live=data.live;state.status=data.status;
      renderDaily();
    } catch(error) {
      state.live=null;state.status={state:"error"};renderDaily();
      $("notice-title").textContent="Current data could not be loaded or validated.";
      $("notice-text").textContent="No current statistics are shown. This is a data-availability issue, not a report of zero incidents. The historical archive remains a separate source.";
      console.error("The current snapshot could not be loaded or validated.");
    }
    // Reevaluate age while a page is left open, without pretending to fetch new data.
    setInterval(renderStatus,60000);
  }
  initialize();
})();

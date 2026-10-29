"use strict";
const $ = id => document.getElementById(id);
let token = "", currentSpec = {}, lastResult = null, marketCSV = "", eventCSV = "", feed = null;
const money = value => value == null ? "Undefined" : new Intl.NumberFormat("en-US", {style:"currency",currency:"USD",maximumFractionDigits:2}).format(value);
const pct = value => value == null ? "Undefined" : `${(value * 100).toFixed(2)}%`;
const escapeHTML = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
function message(text, error = false) { $("message").textContent = text; $("message").className = `message${error ? " error" : ""}`; $("message").hidden = false; }
async function api(path, body) {
  const response = await fetch(path, {method:body === undefined ? "GET" : "POST", headers:{"Content-Type":"application/json","X-Lab-Token":token}, ...(body === undefined ? {} : {body:JSON.stringify(body)})});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || "The request could not be completed.");
  return value;
}
async function action(button, task) {
  const original = button.textContent;
  button.disabled = true; button.textContent = "Working…";
  $("message").hidden = true;
  try { await task(); } catch (error) { message(error.message, true); window.scrollTo({top:0,behavior:"smooth"}); }
  finally { button.disabled = false; button.textContent = original; }
}
function on(id, task) { $(id).addEventListener("click", () => action($(id), task)); }
function download(name, value, type = "application/json") {
  const url = URL.createObjectURL(new Blob([typeof value === "string" ? value : JSON.stringify(value,null,2)], {type}));
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = name; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 5000);
}
function ruleText(rule) {
  if (!rule) return "no automatic exit";
  if (rule.all || rule.any) return `(${(rule.all || rule.any).map(ruleText).join(rule.all ? " AND " : " OR ")})`;
  const label = value => typeof value === "string" ? value.replaceAll("_", " ") : value;
  return `${label(rule.left)} ${rule.op} ${label(rule.right)}`;
}
function setSpec(spec) {
  if (!spec || typeof spec !== "object" || !spec.entry) throw new Error("A strategy requires an entry rule tree.");
  currentSpec = spec;
  if (spec.bar_seconds != null) $("bar-seconds").value = spec.bar_seconds;
  $("location").value = spec.location || "";
  if (spec.amount != null) { $("amount").value = spec.amount; $("custom-budget").value = spec.amount; }
  const leaves = [];
  const collect = rule => { if(rule.all || rule.any) (rule.all || rule.any).forEach(collect); else leaves.push(rule); };
  collect(spec.entry);
  for (const rule of leaves) {
    if (rule.left === "temperature" && typeof rule.right === "number") $("threshold").value = rule.right;
    if (/^momentum_\d+$/.test(rule.left)) $("fast").value = rule.left.split("_")[1];
    if (/^sma_\d+$/.test(rule.left)) $("fast").value = rule.left.split("_")[1];
    if (typeof rule.right === "string" && /^sma_\d+$/.test(rule.right)) $("slow").value = rule.right.split("_")[1];
  }
  $("spec").value = JSON.stringify(spec,null,2);
  $("interpretation").textContent = `${spec.sizing === "cash" ? `Buy up to ${money(spec.amount)} including fees` : `Target ${pct(spec.weight ?? 1)} exposure`} when ${ruleText(spec.entry)}.${spec.exit ? ` Exit when ${ruleText(spec.exit)}.` : " Hold existing units when the condition is false."}${spec.once ? " Enter once." : ""}`;
  $("template").value = spec.name in {weather:1,buy_hold:1,sma_cross:1,momentum:1,mean_reversion:1} ? spec.name : "custom_rules";
}
function execution() { return {initial_cash:Number($("cash").value),fee_bps:Number($("fee").value),slippage_bps:Number($("slippage").value),periods_per_year:Number($("annual-periods").value),bar_seconds:Number($("bar-seconds").value)}; }
function payload(mode = "rules") {
  const spec = {...currentSpec,bar_seconds:Number($("bar-seconds").value)};
  if ($("location").value.trim()) spec.location = $("location").value.trim(); else delete spec.location;
  return {mode,name:$("name").value,strategy:spec,execution:execution(),market_csv:marketCSV,events_csv:eventCSV,provenance_note:$("provenance").value};
}
function plot(result) {
  const canvas = $("chart"), ratio = window.devicePixelRatio || 1, width = canvas.clientWidth, height = 280;
  if (!width) return;
  canvas.width = width * ratio; canvas.height = height * ratio;
  const ctx = canvas.getContext("2d"); ctx.scale(ratio,ratio);
  const strategy = result.strategy.equity, benchmark = result.benchmark.equity;
  const values = strategy.concat(benchmark).map(r => r.equity);
  let min = Math.min(...values), max = Math.max(...values);
  if (max === min) { max += 1; min -= 1; }
  const pad = {left:65,right:18,top:12,bottom:32};
  const y = value => pad.top + (max-value)/(max-min)*(height-pad.top-pad.bottom);
  ctx.font = "10px Segoe UI";
  for (let i = 0; i <= 4; i++) {
    const val = min + (max-min)*i/4, yy=y(val);
    ctx.strokeStyle="#edf0f6"; ctx.beginPath();ctx.moveTo(pad.left,yy);ctx.lineTo(width-pad.right,yy);ctx.stroke();
    ctx.fillStyle="#7b8699";ctx.textAlign="right";ctx.fillText(money(val),pad.left-10,yy+3);
  }
  for (const [rows,color,line] of [[benchmark,"#b3bdcf",1.8],[strategy,"#4659dc",2.3]]) {
    ctx.strokeStyle=color;ctx.lineWidth=line;ctx.beginPath();
    rows.forEach((r,i)=>{const x=pad.left+i/(rows.length-1)*(width-pad.left-pad.right);i?ctx.lineTo(x,y(r.equity)):ctx.moveTo(x,y(r.equity));});ctx.stroke();
  }
  ctx.fillStyle="#7b8699";ctx.textAlign="left";ctx.fillText(strategy[0].timestamp.slice(0,10),pad.left,height-7);ctx.textAlign="right";ctx.fillText(strategy.at(-1).timestamp.slice(0,10),width-pad.right,height-7);
}
function showResult(result) {
  lastResult = result; $("results").hidden = false; $("result-title").textContent = result.name;
  const metrics = result.summary, baseline = result.benchmark.metrics;
  const cards = [["Total return",pct(metrics.total_return),`Buy and hold ${pct(baseline.total_return)}`],["Maximum drawdown",pct(metrics.max_drawdown),"Measured from each previous equity peak"],["Excess return",pct(metrics.excess_return),"Strategy minus same-period buy and hold"],["Fees paid",money(metrics.fees_paid),`${metrics.trade_count} fills · slippage applied to fill prices`]];
  $("metrics").innerHTML = cards.map(([label,value,foot])=>`<div class="metric"><div class="label">${label}</div><div class="value">${value}</div><div class="foot">${foot}</div></div>`).join("");
  $("warnings").innerHTML = result.warnings.map(w=>`<li>${escapeHTML(w)}</li>`).join("");
  $("chart-alt").textContent = `${result.dataset.source}. Strategy finishes at ${money(metrics.final_equity)}, buy and hold at ${money(baseline.final_equity)}. ${result.strategy.equity.length} evaluated bars. Sharpe: ${metrics.sharpe == null ? "undefined" : metrics.sharpe.toFixed(2)}; annualized return: ${pct(metrics.annualized_return)}. Annualized return is undefined for periods shorter than one year.`;
  $("fills").innerHTML = result.strategy.fills.slice(0,50).map(f=>`<tr><td>${escapeHTML(f.filled_at.slice(0,10))}</td><td>${escapeHTML(f.side)}</td><td>${f.quantity.toFixed(5)}</td><td>${money(f.price)}</td><td>${money(f.fee)}</td></tr>`).join("") || '<tr><td colspan="5">No fills in this experiment.</td></tr>';
  const ml = result.ml;
  $("ml-diagnostics").innerHTML = ml ? `<h2>Held-out model diagnostics</h2><p class="hint">Train ${ml.splits.train.rows} · validation ${ml.splits.validation.rows} · test ${ml.splits.test.rows}. ${ml.splits.purged_rows} boundary rows purged.</p><p class="hint">Selected ridge α ${ml.model.alpha} using validation MSE ${ml.validation.mse.toExponential(3)}. Final test MAE ${ml.test.mae.toExponential(3)}, directional accuracy ${pct(ml.test.directional_accuracy)}. Prediction accuracy does not equal profit.</p>` : "";
  requestAnimationFrame(()=>plot(result));
  $("results").scrollIntoView({behavior:"smooth",block:"start"});
}
async function refreshHistory() {
  const values = await api("/api/history");
  $("history-list").innerHTML = values.length ? `<div class="table-scroll"><table><thead><tr><th>Select</th><th>Experiment</th><th>Mode</th><th>Return</th><th>Actions</th></tr></thead><tbody>${values.map(r=>`<tr><td><input type="checkbox" name="compare" value="${r.id}" aria-label="Select ${escapeHTML(r.name)}"></td><td>${escapeHTML(r.name)}<br><span class="hint">${escapeHTML(r.created_at?.slice(0,16))}</span></td><td>${escapeHTML(r.mode)}</td><td>${pct(r.summary.total_return)}</td><td><button class="text-button" data-view="${r.id}">View</button><button class="text-button" data-rerun="${r.id}">Rerun</button></td></tr>`).join("")}</tbody></table></div>` : '<p>No saved experiments yet. Run your first hypothesis.</p>';
  $("history-list").querySelectorAll("[data-view]").forEach(button=>button.addEventListener("click",()=>action(button,async()=>showResult(await api(`/api/experiments/${button.dataset.view}`)))));
  $("history-list").querySelectorAll("[data-rerun]").forEach(button=>button.addEventListener("click",()=>action(button,async()=>showResult(await api("/api/rerun",{id:button.dataset.rerun})))));
}
function addCondition(left="temperature",op="<",right="5") {
  const item=document.createElement("div");item.className="condition";
  const fields=["close","temperature","sma_20","sma_50","sma_200","momentum_20"];
  item.innerHTML=`<div class="two-col"><label>Feature<select class="left">${fields.map(f=>`<option ${f===left?"selected":""}>${f}</option>`).join("")}</select></label><label>Comparison<select class="op">${["<",">","<=",">=","=="].map(o=>`<option ${o===op?"selected":""}>${escapeHTML(o)}</option>`).join("")}</select></label></div><label>Number or feature name<input class="right" value="${escapeHTML(right)}"></label><button class="text-button remove">Remove condition</button>`;
  item.querySelector(".remove").addEventListener("click",()=>item.remove());$("conditions").append(item);
}
function settings(value) { $("credential-status").textContent = `${value.saved?"A key is saved.":"No key is saved."} Storage: ${value.storage}. Location: ${value.location}. Removal deletes the saved credential file.`; }
document.querySelectorAll(".nav").forEach(button=>button.addEventListener("click",async()=>{
  document.querySelectorAll(".nav").forEach(b=>b.classList.toggle("active",b===button));
  document.querySelectorAll(".panel").forEach(p=>p.hidden=p.id!==`tab-${button.dataset.tab}`);
  $("page-label").textContent=button.textContent.trim().replace(/^[^A-Za-z]+/,"").toUpperCase();
  if (button.dataset.tab==="history") try {await refreshHistory();} catch(error){message(error.message,true);}
}));
on("interpret",async()=>{setSpec(await api("/api/parse",{text:$("hypothesis").value}));message("Interpretation ready. Review the rules and assumptions before running.");});
on("update-template",async()=>{
  const spec=await api("/api/preset",{name:$("template").value,fast:Number($("fast").value),slow:Number($("slow").value),amount:Number($("amount").value),threshold:Number($("threshold").value)});
  spec.bar_seconds=Number($("bar-seconds").value); if($("location").value.trim())spec.location=$("location").value.trim();
  setSpec(spec);
});
on("apply-spec",async()=>{const spec=JSON.parse($("spec").value);setSpec(spec);message("Specification applied. It will be validated when the experiment runs.");});
on("add-condition",async()=>{if($("conditions").children.length>=20)throw new Error("Use at most 20 conditions.");addCondition();});
on("apply-conditions",async()=>{
  const rules=[...$("conditions").children].map(row=>{const raw=row.querySelector(".right").value.trim();if(!raw)throw new Error("Enter a number or feature name.");return {left:row.querySelector(".left").value,op:row.querySelector(".op").value,right:Number.isFinite(Number(raw))?Number(raw):raw};});
  if(!rules.length)throw new Error("Add at least one condition.");
  setSpec({name:"custom_rules",entry:{[$("logic").value]:rules},sizing:"cash",amount:Number($("custom-budget").value),bar_seconds:Number($("bar-seconds").value)});
});
for(const [id,kind] of [["market-file","market"],["events-file","events"]]) $(id).addEventListener("change",async()=>{
  const file=$(id).files[0];if(!file)return;if(file.size>2000000){message("Use a CSV under 2 MB and at most 5,000 market bars.",true);return;}
  const value=await file.text();if(kind==="market"){marketCSV=value;$("instrument-label").textContent="User-imported instrument";}else eventCSV=value;
  $("fixture-tag").textContent=marketCSV?"USER-IMPORTED MARKET DATA":"SYNTHETIC MARKET + IMPORTED EVENTS";
  $("data-label").textContent=`${marketCSV?"User market CSV":"Synthetic market fixture"}; ${eventCSV?"user event CSV":marketCSV?"no external events":"synthetic weather fixture"}. Verify source, timezone, interval and data rights.`;
});
on("reset-data",async()=>{marketCSV="";eventCSV="";$("fixture-tag").textContent="SYNTHETIC OFFLINE FIXTURES · 520 DAYS";$("market-file").value="";$("events-file").value="";$("instrument-label").textContent="Synthetic BTC-like instrument";$("data-label").textContent="Generated market and weather data. A software demonstration, not historical Bitcoin performance.";});
on("run",async()=>showResult(await api("/api/run",payload())));
on("run-ml",async()=>{const body=payload("ml");body.name=`${$("name").value} · ridge`;body.ml={feature_names:[...document.querySelectorAll('input[name="feature"]:checked')].map(i=>i.value),horizon:Number($("horizon").value),train_fraction:Number($("train-fraction").value),validation_fraction:Number($("val-fraction").value),ridge_alphas:$("alphas").value.split(",").map(Number),threshold:Number($("prediction-threshold").value),seed:42};showResult(await api("/api/run",body));});
on("search",async()=>{const result=await api("/api/search",{market_csv:marketCSV,trials:Number($("trials").value),seed:Number($("seed").value)});$("search-results").innerHTML=`<p class="hint">${result.trial_count} seeded trials. Validation is exploratory.</p><table><thead><tr><th>Trial</th><th>Feature subset</th><th>Validation MSE</th></tr></thead><tbody>${result.trials.map((r,i)=>`<tr><td>${i+1}</td><td>${escapeHTML(r.features.join(", "))}</td><td>${r.validation.mse.toExponential(3)}</td></tr>`).join("")}</tbody></table>`;});
on("export",async()=>{if(lastResult)download(`hypothesis-lab-${lastResult.id}.json`,lastResult);});
on("refresh-history",refreshHistory);
on("compare",async()=>{
  const ids=[...document.querySelectorAll('input[name="compare"]:checked')].map(i=>i.value);
  if(ids.length!==2)throw new Error("Select exactly two experiments.");
  const rows=await Promise.all(ids.map(id=>api(`/api/experiments/${id}`)));
  const [a,b]=rows;
  const compatible=a.dataset.identity===b.dataset.identity&&JSON.stringify(a.configuration.execution)===JSON.stringify(b.configuration.execution)&&a.strategy.equity[0].timestamp===b.strategy.equity[0].timestamp&&a.strategy.equity.at(-1).timestamp===b.strategy.equity.at(-1).timestamp;
  if(!compatible)throw new Error("These runs use different data, periods or execution settings. Rerun them with matching assumptions before comparing returns.");
  $("comparison").innerHTML=`<h2>Matched comparison</h2><table><thead><tr><th>Experiment</th><th>Return</th><th>Drawdown</th><th>Fees</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${escapeHTML(r.name)}</td><td>${pct(r.summary.total_return)}</td><td>${pct(r.summary.max_drawdown)}</td><td>${money(r.summary.fees_paid)}</td></tr>`).join("")}</tbody></table><p class="callout">Choosing a winner after repeated comparisons creates selection bias. Results describe these samples only.</p>`;
});
$("import-run").addEventListener("change",async()=>{const file=$("import-run").files[0];if(!file)return;try{if(file.size>3000000)throw new Error("Import must be under 3 MB.");showResult(await api("/api/import",JSON.parse(await file.text())));await refreshHistory();}catch(error){message(error.message,true);}});
on("save-key",async()=>{settings(await api("/api/settings/save",{key:$("api-key").value,consent:$("consent").checked}));$("api-key").value="";$("consent").checked=false;message("Optional credential saved locally with your consent.");});
on("remove-key",async()=>{settings(await api("/api/settings/remove",{}));$("api-key").value="";message("Saved provider credential removed.");});
on("test-key",async()=>{$("key-status").textContent="Testing the selected provider…";try{const value=await api("/api/settings/test",{});$("key-status").textContent=`${value.status}: ${value.symbol} ${money(value.price)} on ${value.latest_trading_day}. ${value.warning}`;}catch(error){$("key-status").textContent="Connection unavailable.";throw error;}});
on("refresh-feed",async()=>{$("feed-status").textContent="Requesting completed daily candles…";try{feed=await api("/api/feed",{});$("feed-status").textContent=`${feed.status} · ${feed.bars.length} completed bars. Latest close ${money(feed.latest_close)} at ${feed.last_completed_at}. Age ${(feed.delay_seconds/3600).toFixed(1)} hours. Fetched ${feed.fetched_at}. ${feed.warnings.join(" ")}`;$("download-feed").hidden=false;}catch(error){$("feed-status").textContent="Unavailable. Historical fixtures and CSV imports remain ready.";throw error;}});
on("download-feed",async()=>{if(feed)download("kraken-completed-daily.csv","timestamp,open,high,low,close,volume\n"+feed.bars.map(b=>[b.timestamp,b.open,b.high,b.low,b.close,b.volume].join(",")).join("\n"),"text/csv");});
on("fetch-weather",async()=>{const value=await api("/api/weather",{latitude:Number($("latitude").value),longitude:Number($("longitude").value),start:$("weather-start").value,end:$("weather-end").value});download("open-meteo-revised-events.csv",value.csv,"text/csv");message(`${value.attribution}. ${value.warnings.join(" ")}`);});
on("stop",async()=>{await api("/api/shutdown",{});message("Hypothesis Lab stopped. Close this tab; restart with the documented launch command.");$("stop").disabled=true;});
window.addEventListener("resize",()=>{if(lastResult)plot(lastResult);});
(async()=>{try{const boot=await api("/api/bootstrap");token=boot.token;$("version").textContent=`v${boot.version}`;setSpec(boot.preset);settings(boot.settings);addCondition();addCondition("close",">","sma_200");}catch(error){message(`The local service is unavailable. ${error.message}`,true);}})();

"use strict";

const $ = (selector) => document.querySelector(selector);
const state = { token: sessionStorage.getItem("iyosi_admin_token"), items: [], cursor: null, selected: null, detail: null };
const PRIVATE_FIELDS = new Set(["account_id", "actor_id", "basis", "detail", "verification_evidence", "evidence", "email"]);
const PLACE_ACTIONS = ["resolve", "verify_designated", "set_status", "hide_place", "restore_place", "correct_place", "merge_place"];
const ACTION_LABELS = {
  publish: "Publish submission", reject: "Reject submission", merge: "Merge submission", resolve: "Resolve without changing content",
  verify_designated: "Verify designated status", set_status: "Set advisory status", hide_place: "Hide place", restore_place: "Restore place",
  correct_place: "Correct place", merge_place: "Merge published place", hide_confirmation: "Hide confirmation",
  hide_review: "Hide review", restore_review: "Restore review", approve_deletion: "Approve account deletion"
};

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}
function fmt(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}
function date(value) { return value ? new Date(value).toLocaleString() : "—"; }
function localDateTimeInputValue(value) {
  return new Date(value.getTime() - value.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
function notice(message, kind = "") {
  const node = $("#notice");
  node.textContent = message;
  node.className = kind;
  node.hidden = !message;
}
function errorText(error) {
  const details = error.body?.field_errors?.map((item) => `${item.field}: ${item.message}`).join("; ");
  const request = error.body?.request_id || error.requestId;
  return `${error.body?.message || error.message || "Request failed"}${details ? ` (${details})` : ""}${request ? ` · Request ${request}` : ""}`;
}
async function api(path, options = {}) {
  const headers = { Accept: "application/json", ...options.headers };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (options.body) headers["Content-Type"] = "application/json";
  let response;
  try { response = await fetch(path, { ...options, headers, cache: "no-store" }); }
  catch { throw new Error("The API could not be reached. Check the connection and retry."); }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && path !== "/v1/auth/token") signOut("Your session expired. Sign in again.");
    const error = new Error(body?.message || `HTTP ${response.status}`);
    error.status = response.status;
    error.body = body;
    error.requestId = response.headers.get("X-Request-ID");
    throw error;
  }
  return body;
}
function signOut(message = "") {
  state.token = null; state.items = []; state.cursor = null; state.selected = null; state.detail = null;
  sessionStorage.removeItem("iyosi_admin_token");
  $("#workspace").hidden = true; $("#identity").hidden = true; $("#login-view").hidden = false;
  $("#password").value = "";
  notice(message, message ? "error" : "");
}
async function enter() {
  const me = await api("/v1/me");
  if (me.role !== "admin") { signOut(); throw new Error("This account does not have admin access."); }
  $("#operator").textContent = me.email;
  $("#login-view").hidden = true; $("#workspace").hidden = false; $("#identity").hidden = false;
  await loadQueue(false);
}
async function loadQueue(more) {
  const selected = state.selected;
  if (!more) { state.items = []; state.cursor = null; state.selected = null; state.detail = null; $("#detail").replaceChildren(el("div", "Select a case to inspect its source and history.", "empty")); }
  const query = new URLSearchParams({ state: $("#queue-state").value, limit: "30" });
  if (more && state.cursor) query.set("cursor", state.cursor);
  const data = await api(`/v1/admin/moderation-cases?${query}`);
  state.items.push(...data.items); state.cursor = data.next_cursor;
  renderQueue();
  if (!more && selected && state.items.some((item) => item.id === selected)) await selectCase(selected);
}
function renderQueue() {
  const list = $("#queue-list"); list.replaceChildren();
  $("#queue-count").textContent = `${state.items.length}${state.cursor ? "+" : ""} cases`;
  $("#next-page").hidden = !state.cursor;
  if (!state.items.length) list.append(el("p", "No cases in this queue."));
  for (const item of state.items) {
    const button = el("button", null, `case-item${item.id === state.selected ? " active" : ""}`);
    button.type = "button";
    button.append(el("span", `Priority ${item.priority}`, `pill${item.priority >= 2 ? " high" : ""}`), el("strong", `${item.source_type.replaceAll("_", " ")} · ${item.id}`), el("small", date(item.created_at)));
    button.addEventListener("click", () => selectCase(item.id).catch(showError));
    list.append(button);
  }
}
async function selectCase(id) {
  state.selected = id; state.detail = null; renderQueue();
  $("#detail").replaceChildren(el("div", "Loading case…", "empty"));
  const detail = await api(`/v1/admin/moderation-cases/${encodeURIComponent(id)}`);
  if (state.selected !== id) return;
  state.detail = detail;
  renderDetail();
}
function fieldsCard(title, object) {
  const section = el("section", null, "card"); section.append(el("h3", title));
  if (!object) { section.append(el("p", "No record is available.")); return section; }
  const list = el("dl", null, "fields");
  for (const [key, value] of Object.entries(object)) {
    if (PRIVATE_FIELDS.has(key) || key === "password_hash") continue;
    list.append(el("dt", key.replaceAll("_", " ")), el("dd", fmt(value)));
  }
  section.append(list); return section;
}
function privateCard(detail) {
  const values = {};
  for (const [label, object] of [["Source", detail.source], ["Place", detail.context?.place]]) {
    for (const [key, value] of Object.entries(object || {})) if (PRIVATE_FIELDS.has(key) && value !== null && value !== undefined) values[`${label} · ${key}`] = value;
  }
  const card = el("section", null, "card private");
  card.append(el("h3", "Private case material"), el("p", "Reveal only when needed for this decision. Do not copy it into a public source summary."));
  if (!Object.keys(values).length) { card.append(el("p", "No private fields on this case.")); return card; }
  const button = el("button", "Reveal private material", "secondary"); button.type = "button";
  const content = el("pre", JSON.stringify(values, null, 2), "private-content"); content.hidden = true;
  button.addEventListener("click", () => { content.hidden = !content.hidden; button.textContent = content.hidden ? "Reveal private material" : "Hide private material"; });
  card.append(button, content); return card;
}
function historyCard(detail) {
  const card = el("section", null, "card"); card.append(el("h3", "Decision history"));
  if (!detail.decisions.length) { card.append(el("p", "No decisions recorded.")); return card; }
  for (const decision of detail.decisions) {
    const row = el("div", null, "history-item");
    row.append(el("strong", ACTION_LABELS[decision.action] || decision.action), el("div", `${date(decision.created_at)} · ${decision.actor_id}`, "meta"), el("p", decision.reason));
    const snapshots = el("details"); snapshots.append(el("summary", "Reveal private audit snapshots"), el("pre", JSON.stringify({ old_state: decision.old_state, new_state: decision.new_state }, null, 2)));
    row.append(snapshots); card.append(row);
  }
  return card;
}
function actionsFor(detail) {
  const { case: item, source, context } = detail;
  if (item.state !== "open") return [];
  if (item.source_type === "submission") return source?.intent === "create" ? ["publish", "reject", "merge"] : ["publish", "reject"];
  if (item.source_type === "deletion_request") return ["approve_deletion"];
  if (item.source_type === "report" && source?.target_type === "review") return ["resolve", "hide_review", "restore_review"];
  if (item.source_type === "confirmation") return ["hide_confirmation", ...PLACE_ACTIONS];
  return context?.place ? PLACE_ACTIONS : ["resolve"];
}
function renderDetail() {
  const detail = state.detail, item = detail.case;
  const root = $("#detail"); root.replaceChildren();
  const head = el("div", null, "detail-head");
  const heading = el("div"); heading.append(el("h2", `${item.source_type.replaceAll("_", " ")} case`), el("div", `${item.id} · ${item.state} · opened ${date(item.created_at)}`, "meta"));
  head.append(heading, el("span", `Priority ${item.priority}`, `pill${item.priority >= 2 ? " high" : ""}`)); root.append(head);
  const grid = el("div", null, "detail-grid"); grid.append(fieldsCard("Source record", detail.source));
  if (detail.context?.review) grid.append(fieldsCard("Reported review", detail.context.review));
  if (detail.context?.place) grid.append(fieldsCard("Current place · version " + detail.context.place.version, detail.context.place));
  root.append(grid, privateCard(detail), historyCard(detail));
  const actions = actionsFor(detail);
  if (actions.length) root.append(decisionForm(detail, actions));
}
function option(value, label) { const node = el("option", label); node.value = value; return node; }
function decisionForm(detail, actions) {
  const form = el("form", null, "decision-form"); form.id = "decision-form";
  form.append(el("h3", "Record a decision"), el("p", "The API records the action, reason, and before/after state in one transaction."));
  const actionLabel = el("label", "Action"); const action = el("select"); action.name = "action";
  for (const value of actions) action.append(option(value, ACTION_LABELS[value])); actionLabel.append(action); form.append(actionLabel);
  const grid = el("div", null, "form-grid");
  const add = (name, title, type = "text", extras = {}) => {
    const label = el("label", title); label.dataset.for = name;
    const input = type === "select" ? el("select") : el("input"); input.name = name;
    if (type !== "select") input.type = type;
    if (extras.placeholder) input.placeholder = extras.placeholder;
    if (extras.maxLength) input.maxLength = extras.maxLength;
    label.append(input); grid.append(label); return input;
  };
  const status = add("advisory_status", "Advisory status", "select");
  status.append(option("", "Select a status"));
  for (const value of ["community_reported", "disputed", "prohibited", "closed", "verified_designated"]) status.append(option(value, value.replaceAll("_", " ")));
  if (detail.case.source_type === "submission") status.value = "community_reported";
  const canonical = add("canonical_place_id", "Canonical place ID");
  const evidenceType = add("evidence_type", "Evidence type", "select");
  for (const value of ["signage", "venue_confirmation", "official_listing"]) evidenceType.append(option(value, value.replaceAll("_", " ")));
  add("public_source", "Public source summary", "text", { maxLength: 240 });
  add("evidence", "Private evidence details", "text", { maxLength: 1000 });
  const reviewed = add("reviewed_at", "Reviewed at", "datetime-local"); reviewed.value = localDateTimeInputValue(new Date());
  add("name", "Corrected name", "text", { maxLength: 120 });
  const kind = add("kind", "Corrected kind", "select"); kind.append(option("", "Keep current kind"));
  for (const value of ["public_designated", "venue_designated", "informal_outdoor", "venue_claim"]) kind.append(option(value, value.replaceAll("_", " ")));
  const inside = add("inside_venue", "Inside venue", "select"); inside.append(option("", "Keep current value"), option("true", "Yes"), option("false", "No"));
  add("lat", "Corrected latitude", "number", { placeholder: "14.6000" }).step = "any";
  add("lon", "Corrected longitude", "number", { placeholder: "121.0000" }).step = "any";
  add("access_lat", "Corrected entrance latitude", "number").step = "any";
  add("access_lon", "Corrected entrance longitude", "number").step = "any";
  const notesLabel = el("label", "Corrected access notes", "wide"); notesLabel.dataset.for = "access_notes";
  const notes = el("textarea"); notes.name = "access_notes"; notes.maxLength = 500; notesLabel.append(notes); grid.append(notesLabel);
  form.append(grid);
  const reasonLabel = el("label", "Reason · required for audit", "wide");
  const reason = el("textarea"); reason.name = "reason"; reason.required = true; reason.minLength = 5; reason.maxLength = 1000;
  reasonLabel.append(reason); form.append(reasonLabel);
  const version = detail.context?.place?.version;
  if (version !== undefined) form.append(el("p", `Current place version: ${version}. Changes will be rejected if another operator updates it first.`, "help"));
  const submit = el("button", "Apply decision"); submit.type = "submit"; form.append(submit);
  const update = () => {
    const selected = action.value;
    const visible = (name, yes) => { const label = grid.querySelector(`[data-for="${name}"]`); label.hidden = !yes; label.querySelector("input,select,textarea").required = yes && ["canonical_place_id", "evidence_type", "public_source", "evidence", "reviewed_at"].includes(name); };
    const statusNeeded = selected === "publish" || selected === "set_status";
    visible("advisory_status", statusNeeded);
    status.required = statusNeeded;
    for (const name of ["canonical_place_id"]) visible(name, selected === "merge" || selected === "merge_place");
    const verify = selected === "verify_designated" || (selected === "publish" && status.value === "verified_designated");
    for (const name of ["evidence_type", "public_source", "evidence", "reviewed_at"]) visible(name, verify);
    for (const name of ["name", "kind", "inside_venue", "lat", "lon", "access_lat", "access_lon", "access_notes"]) visible(name, selected === "correct_place");
    if (selected === "publish") {
      for (const opt of status.options) opt.disabled = opt.value === "closed";
      if (status.value === "closed") status.value = "community_reported";
    } else {
      for (const opt of status.options) opt.disabled = opt.value === "verified_designated";
      if (status.value === "verified_designated") status.value = "";
    }
  };
  action.addEventListener("change", update); status.addEventListener("change", update); update();
  form.addEventListener("submit", async (event) => {
    event.preventDefault(); submit.disabled = true; notice("");
    try {
      const data = buildDecision(new FormData(form), detail);
      if (["publish", "merge", "merge_place", "approve_deletion", "hide_place"].includes(data.action) && !window.confirm(`Apply “${ACTION_LABELS[data.action]}” to ${detail.case.id}?`)) return;
      await api(`/v1/admin/moderation-cases/${encodeURIComponent(detail.case.id)}/decisions`, { method: "POST", body: JSON.stringify(data) });
      notice(`Decision recorded for ${detail.case.id}.`);
      await loadQueue(false);
      await selectCase(detail.case.id);
    } catch (error) {
      if (error.status === 409) { notice(`${errorText(error)}. Reloading the case now; review current values before deciding again.`, "conflict"); await selectCase(detail.case.id).catch(showError); }
      else showError(error);
    } finally { submit.disabled = false; }
  });
  return form;
}
function buildDecision(data, detail) {
  const action = data.get("action");
  const result = { action, reason: String(data.get("reason")).trim() };
  const place = detail.context?.place;
  if (place && !["resolve", "hide_confirmation"].includes(action)) result.expected_version = place.version;
  if (action === "publish" && detail.source?.intent === "correct" && place) result.expected_version = place.version;
  if (["publish", "set_status"].includes(action)) result.advisory_status = data.get("advisory_status");
  if (["merge", "merge_place"].includes(action)) result.canonical_place_id = String(data.get("canonical_place_id")).trim();
  if (action === "verify_designated" || (action === "publish" && result.advisory_status === "verified_designated")) {
    for (const key of ["evidence_type", "public_source", "evidence"]) result[key] = String(data.get(key)).trim();
    result.reviewed_at = new Date(String(data.get("reviewed_at"))).toISOString();
  }
  if (action === "correct_place") {
    for (const key of ["name", "kind", "access_notes"]) { const value = String(data.get(key) || "").trim(); if (value) result[key] = value; }
    if (data.get("inside_venue")) result.inside_venue = data.get("inside_venue") === "true";
    for (const [prefix, target] of [["", "location"], ["access_", "access_point"]]) {
      const lat = String(data.get(`${prefix}lat`) || "").trim(), lon = String(data.get(`${prefix}lon`) || "").trim();
      if (Boolean(lat) !== Boolean(lon)) throw new Error(`Enter both ${target} coordinates.`);
      if (lat && lon) result[target] = { lat: Number(lat), lon: Number(lon) };
    }
  }
  return result;
}
function showError(error) { notice(errorText(error), "error"); }
$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault(); notice("");
  const button = event.currentTarget.querySelector("button"); button.disabled = true;
  try {
    const token = await api("/v1/auth/token", { method: "POST", body: JSON.stringify({ email: $("#email").value, password: $("#password").value }) });
    state.token = token.access_token; sessionStorage.setItem("iyosi_admin_token", state.token);
    $("#password").value = "";
    await enter();
  } catch (error) { showError(error); }
  finally { button.disabled = false; }
});
$("#sign-out").addEventListener("click", () => signOut());
$("#manual-case-form").addEventListener("submit", async (event) => {
  event.preventDefault(); notice("");
  const form = event.currentTarget, button = form.querySelector("button"); button.disabled = true;
  try {
    const placeId = String(new FormData(form).get("place_id")).trim();
    const created = await api(`/v1/admin/moderation-cases?place_id=${encodeURIComponent(placeId)}`, { method: "POST" });
    form.reset(); $("#queue-state").value = "open";
    await loadQueue(false); await selectCase(created.id);
    notice(`Manual case ${created.id} opened.`);
  } catch (error) { showError(error); }
  finally { button.disabled = false; }
});
$("#refresh").addEventListener("click", () => loadQueue(false).catch(showError));
$("#queue-state").addEventListener("change", () => loadQueue(false).catch(showError));
$("#next-page").addEventListener("click", () => loadQueue(true).catch(showError));
if (state.token) enter().catch((error) => { if (state.token) showError(error); });

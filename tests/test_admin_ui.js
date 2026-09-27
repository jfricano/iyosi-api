const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../admin/assets/admin.js"), "utf8");
const context = {
  document: { querySelector: () => ({ addEventListener() {} }) },
  sessionStorage: { getItem: () => null },
};
vm.runInNewContext(`${source}\nglobalThis.testApi = { actionsFor, buildDecision };`, context);
const { actionsFor, buildDecision } = context.testApi;
const form = (values) => ({ get: (key) => values[key] ?? "" });

const correction = { case: { source_type: "submission", state: "open" }, source: { intent: "correct" }, context: { place: { version: 7 } } };
assert.equal(JSON.stringify(actionsFor(correction)), JSON.stringify(["publish", "reject"]));
assert.equal(buildDecision(form({ action: "publish", reason: "Reviewed evidence", advisory_status: "community_reported" }), correction).expected_version, 7);

const reviewReport = { case: { source_type: "report", state: "open" }, source: { target_type: "review" }, context: { place: { version: 3 } } };
assert.equal(JSON.stringify(actionsFor(reviewReport)), JSON.stringify(["resolve", "hide_review", "restore_review"]));

const deletion = { case: { source_type: "deletion_request", state: "open" }, source: {}, context: {} };
assert.equal(JSON.stringify(actionsFor(deletion)), JSON.stringify(["approve_deletion"]));

const placeCase = { case: { source_type: "manual", state: "open" }, source: {}, context: { place: { version: 4 } } };
const correctionPayload = buildDecision(form({ action: "correct_place", reason: "Correct public entrance", lat: "14.6", lon: "121.0", access_lat: "14.61", access_lon: "121.01", inside_venue: "false" }), placeCase);
assert.equal(correctionPayload.expected_version, 4);
assert.equal(correctionPayload.location.lat, 14.6);
assert.equal(correctionPayload.access_point.lon, 121.01);
assert.equal(correctionPayload.inside_venue, false);
assert.throws(() => buildDecision(form({ action: "correct_place", reason: "Correct public entrance", lat: "14.6" }), placeCase), /both location coordinates/);

console.log("Admin action and decision payload checks passed");

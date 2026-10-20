const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const html = fs.readFileSync(path.join(__dirname, "../site/index.html"), "utf8");
const source = html.slice(html.indexOf("const state ="), html.indexOf("function canShowAccounts"));
const elements = {
  min: { value: "3000" }, max: { value: "" },
  dayFrom: { value: "20261020" }, dayTo: { value: "20261020" },
};
vm.runInNewContext(source + `
state.data = {
  solo: [[0, 20261020, 0, 3000, 2], [0, 20261020, 0, 3050, 1]],
  duo: [[0, 20261020, 0, 3000, 2], [0, 20261020, 0, 3050, 1]],
  pair: [[0, 20261020, 0, 1, 3000, 2], [0, 20261020, 0, 1, 3050, 1]],
  rankSums: { solo: [4, 3], duo: [4, 3], pair: [4, 3] },
  accounts: {
    solo: [[0, 20261020, 0, 0, 3000, 1], [0, 20261020, 0, 0, 3050, 3]],
    duo: [[0, 20261020, 0, 0, 3000, 1], [0, 20261020, 0, 0, 3050, 3]],
    pair: [[0, 20261020, 0, 1, 0, 1, 3000, 1], [0, 20261020, 0, 1, 0, 1, 3050, 3]],
  },
};
for (const view of ['solo', 'duo', 'pair']) {
  state.view = view;
  const key = view === 'pair' ? '0,1' : 0;
  assert.equal(fmtPlace(tally().rows[0][2], tally().rows[0][1]), view === 'solo' ? '2.3/10' : '2.3/5');
  for (const missingIndex of [0, 1]) {
    const original = state.data.rankSums[view][missingIndex];
    state.data.rankSums[view][missingIndex] = null;
    const row = tally().rows[0];
    assert.equal(row[1], 3);
    assert.equal(fmtPlace(row[2], row[1]), '—');
    state.data.rankSums[view][missingIndex] = original;

    const accountRow = state.data.accounts[view][missingIndex], last = accountRow.length - 1;
    const originalPlace = accountRow[last];
    accountRow[last] = null;
    const account = accounts(key)[0][1];
    assert.equal(account.n, 2);
    assert.equal(account.max, 3050);
    assert.equal(fmtPlace(account.places, account.n), '—');
    accountRow[last] = originalPlace;
  }
  const saved = state.data.rankSums;
  delete state.data.rankSums;
  const legacy = tally().rows[0];
  assert.equal(legacy[1], 3);
  assert.equal(fmtPlace(legacy[2], legacy[1]), '—');
  state.data.rankSums = saved;
}
`, { assert, document: { getElementById: id => elements[id] } });
console.log("Weighted ranks, mode denominators, and unknown rank propagation passed.");

// Remembers the machine on screen so "Shuffle" never shows it twice in a row.
// TRMNL keeps `trmnl_state` between refreshes and exposes it to the polling URL as
// {{ trmnl.state.last_id }}, which the API receives as `avoid`. Nothing is stored on
// the server. Everything else passes through unchanged.
function transform(input) {
  if (!input || typeof input !== "object") return input;
  const output = {};
  for (const key of Object.keys(input)) {
    if (key !== "trmnl") output[key] = input[key];
  }
  if (input.machine && input.machine.id) {
    output.trmnl_state = { last_id: input.machine.id };
  }
  return Object.keys(output).length ? output : input;
}

// Serverless runtime entry point.
function run(input) {
  return transform(input);
}

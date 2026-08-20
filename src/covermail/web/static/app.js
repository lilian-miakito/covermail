"use strict";

const byId = (id) => document.getElementById(id);
const apiHeaders = {"Content-Type": "application/json"};
let currentAddress = null;
let createdAddress = null;
let estimateTimer = null;
const sectionCounts = {A: 0, B: 0, BC: 0, C: 0, D: 0};

function toast(message) {
  const node = byId("toast");
  node.textContent = message;
  node.classList.add("show");
  window.setTimeout(() => node.classList.remove("show"), 1800);
}

async function api(path, options = {}) {
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers: {...apiHeaders, ...(options.headers || {})},
  });
  if (!response.ok) {
    let detail = `Local error (${response.status})`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_) { /* response was not JSON */ }
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

function openView(name) {
  const visible = document.querySelector("[data-view]:not(.hidden)");
  if (visible && visible.dataset.view === "read" && name !== "read") {
    byId("secret-output").value = "";
    byId("read-passphrase").value = "";
  }
  document.querySelectorAll("[data-view]").forEach((node) => node.classList.toggle("hidden", node.dataset.view !== name));
  window.scrollTo({top: 0, behavior: "smooth"});
  if (name === "read") refreshIdentities();
  if (name === "advanced") refreshDiagnostics();
}

document.querySelectorAll("[data-open]").forEach((button) => button.addEventListener("click", () => openView(button.dataset.open)));

document.querySelectorAll("[data-copy]").forEach((button) => button.addEventListener("click", async () => {
  const source = byId(button.dataset.copy);
  await navigator.clipboard.writeText(source.value || source.textContent || "");
  toast("Copied to clipboard");
}));

byId("create-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  byId("create-status").textContent = "Creating and encrypting the identity…";
  try {
    const result = await api("/identities", {method: "POST", body: JSON.stringify({
      label: byId("create-label").value,
      passphrase: byId("create-passphrase").value,
      passphrase_confirmation: byId("create-confirmation").value,
    })});
    createdAddress = result.address;
    byId("created-label").textContent = result.label;
    byId("created-fingerprint").textContent = result.fingerprint;
    byId("created-address").value = JSON.stringify(result.address, null, 2);
    byId("create-result").classList.remove("empty");
    byId("create-passphrase").value = "";
    byId("create-confirmation").value = "";
    byId("create-status").textContent = "Identity saved on this device.";
  } catch (error) {
    byId("create-status").textContent = error.message;
  }
});

byId("download-address").addEventListener("click", () => {
  if (!createdAddress) return;
  const blob = new Blob([`${JSON.stringify(createdAddress, null, 2)}\n`], {type: "application/json"});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "covermail-address.json";
  link.click();
  URL.revokeObjectURL(link.href);
});

byId("write-address-file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (file) byId("write-address").value = await file.text();
});

async function inspectAddress() {
  const address = JSON.parse(byId("write-address").value);
  const result = await api("/addresses/inspect", {method: "POST", body: JSON.stringify({address})});
  currentAddress = result.address;
  byId("recipient-label").textContent = result.label;
  byId("recipient-meta").textContent = `${result.model_id} · ${result.language}`;
  byId("recipient-fingerprint").textContent = result.fingerprint;
  byId("recipient-card").classList.remove("hidden");
  byId("fingerprint-confirmed").checked = false;
  scheduleEstimate();
  return result;
}

byId("inspect-address").addEventListener("click", async () => {
  try { await inspectAddress(); }
  catch (error) { byId("write-status").textContent = error.message; }
});

function writePayload() {
  return {
    address: currentAddress,
    prompt: byId("write-prompt").value,
    secret: byId("write-secret").value,
  };
}

async function estimate() {
  const secret = byId("write-secret").value;
  byId("budget-plain").textContent = new TextEncoder().encode(secret).length;
  if (!currentAddress || !secret || !byId("write-prompt").value) return;
  try {
    const result = await api("/messages/estimate", {method: "POST", body: JSON.stringify(writePayload())});
    byId("budget-compressed").textContent = result.compressed_body_bytes;
    byId("budget-hpke").textContent = result.hpke_overhead_bytes;
    byId("budget-stream").textContent = result.packet_bytes;
    byId("budget-tokens").textContent = result.estimated_carrier_tokens;
    byId("budget-chars").textContent = result.estimated_characters;
  } catch (_) { /* validation feedback appears on submit */ }
}

function scheduleEstimate() {
  window.clearTimeout(estimateTimer);
  estimateTimer = window.setTimeout(estimate, 350);
}

["write-prompt", "write-secret"].forEach((id) => byId(id).addEventListener("input", scheduleEstimate));

function stateLabel(value) {
  return ({queued: "Queued", framing: "Encrypting", loading_model: "Loading Qwen 3.5", generating: "Generating", validating: "Validating", decoding: "Decoding", unlocking: "Unlocking", complete: "Complete", failed: "Failed", cancelled: "Cancelled"})[value] || value;
}

function resetProtocolView() {
  const visual = byId("carrier-visual");
  visual.replaceChildren();
  visual.classList.add("empty");
  const placeholder = document.createElement("span");
  placeholder.className = "visual-placeholder";
  placeholder.textContent = "Tokens chosen with Qwen 3.5 will appear here with their section.";
  visual.append(placeholder);
  Object.keys(sectionCounts).forEach((section) => {
    sectionCounts[section] = 0;
    byId(`tokens-${section.toLowerCase()}`).textContent = "0";
  });
  byId("token-inspector").textContent = "Select a token to inspect its ID and confirmed bits.";
}

function appendProtocolToken(annotation) {
  if (typeof annotation.text !== "string") return;
  const visual = byId("carrier-visual");
  if (visual.classList.contains("empty")) {
    visual.replaceChildren();
    visual.classList.remove("empty");
  }
  const section = Object.hasOwn(sectionCounts, annotation.section) ? annotation.section : "D";
  const node = document.createElement("span");
  node.className = `protocol-token section-${section}`;
  node.textContent = annotation.text;
  node.dataset.index = annotation.token_index;
  node.dataset.tokenId = annotation.token_id;
  node.dataset.section = section;
  node.dataset.confirmedFrom = annotation.confirmed_from;
  node.dataset.confirmedTo = annotation.confirmed_to ?? annotation.confirmed_bits;
  node.title = `#${annotation.token_index} · token ${annotation.token_id} · section ${section}`;
  visual.append(node);
  sectionCounts[section] += 1;
  byId(`tokens-${section.toLowerCase()}`).textContent = sectionCounts[section];
  visual.scrollTop = visual.scrollHeight;
}

function renderProtocolAnnotations(annotations) {
  resetProtocolView();
  annotations.forEach(appendProtocolToken);
}

byId("carrier-visual").addEventListener("click", (event) => {
  const selected = event.target.closest(".protocol-token");
  if (!selected) return;
  byId("carrier-visual").querySelectorAll(".selected").forEach((node) => node.classList.remove("selected"));
  selected.classList.add("selected");
  const from = Number(selected.dataset.confirmedFrom);
  const to = Number(selected.dataset.confirmedTo);
  const delta = to - from;
  byId("token-inspector").textContent = `#${selected.dataset.index} · ID ${selected.dataset.tokenId} · section ${selected.dataset.section} · bits ${from} → ${to} (${delta >= 0 ? "+" : ""}${delta})`;
});

async function streamJob(jobId, onEvent) {
  const response = await fetch(`/api/v1/jobs/${jobId}/events`);
  if (!response.ok) throw new Error("Progress stream unavailable.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const {done, value} = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const data = block.split("\n").filter((line) => line.startsWith("data: ")).map((line) => line.slice(6)).join("\n");
      if (data) onEvent(JSON.parse(data));
    }
    if (done) break;
  }
  return api(`/jobs/${jobId}`);
}

byId("write-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  byId("write-status").textContent = "";
  byId("carrier-output").value = "";
  resetProtocolView();
  try {
    if (!currentAddress) await inspectAddress();
    const started = await api("/messages/encode", {method: "POST", body: JSON.stringify({
      ...writePayload(),
      fingerprint_confirmed: byId("fingerprint-confirmed").checked,
      live_preview: byId("live-preview").checked,
    })});
    const pill = byId("encode-state");
    pill.className = "state-pill active";
    const finished = await streamJob(started.job_id, (message) => {
      if (message.type === "state") {
        pill.textContent = stateLabel(message.state);
        if (message.state === "failed") pill.className = "state-pill error";
      }
      if (message.type === "token") {
        if (message.delta) {
          byId("carrier-output").value += message.delta;
          appendProtocolToken({...message, text: message.delta, confirmed_to: message.confirmed_bits});
        }
        if (message.total_bits) {
          const ratio = (message.confirmed_bits / message.total_bits) * 100;
          byId("encode-progress").style.width = `${Math.min(100, ratio)}%`;
        }
        byId("metric-tokens").textContent = message.token_index;
      }
    });
    if (finished.state !== "complete") throw new Error(finished.error || "Generation failed.");
    const result = finished.result;
    byId("carrier-output").value = result.carrier;
    renderProtocolAnnotations(result.token_annotations);
    byId("metric-tokens").textContent = result.tokens;
    byId("metric-speed").textContent = result.tokens_per_second.toFixed(1);
    byId("metric-k").textContent = result.k_all.toFixed(2);
    byId("encode-progress").style.width = "100%";
    pill.textContent = "Complete";
    pill.className = "state-pill";
    byId("write-status").textContent = "Carrier validated and ready to copy.";
  } catch (error) {
    byId("encode-state").textContent = "Failed";
    byId("encode-state").className = "state-pill error";
    byId("write-status").textContent = error.message;
  }
});

async function refreshIdentities() {
  try {
    const result = await api("/identities");
    const select = byId("read-identity");
    const selected = select.value;
    select.replaceChildren(new Option("Choose…", ""));
    result.identities.forEach((identity) => select.add(new Option(`${identity.label} · ${identity.fingerprint.slice(0, 24)}…`, identity.address_id)));
    select.value = selected;
  } catch (error) { byId("read-status").textContent = error.message; }
}

byId("read-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  byId("read-status").textContent = "";
  byId("secret-output").value = "";
  try {
    const started = await api("/messages/decode", {method: "POST", body: JSON.stringify({
      identity_id: byId("read-identity").value,
      passphrase: byId("read-passphrase").value,
      carrier: byId("read-carrier").value,
    })});
    const pill = byId("decode-state");
    pill.className = "state-pill active";
    const finished = await streamJob(started.job_id, (message) => {
      if (message.type === "state") pill.textContent = stateLabel(message.state);
      if (message.type === "progress") {
        const ratio = message.total_tokens ? (message.processed_tokens / message.total_tokens) * 100 : 0;
        byId("decode-progress").style.width = `${Math.min(100, ratio)}%`;
      }
    });
    byId("read-passphrase").value = "";
    if (finished.state !== "complete") throw new Error(finished.error || "Decoding failed.");
    byId("secret-output").value = finished.result.secret;
    byId("decode-progress").style.width = "100%";
    pill.textContent = "Authenticated";
    pill.className = "state-pill";
    byId("read-status").textContent = `${finished.result.plaintext_utf8_bytes} bytes recovered.`;
    await api(`/jobs/${started.job_id}`, {method: "DELETE"});
  } catch (error) {
    byId("read-passphrase").value = "";
    byId("decode-state").textContent = "Failed";
    byId("decode-state").className = "state-pill error";
    byId("read-status").textContent = error.message;
  }
});

byId("clear-secret").addEventListener("click", () => {
  byId("secret-output").value = "";
  byId("read-carrier").value = "";
  byId("read-passphrase").value = "";
  toast("Content cleared from the screen");
});

async function refreshDiagnostics() {
  try {
    const health = await fetch("/api/v1/health").then((response) => response.json());
    byId("diag-service").textContent = "Loopback service active";
    byId("diag-health").textContent = JSON.stringify(health, null, 2);
    const model = await api("/models/status");
    byId("diag-model").textContent = model.ready_on_disk ? "Artifacts present" : "Model incomplete";
    byId("diag-model-data").textContent = JSON.stringify(model, null, 2);
  } catch (error) {
    byId("diag-service").textContent = "Invalid session";
    byId("diag-health").textContent = error.message;
  }
}

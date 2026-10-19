'use strict';
const $ = id => document.getElementById(id);
const form = $('note-form');
let state, editing = null, baseline = '', busy = false, refreshJob = null;
const signatures = {};
let pending;
try { pending = JSON.parse(sessionStorage.getItem('maxpane-cr-pending') || 'null'); } catch { pending = null; }
const element = (tag, text, className) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; };
const values = () => ({view: $('view').value, kind: form.elements.kind.value, area: $('area').value, text: $('text').value});
const dirty = () => !!state && JSON.stringify(values()) !== baseline;
const tell = (message, error = false) => { const node = $(error ? 'error' : 'notice'); node.textContent = message; node.hidden = !message; };
const clearMessages = () => { tell(''); tell('', true); };
const connectivity = message => { $('connection-error').textContent = message; $('connection-error').hidden = !message; };
const keepPending = value => { pending = value; try { value ? sessionStorage.setItem('maxpane-cr-pending', JSON.stringify(value)) : sessionStorage.removeItem('maxpane-cr-pending'); } catch { /* The in-memory request ID still protects retries. */ } };
async function api(path, method = 'GET', data) {
  const options = {method, cache: 'no-store'};
  if (data !== undefined) { options.headers = {'Content-Type': 'application/json', 'X-CR-Token': state.csrf_token}; options.body = JSON.stringify(data); }
  const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 15000);
  options.signal = controller.signal;
  try {
    const response = await fetch(path, options);
    const body = response.status === 204 ? null : await response.json();
    if (!response.ok) { const error = new Error(body?.message || body?.error || `Request failed (${response.status}).`); error.status = response.status; throw error; }
    return body;
  } finally { clearTimeout(timeout); }
}
function options(select, entries, selected) {
  select.replaceChildren(...entries.map(entry => { const option = element('option', entry.label); option.value = entry.id; return option; }));
  if (entries.some(entry => entry.id === selected)) select.value = selected;
}
function areas(selected) { options($('area'), state.catalogue.find(view => view.id === $('view').value)?.areas[form.elements.kind.value] || [], selected); }
function resetEditor(note, selection) {
  editing = note ? {id: note.id, version: note.version} : null;
  const current = note || selection || values();
  if (current.view) $('view').value = current.view;
  form.elements.kind.value = current.kind || 'card'; areas(current.area);
  $('text').value = note?.text || '';
  baseline = JSON.stringify(values()); renderViews(); renderDrafts(true); updateControls();
}
function mayDiscard() { return !dirty() || confirm('Discard your unsaved changes? Your saved notes will stay in the round.'); }
function updateControls() {
  const changed = dirty(), waiting = !!pending;
  for (const input of form.elements) input.disabled = busy || !state || waiting;
  $('new-note').disabled = busy || !state || waiting;
  $('save').disabled = busy || !state || waiting || !changed || !$('text').value.trim();
  $('save').textContent = editing ? 'Save changes' : 'Save note';
  $('new-note').textContent = editing ? 'New note' : 'Clear';
  $('editor-title').textContent = editing ? 'Edit note' : 'New note';
  $('edit-state').textContent = changed ? 'Unsaved changes' : editing ? 'Saved note' : 'Not saved';
  $('send').disabled = busy || !state?.session.connected || !!state?.active_batch || changed || (!waiting && !state?.drafts.length);
  $('send').replaceChildren(document.createTextNode(waiting ? 'Retry Codex Queue' : 'Codex Queue'), element('span', '↗'));
  $('send').lastChild.setAttribute('aria-hidden', 'true');
  $('send-help').textContent = !state ? 'Connecting to this coding conversation…' : !state.session.connected ? 'No coding conversation connected. Start this workspace from your current Codex session to enable the queue.' : state.active_batch ? 'A round is in progress. Save notes here for the next round.' : changed ? 'Save or clear your unsaved changes before sending this round.' : waiting ? 'The last request could not be confirmed. Retry to check and send the same round safely.' : 'Queues the saved round in your current coding conversation.';
  for (const button of document.querySelectorAll('#drafts button, #views button')) button.disabled = busy || waiting;
  for (const button of document.querySelectorAll('#batch button')) button.disabled = busy || !state?.session.connected;
}
function renderViews() {
  if (!state) return;
  const signature = JSON.stringify([state.catalogue, state.drafts.map(note => note.view), $('view').value]);
  if (signatures.views === signature) return;
  signatures.views = signature;
  $('views').replaceChildren(...state.catalogue.map(view => {
    const button = element('button', undefined, 'view-button'); button.type = 'button';
    button.append(element('span', view.label), element('small', String(state.drafts.filter(note => note.view === view.id).length)));
    if (view.id === $('view').value) button.setAttribute('aria-current', 'page');
    button.addEventListener('click', () => { if (busy || pending || !mayDiscard()) return; showTab('active'); resetEditor(null, {view: view.id, kind: 'card'}); $('text').focus(); });
    return button;
  }));
}
function locationLabel(note) {
  const view = state.catalogue.find(item => item.id === note.view);
  const area = view?.areas[note.kind]?.find(item => item.id === note.area);
  return `${view?.label || note.view} / ${note.kind === 'card' ? 'Card' : 'Content'} / ${area?.label || note.area}`;
}
function grouped(notes, editable = false) {
  const groups = new Map();
  for (const note of notes) { const key = JSON.stringify([note.view, note.kind, note.area]); if (!groups.has(key)) groups.set(key, []); groups.get(key).push(note); }
  return [...groups.values()].map(entries => {
    const section = element('section', undefined, 'note-group'); section.append(element('h3', locationLabel(entries[0]), 'group-title'));
    for (const note of entries) {
      const article = element('article', undefined, `note${editable && editing?.id === note.id ? ' editing' : ''}`); article.append(element('p', note.text, 'note-text'));
      if (editable) {
        const actions = element('div', undefined, 'note-actions');
        for (const [label, handler] of [['Edit', () => { if (busy || pending || !mayDiscard()) return; resetEditor(note); $('text').focus(); }], ['Remove', () => removeNote(note)]]) {
          const button = element('button', label, `text-button${label === 'Remove' ? ' danger' : ''}`); button.type = 'button'; button.setAttribute('aria-label', `${label} note: ${note.text.slice(0, 70)}`); button.addEventListener('click', handler); actions.append(button);
        }
        article.append(actions);
      }
      section.append(article);
    }
    return section;
  });
}
function empty(title, detail) { const node = element('div', undefined, 'empty'); node.append(element('strong', title), document.createTextNode(detail)); return node; }
function renderDrafts(force = false) {
  if (!state) return;
  const signature = JSON.stringify([state.drafts, editing?.id]);
  if (!force && signatures.drafts === signature) return;
  signatures.drafts = signature;
  $('drafts').replaceChildren(...(state.drafts.length ? grouped(state.drafts, true) : [empty('A fresh round starts here', 'Choose a view and save your first change request.')]));
}
const statusCopy = {queued: ['Round queued', 'Your saved notes are waiting to be sent to the current coding conversation.'], delivering: ['Sending your round', 'Waiting for the coding conversation to receive this round.'], sent: ['Round sent', 'Your coding conversation has received this round.'], processing: ['Changes in progress', 'This round is being worked on. Completed changes will appear in Archive.'], failed: ['Round could not be sent', 'Retry this round to send the same saved notes.'], uncertain: ['Delivery needs checking', 'Retry this round to confirm delivery without creating a second round.']};
const batchMessage = batch => ({queued: 'Round saved and queued for delivery.', delivering: 'Round saved. Sending to your coding conversation.', sent: 'Round sent to your coding conversation.', processing: 'Round received. Changes are in progress.', completed: 'Round completed. See Archive for the results.', failed: 'Round saved, but delivery failed. Retry it below.', uncertain: 'Round saved. Delivery could not be confirmed; retry below to check.'}[batch.status] || 'Round saved.');
function renderBatch() {
  const batch = state.active_batch, signature = JSON.stringify(batch);
  if (signatures.batch === signature) return;
  signatures.batch = signature; $('batch').hidden = !batch; $('batch').replaceChildren();
  if (!batch) return;
  const copy = statusCopy[batch.status] || ['Round in progress', 'Your notes are saved.'];
  $('batch').append(element('h2', copy[0]), element('p', copy[1]));
  if (batch.error) $('batch').append(element('p', batch.error, 'error-text'));
  if (['failed', 'uncertain'].includes(batch.status)) { const retry = element('button', 'Retry Codex Queue', 'button quiet'); retry.type = 'button'; retry.addEventListener('click', () => mutate(async () => api(`/api/batches/${encodeURIComponent(batch.id)}/retry`, 'POST', {}))); $('batch').append(retry); }
  const details = element('details'); details.append(element('summary', `${batch.notes.length} submitted ${batch.notes.length === 1 ? 'note' : 'notes'}`), ...grouped(batch.notes)); $('batch').append(details);
}
function renderArchive() {
  const signature = JSON.stringify(state.archive);
  if (signatures.archive === signature) return;
  signatures.archive = signature;
  $('archive').replaceChildren(...(state.archive.length ? state.archive.map(batch => {
    const details = element('details', undefined, 'archive-entry');
    const date = new Date(batch.completed_at); const label = Number.isNaN(date.valueOf()) ? batch.completed_at : date.toLocaleString(undefined, {dateStyle: 'medium', timeStyle: 'short'});
    details.append(element('summary', `${label} — ${batch.notes.length} ${batch.notes.length === 1 ? 'note' : 'notes'}`));
    const body = element('div', undefined, 'archive-body');
    for (const [label, content] of [['Changes', batch.summary], ['Validation', batch.validation], ['Commit', batch.commit]]) { if (content) body.append(element('h3', label), element('p', typeof content === 'string' ? content : JSON.stringify(content, null, 2), label === 'Commit' ? 'metadata' : 'note-text')); }
    body.append(element('h3', 'Submitted notes'), ...grouped(batch.notes)); details.append(body); return details;
  }) : [empty('No completed rounds yet', 'Finished requests will be kept here, ready for your next round.')]));
}
function render() {
  $('connection').textContent = state.session.connected ? state.session.label || 'Conversation connected' : 'No conversation connected';
  $('connection-dot').classList.toggle('connected', state.session.connected);
  $('active-count').textContent = state.drafts.length + (state.active_batch?.notes.length || 0);
  $('archive-count').textContent = state.archive.length; $('draft-count').textContent = state.drafts.length;
  $('round-title').textContent = state.active_batch ? 'Next round' : 'Current round';
  renderViews(); renderDrafts(); renderBatch(); renderArchive(); updateControls();
}
function refresh(afterMutation = false) {
  if (refreshJob) return afterMutation ? refreshJob.catch(() => {}).then(() => refresh()) : refreshJob;
  refreshJob = (async () => {
    const first = !state; state = await api('/api/state');
    connectivity('');
    if (first) { options($('view'), state.catalogue); resetEditor(); }
    const confirmed = pending && [state.active_batch, ...state.archive].find(batch => batch && pending.notes.every(note => batch.notes.some(saved => saved.id === note.id && saved.version === note.version)));
    if (confirmed) { keepPending(null); if (editing && !dirty()) resetEditor(); tell(batchMessage(confirmed)); }
    render();
  })().finally(() => { refreshJob = null; });
  return refreshJob;
}
async function mutate(action) {
  if (busy) return;
  busy = true; clearMessages(); updateControls();
  try {
    const result = await action(); await refresh(true);
    if (result?.status) tell(batchMessage([state.active_batch, ...state.archive].find(batch => batch?.id === result.id) || result));
  }
  catch (error) {
    if (error.status === 409) await refresh(true).catch(() => {});
    tell(`${error.message}${error.status === 409 ? ' Your text is preserved. Copy your changes, then use Edit to reload the latest saved note.' : ''}`, true);
  }
  finally { busy = false; updateControls(); }
}
async function removeNote(note) {
  if (busy || pending || (editing?.id === note.id && !mayDiscard()) || !confirm('Remove this saved note from the round?')) return;
  await mutate(async () => { await api(`/api/notes/${encodeURIComponent(note.id)}`, 'DELETE', {version: note.version}); if (editing?.id === note.id) resetEditor(); tell('Note removed.'); });
}
form.addEventListener('submit', event => {
  event.preventDefault();
  if (!$('text').value.trim() || pending) return;
  mutate(async () => { const note = values(); await api(editing ? `/api/notes/${encodeURIComponent(editing.id)}` : '/api/notes', editing ? 'PATCH' : 'POST', editing ? {...note, version: editing.version} : note); resetEditor(null, note); tell('Note saved.'); });
});
form.addEventListener('input', updateControls);
$('view').addEventListener('change', () => { areas(); renderViews(); updateControls(); });
for (const radio of form.elements.kind) radio.addEventListener('change', () => { areas(); updateControls(); });
$('new-note').addEventListener('click', () => { if (mayDiscard()) { resetEditor(); $('text').focus(); } });
$('send').addEventListener('click', () => {
  if (dirty() || busy || !state?.session.connected || state.active_batch) return;
  if (!pending) keepPending({request_id: crypto.randomUUID(), notes: state.drafts.map(({id, version}) => ({id, version}))});
  mutate(async () => {
    let batch;
    try { batch = await api('/api/batches', 'POST', pending); }
    catch (error) { if (error.status >= 400 && error.status < 500) keepPending(null); throw error; }
    keepPending(null); if (editing) resetEditor(); return batch;
  });
});
function showTab(name) { for (const tab of ['active', 'archive']) { $(`${tab}-panel`).hidden = tab !== name; if (tab === name) $(`${tab}-tab`).setAttribute('aria-current', 'page'); else $(`${tab}-tab`).removeAttribute('aria-current'); } }
for (const tab of ['active', 'archive']) $(`${tab}-tab`).addEventListener('click', () => showTab(tab));
window.addEventListener('beforeunload', event => { if (dirty()) { event.preventDefault(); event.returnValue = ''; } });
updateControls();
refresh().catch(error => connectivity(`Could not load the workspace. ${error.message} Retrying automatically.`));
setInterval(() => { if (!busy && !refreshJob) refresh().catch(() => connectivity('Connection interrupted. Your unsaved text is still here; reconnecting automatically.')); }, 4000);

'use strict';

// Quiz + browse UI. Ported from the static site; questions now come from the
// JSON API, and answers are recorded for logged-in users.

// ── Category colour map ───────────────────────────────────────────────────────
const CATEGORY_COLORS = {
  'Διοικητικό Δίκαιο':                                                      'bg-success',
  'Συνταγματικό Δίκαιο':                                                    'bg-primary',
  'Οικονομικές Επιστήμες':                                                  'bg-warning text-dark',
  'Πληροφορική και Ψηφιακή Διακυβέρνηση':                                   'bg-dark',
  'Ευρωπαϊκοί Θεσμοί και Δίκαιο':                                          'bg-danger',
  'Διοίκηση Ανθρώπινου Δυναμικού':                                          'bg-info text-dark',
  'Σύγχρονη Ιστορία της Ελλάδος (1875-σήμερα)':                            'bg-secondary',
  'Κώδικας Κατάστασης Πολιτικών Διοικητικών Υπαλλήλων και Υπαλλήλων Ν.Π.Δ.Δ.': 'bg-secondary',
  'Διοίκηση Επιχειρήσεων και Οργανισμών':                                   'bg-primary',
  'Κώδικας συμπεριφοράς δημοσίων Υπαλλήλων':                               'bg-success',
  'Γενικός Κανονισμός για την Προστασία των Δεδομένων (GDPR)':              'bg-danger',
};
const LETTERS = ['α', 'β', 'γ', 'δ'];
const QUIZ_SIZE = 25;
const LOGGED_IN = document.body.dataset.auth === '1';
const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]').content;

function categoryBadge(name) {
  const cls = CATEGORY_COLORS[name] || 'bg-secondary';
  return `<span class="badge badge-category ${cls} me-1">${escHtml(name)}</span>`;
}

// ── State ─────────────────────────────────────────────────────────────────────
let catBySlug = {};       // slug → { slug, name, count }

// Quiz state
let quizSet = [];
let quizIndex = 0;
let quizAnswers = {};     // question id → chosen option index

// Quiz timing: one minute per question (25 questions → 25:00). A question's own
// time runs only while it is on screen and still unanswered; revisits add up.
const MS_PER_QUESTION = 60 * 1000;
let quizTimes = {};       // question id → ms spent on it before answering
let viewStartedAt = null; // performance.now() when the current unanswered question appeared
let quizStartedAt = 0;
let quizUsedMs = 0;       // time used when the quiz ended
let quizTimedOut = false;
let quizTimer = null;     // countdown interval
// Bumped whenever a quiz or browse load starts, so a slower, older response
// can't take over the screen (or start a second countdown) after a newer click.
let loadRun = 0;

// Browse state
let browse = { page: 1, pages: 1, total: 0, items: [] };
let browseChoice = {};    // question id → chosen index, or -1 when only revealed

// ── DOM refs ──────────────────────────────────────────────────────────────────
const elLoading        = document.getElementById('loading');
const elWelcome        = document.getElementById('welcome');
const elMessage        = document.getElementById('messageBox');
const elQuiz           = document.getElementById('quizContainer');
const elBrowse         = document.getElementById('browseContainer');
const elBrowseQ        = document.getElementById('browseQuestions');
const elPagination     = document.getElementById('pagination');
const elCategoryFilter = document.getElementById('categoryFilter');
const elPoolFilter     = document.getElementById('poolFilter');   // only when logged in
const btnQuiz          = document.getElementById('btnQuiz');
const btnBrowse        = document.getElementById('btnBrowse');

// ── API helpers ───────────────────────────────────────────────────────────────
async function api(path, options = {}) {
  const res = await fetch(path, { credentials: 'same-origin', ...options });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
  return body;
}

// timeMs: time spent on the question (quiz mode); omitted for browse answers.
function recordAttempt(q, chosen, mode, timeMs) {
  if (!LOGGED_IN) return;
  api('/api/attempts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
    body: JSON.stringify({ question_id: q.id, chosen, mode, time_ms: timeMs }),
  }).catch(err => console.warn('Η απάντηση δεν αποθηκεύτηκε:', err.message));
}

function toQuestion(item) {
  const cat = catBySlug[item.category];
  return { id: item.id, n: item.n, question: item.q, answers: item.a,
           correct: item.c, category: cat ? cat.name : item.category };
}

function selectedParams(extra = {}) {
  const params = new URLSearchParams(extra);
  if (elCategoryFilter.value) params.set('category', elCategoryFilter.value);
  return params;
}

// ── Boot ──────────────────────────────────────────────────────────────────────
async function init() {
  showSection('loading');
  let categories;
  try {
    categories = await api('/api/categories');
  } catch (e) {
    showSection('welcome');
    showMessage(`Αδυναμία φόρτωσης κατηγοριών: ${escHtml(e.message)}`);
    return;
  }
  categories.forEach(c => { catBySlug[c.slug] = c; });
  populateCategoryFilter(categories);

  // Deep links from the stats page, e.g. /?category=x&pool=wrong&start=quiz
  const params = new URLSearchParams(window.location.search);
  if (catBySlug[params.get('category')]) elCategoryFilter.value = params.get('category');
  if (elPoolFilter && ['all', 'unseen', 'wrong'].includes(params.get('pool'))) {
    elPoolFilter.value = params.get('pool');
  }
  showSection('welcome');
  if (params.get('start') === 'quiz') startQuiz();
  else if (params.get('start') === 'browse') startBrowse(1);
}

function populateCategoryFilter(categories) {
  categories
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name, 'el'))
    .forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.slug;
      opt.textContent = `${c.name} (${c.count})`;
      elCategoryFilter.appendChild(opt);
    });
}

// ── Section visibility & messages ─────────────────────────────────────────────
function showSection(name) {
  elLoading.classList.toggle('d-none', name !== 'loading');
  elWelcome.classList.toggle('d-none', name !== 'welcome');
  elQuiz.classList.toggle('d-none', name !== 'quiz');
  elBrowse.classList.toggle('d-none', name !== 'browse');
  if (name !== 'welcome') elMessage.innerHTML = '';
}

function showMessage(html, kind = 'danger') {
  elMessage.innerHTML = `<div class="alert alert-${kind}">${html}</div>`;
}

// ── QUIZ MODE ─────────────────────────────────────────────────────────────────
async function startQuiz() {
  stopQuizTimer();
  const run = ++loadRun;
  const pool = elPoolFilter ? elPoolFilter.value : 'all';
  showSection('loading');
  let data;
  try {
    data = await api('/api/quiz?' + selectedParams({ size: QUIZ_SIZE, pool }));
    if (run !== loadRun) return;
  } catch (e) {
    if (run !== loadRun) return;
    showSection('welcome');
    showMessage(`Αδυναμία φόρτωσης quiz: ${escHtml(e.message)}`);
    return;
  }
  if (data.items.length === 0) {
    showSection('welcome');
    const empty = {
      wrong: 'Δεν υπάρχουν ερωτήσεις που απαντήσατε λάθος εδώ. Μπράβο!',
      unseen: 'Έχετε ήδη απαντήσει όλες τις ερωτήσεις εδώ.',
      all: 'Δεν βρέθηκαν ερωτήσεις για αυτή την κατηγορία.',
    };
    showMessage(empty[data.pool] || empty.all, 'info');
    return;
  }
  quizSet = data.items.map(toQuestion);
  quizIndex = 0;
  quizAnswers = {};
  quizTimes = {};
  quizTimedOut = false;
  quizStartedAt = performance.now();
  quizTimer = setInterval(tickQuizClock, 250);
  showSection('quiz');
  renderQuizQuestion();
}

function quizLimitMs() {
  return quizSet.length * MS_PER_QUESTION;
}

// Abandons the running quiz clock (new quiz, or leaving for browse mode).
function stopQuizTimer() {
  clearInterval(quizTimer);
  quizTimer = null;
  viewStartedAt = null;
}

function quizDeadline() {
  return quizStartedAt + quizLimitMs();
}

// Adds the time the current question has been on screen to its total; time
// after the deadline never counts (background tabs can fire the timer late).
function pauseQuestionClock() {
  if (viewStartedAt === null) return;
  const q = quizSet[quizIndex];
  const now = Math.min(performance.now(), quizDeadline());
  quizTimes[q.id] = (quizTimes[q.id] || 0) + Math.max(0, now - viewStartedAt);
  viewStartedAt = null;
}

// A question's clock only runs while the page is visible; the countdown doesn't stop.
document.addEventListener('visibilitychange', () => {
  if (quizTimer === null) return;
  if (document.hidden) {
    pauseQuestionClock();
  } else {
    if (quizAnswers[quizSet[quizIndex].id] === undefined) viewStartedAt = performance.now();
    tickQuizClock();
  }
});

function tickQuizClock() {
  if (quizTimer === null) return;
  const remaining = quizDeadline() - performance.now();
  if (remaining <= 0) { finishQuiz(true); return; }
  const el = document.getElementById('quizClock');
  if (!el) return;
  el.textContent = fmtClock(remaining);
  el.className = 'badge ' + (remaining < 60 * 1000 ? 'bg-danger'
    : remaining < 5 * 60 * 1000 ? 'bg-warning text-dark' : 'bg-light text-dark border');
}

function finishQuiz(timedOut) {
  if (quizTimer === null) return;
  pauseQuestionClock();
  clearInterval(quizTimer);
  quizTimer = null;
  quizUsedMs = Math.min(performance.now() - quizStartedAt, quizLimitMs());
  quizTimedOut = timedOut;
  renderQuizResults();
}

function renderQuizQuestion() {
  const total = quizSet.length;
  const q = quizSet[quizIndex];
  const chosen = quizAnswers[q.id];
  const answered = chosen !== undefined;
  const pct = Math.round(((quizIndex + (answered ? 1 : 0)) / total) * 100);

  const optionsHtml = q.answers.map((text, i) => {
    let cls = 'quiz-option';
    if (answered && i === q.correct) cls += ' correct';
    else if (answered && i === chosen) cls += ' wrong';
    return `<button class="${cls}" ${answered ? 'disabled' : ''} onclick="chooseAnswer(${i})">
      <strong>${LETTERS[i]}.</strong> ${escHtml(text)}
    </button>`;
  }).join('');

  let feedbackHtml = '';
  if (answered) {
    const correct = chosen === q.correct;
    feedbackHtml = `<div class="alert ${correct ? 'alert-success' : 'alert-danger'} mt-3 mb-0">
      ${correct
        ? '<i class="fas fa-check-circle me-2"></i>Σωστά!'
        : `<i class="fas fa-times-circle me-2"></i>Λάθος! Σωστή απάντηση: <strong>${LETTERS[q.correct]}</strong>`}
    </div>`;
  }

  const isLast = quizIndex === total - 1;
  elQuiz.innerHTML = `
    <div class="mb-3">
      <div class="d-flex justify-content-between align-items-center mb-1">
        <small class="text-muted">Ερώτηση ${quizIndex + 1} / ${total}</small>
        <span class="d-flex align-items-center gap-2">
          <small class="text-muted">${pct}%</small>
          <span title="Υπολειπόμενος χρόνος"><i class="fas fa-stopwatch text-muted me-1"></i><span id="quizClock" class="badge bg-light text-dark border"></span></span>
        </span>
      </div>
      <div class="progress progress-bar-quiz">
        <div class="progress-bar" style="width:${pct}%"></div>
      </div>
    </div>
    <div class="card question-card">
      <div class="card-header">${categoryBadge(q.category)}
        <span class="badge bg-secondary ms-1">#${q.n}</span>
      </div>
      <div class="card-body">
        <div class="card-title h5 mb-4">${questionHtml(q.question)}</div>
        ${optionsHtml}
        ${feedbackHtml}
        <div class="d-flex justify-content-between mt-4">
          <button class="btn btn-outline-secondary" onclick="quizNav(-1)" ${quizIndex === 0 ? 'disabled' : ''}>
            <i class="fas fa-arrow-left me-1"></i>Προηγούμενο
          </button>
          <button class="btn btn-primary" onclick="quizNav(1)">
            ${isLast
              ? 'Αποτελέσματα <i class="fas fa-flag-checkered ms-1"></i>'
              : 'Επόμενο <i class="fas fa-arrow-right ms-1"></i>'}
          </button>
        </div>
      </div>
    </div>`;
  if (!answered && viewStartedAt === null) viewStartedAt = performance.now();
  tickQuizClock();
}

function chooseAnswer(i) {
  const q = quizSet[quizIndex];
  if (quizAnswers[q.id] !== undefined || quizTimer === null) return;
  if (performance.now() >= quizDeadline()) { finishQuiz(true); return; }
  pauseQuestionClock();
  quizAnswers[q.id] = i;
  recordAttempt(q, i, 'quiz', Math.round(quizTimes[q.id] || 0));
  renderQuizQuestion();
}

function quizNav(dir) {
  const next = quizIndex + dir;
  if (next < 0) return;
  pauseQuestionClock();
  if (next >= quizSet.length) { finishQuiz(false); return; }
  quizIndex = next;
  renderQuizQuestion();
}

// Time statistics for the finished quiz (answered questions only, except max).
function quizTimeStats() {
  const t = q => quizTimes[q.id] || 0;
  const answered = quizSet.filter(q => quizAnswers[q.id] !== undefined);
  const avg = list => (list.length ? list.reduce((sum, q) => sum + t(q), 0) / list.length : null);
  const byTime = [...answered].sort((a, b) => t(a) - t(b));
  return {
    answered: answered.length,
    avg: avg(answered),
    avgCorrect: avg(answered.filter(q => quizAnswers[q.id] === q.correct)),
    avgWrong: avg(answered.filter(q => quizAnswers[q.id] !== q.correct)),
    fastest: byTime[0],
    slowest: byTime[byTime.length - 1],
    max: Math.max(1, ...quizSet.map(t)),
  };
}

function statTile(value, label) {
  return `<div class="col-6 col-md-3"><div class="border rounded p-2 h-100">
    <div class="fs-4 fw-bold">${value}</div><small class="text-muted">${label}</small></div></div>`;
}

function renderQuizResults() {
  const total = quizSet.length;
  const correct = quizSet.filter(q => quizAnswers[q.id] === q.correct).length;
  const pct = Math.round((correct / total) * 100);
  const color = pct >= 80 ? '#198754' : pct >= 60 ? '#0d6efd' : pct >= 40 ? '#fd7e14' : '#dc3545';
  const time = quizTimeStats();
  const qNo = q => quizSet.indexOf(q) + 1;
  const timeHtml = `
    ${quizTimedOut ? `<div class="alert alert-warning text-start"><i class="fas fa-hourglass-end me-2"></i>
      Ο χρόνος έληξε. Οι ερωτήσεις που δεν απαντήσατε μετράνε ως αναπάντητες.</div>` : ''}
    <div class="row g-2 mb-2">
      ${statTile(fmtDuration(quizUsedMs), `Χρόνος (από ${fmtDuration(quizLimitMs())})`)}
      ${statTile(time.avg === null ? '—' : fmtDuration(time.avg), 'Μέσος χρόνος ανά απαντημένη ερώτηση')}
      ${statTile(time.fastest ? fmtDuration(quizTimes[time.fastest.id] || 0) : '—',
                 time.fastest ? `Ταχύτερη: ερ. ${qNo(time.fastest)}` : 'Ταχύτερη')}
      ${statTile(time.slowest ? fmtDuration(quizTimes[time.slowest.id] || 0) : '—',
                 time.slowest ? `Πιο αργή: ερ. ${qNo(time.slowest)}` : 'Πιο αργή')}
    </div>
    <p class="small text-muted mb-4">
      <i class="fas fa-check text-success me-1"></i>Μ.Ο. στις σωστές: ${time.avgCorrect === null ? '—' : fmtDuration(time.avgCorrect)}
      &nbsp;·&nbsp;
      <i class="fas fa-times text-danger me-1"></i>Μ.Ο. στις λάθος: ${time.avgWrong === null ? '—' : fmtDuration(time.avgWrong)}
      &nbsp;·&nbsp; Απαντήσατε ${time.answered} / ${total}
    </p>`;

  const reviewRows = quizSet.map((q, i) => {
    const chosen = quizAnswers[q.id];
    const ms = quizTimes[q.id] || 0;
    const outcome = chosen === undefined ? 'skip' : chosen === q.correct ? 'ok' : 'bad';
    const icon = chosen === undefined
      ? '<i class="fas fa-minus text-muted"></i>'
      : chosen === q.correct
        ? '<i class="fas fa-check text-success"></i>'
        : '<i class="fas fa-times text-danger"></i>';
    return `<tr>
      <td>${i + 1}</td>
      <td>${escHtml(q.question.substring(0, 70))}${q.question.length > 70 ? '…' : ''}</td>
      <td>${chosen === undefined ? '—' : LETTERS[chosen]}</td>
      <td>${LETTERS[q.correct]}</td>
      <td class="text-center">${icon}</td>
      <td class="time-cell" title="Ερ. ${i + 1}: ${fmtDuration(ms)}">
        <div class="d-flex align-items-center gap-2">
          <div class="time-track"><div class="time-fill time-${outcome}" style="width:${(100 * ms / time.max).toFixed(1)}%"></div></div>
          <span class="small text-nowrap">${fmtDuration(ms)}</span>
        </div>
      </td>
    </tr>`;
  }).join('');

  elQuiz.innerHTML = `
    <div class="card mb-4">
      <div class="card-header bg-primary text-white">
        <h5 class="mb-0"><i class="fas fa-trophy me-2"></i>Αποτελέσματα Quiz</h5>
      </div>
      <div class="card-body text-center py-4">
        <div class="score-circle" style="border-color:${color}; color:${color};">
          <div>${correct}/${total}</div>
          <div style="font-size:1rem;font-weight:400">${pct}%</div>
        </div>
        <div class="progress mb-4" style="height:14px; max-width:400px; margin:0 auto;">
          <div class="progress-bar" style="width:${pct}%; background:${color}"></div>
        </div>
        ${timeHtml}
        <div class="d-flex gap-2 justify-content-center flex-wrap">
          <button class="btn btn-primary" onclick="startQuiz()"><i class="fas fa-redo me-2"></i>Νέο Quiz</button>
          <button class="btn btn-outline-secondary" onclick="renderReview()"><i class="fas fa-search me-2"></i>Ανασκόπηση Απαντήσεων</button>
          ${LOGGED_IN ? '<a class="btn btn-outline-success" href="/stats"><i class="fas fa-chart-bar me-2"></i>Η πρόοδός μου</a>' : ''}
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><strong>Σύνοψη</strong></div>
      <div class="table-responsive">
        <table class="table table-sm table-hover mb-0">
          <thead class="table-light">
            <tr><th>#</th><th>Ερώτηση</th><th>Απάντησα</th><th>Σωστή</th><th></th><th>Χρόνος</th></tr>
          </thead>
          <tbody>${reviewRows}</tbody>
        </table>
      </div>
    </div>`;
}

function renderReview() {
  const html = quizSet.map((q, i) => {
    const chosen = quizAnswers[q.id];
    const opts = q.answers.map((text, k) => {
      let cls = 'list-group-item';
      if (k === q.correct) cls += ' list-group-item-success';
      else if (k === chosen) cls += ' list-group-item-danger';
      return `<div class="${cls}">
        <strong>${LETTERS[k]}.</strong> ${escHtml(text)}
        ${k === q.correct ? '<i class="fas fa-check ms-2 text-success"></i>' : ''}
        ${k === chosen && k !== q.correct ? '<i class="fas fa-times ms-2 text-danger"></i>' : ''}
      </div>`;
    }).join('');
    const badge = chosen === q.correct
      ? '<span class="badge bg-success ms-2">Σωστή</span>'
      : chosen === undefined
        ? '<span class="badge bg-secondary ms-2">Αναπάντητη</span>'
        : '<span class="badge bg-danger ms-2">Λάθος</span>';
    return `<div class="card question-card mb-3">
      <div class="card-header d-flex align-items-center flex-wrap gap-1">
        ${categoryBadge(q.category)}
        <span class="badge bg-secondary">#${q.n}</span>
        <span class="badge bg-light text-dark">Ερ. ${i + 1}</span>
        ${badge}
        <span class="badge bg-light text-dark ms-auto"><i class="fas fa-stopwatch me-1"></i>${fmtDuration(quizTimes[q.id] || 0)}</span>
      </div>
      <div class="card-body">
        <div class="card-title h6">${questionHtml(q.question)}</div>
        <div class="list-group mt-2">${opts}</div>
      </div>
    </div>`;
  }).join('');

  elQuiz.innerHTML = `
    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
      <h5 class="mb-0">Ανασκόπηση Απαντήσεων</h5>
      <div class="d-flex gap-2">
        <button class="btn btn-sm btn-outline-secondary" onclick="renderQuizResults()">
          <i class="fas fa-arrow-left me-1"></i>Πίσω στα Αποτελέσματα
        </button>
        <button class="btn btn-sm btn-primary" onclick="startQuiz()"><i class="fas fa-redo me-1"></i>Νέο Quiz</button>
      </div>
    </div>
    ${html}`;
}

// ── BROWSE MODE ───────────────────────────────────────────────────────────────
async function startBrowse(page) {
  stopQuizTimer();
  const run = ++loadRun;
  showSection('loading');
  let data;
  try {
    data = await api('/api/questions?' + selectedParams({ page }));
    if (run !== loadRun) return;
  } catch (e) {
    if (run !== loadRun) return;
    showSection('welcome');
    showMessage(`Αδυναμία φόρτωσης ερωτήσεων: ${escHtml(e.message)}`);
    return;
  }
  browse = { page: data.page, pages: data.pages, total: data.total, items: data.items.map(toQuestion) };
  browseChoice = {};
  showSection('browse');
  elBrowseQ.innerHTML = `<p class="text-muted small">${data.total} ερωτήσεις — σελίδα ${data.page} / ${data.pages}</p>`
    + browse.items.map(browseCard).join('');
  renderPagination();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function browseCard(q) {
  const choice = browseChoice[q.id];
  const done = choice !== undefined;
  const opts = q.answers.map((text, i) => {
    let cls = 'answer-btn btn w-100 mb-1 text-start';
    if (done && i === q.correct) cls += choice === -1 ? ' revealed' : ' correct';
    else if (done && i === choice) cls += ' wrong';
    return `<button class="${cls}" ${done ? 'disabled' : ''} onclick="browseAnswer(${escHtml(JSON.stringify(q.id))}, ${i})">
      <strong>${LETTERS[i]}.</strong> ${escHtml(text)}
      ${done && i === q.correct ? '<i class="fas fa-check ms-2"></i>' : ''}
    </button>`;
  }).join('');

  let status = '';
  if (choice === -1) status = '<span class="badge bg-success ms-auto"><i class="fas fa-eye me-1"></i>Αποκαλύφθηκε</span>';
  else if (done && choice === q.correct) status = '<span class="badge bg-success ms-auto"><i class="fas fa-check me-1"></i>Σωστά</span>';
  else if (done) status = '<span class="badge bg-danger ms-auto"><i class="fas fa-times me-1"></i>Λάθος</span>';

  return `<div class="card question-card" id="bq-${escHtml(q.id)}">
    <div class="card-header d-flex align-items-center flex-wrap gap-1">
      ${categoryBadge(q.category)}
      <span class="badge bg-secondary">#${q.n}</span>
      ${status}
    </div>
    <div class="card-body">
      <div class="card-title h6 mb-3">${questionHtml(q.question)}</div>
      <div>${opts}</div>
      ${done ? '' : `<button class="btn btn-sm btn-outline-primary mt-2" onclick="browseAnswer(${escHtml(JSON.stringify(q.id))}, -1)">
          <i class="fas fa-eye me-1"></i>Εμφάνιση σωστής απάντησης</button>`}
    </div>
  </div>`;
}

// i = chosen option index, or -1 to just reveal the answer (not recorded).
function browseAnswer(qId, i) {
  const q = browse.items.find(x => x.id === qId);
  if (!q || browseChoice[qId] !== undefined) return;
  browseChoice[qId] = i;
  if (i >= 0) recordAttempt(q, i, 'browse');
  document.getElementById(`bq-${qId}`).outerHTML = browseCard(q);
}

function renderPagination() {
  const { page, pages } = browse;
  if (pages <= 1) { elPagination.innerHTML = ''; return; }

  const maxVisible = 5;
  let start = Math.max(1, page - Math.floor(maxVisible / 2));
  const end = Math.min(pages, start + maxVisible - 1);
  if (end - start + 1 < maxVisible) start = Math.max(1, end - maxVisible + 1);

  let html = '<ul class="pagination flex-wrap">';
  html += pageItem('&laquo;', page - 1, page === 1);
  if (start > 1) {
    html += pageItem('1', 1);
    if (start > 2) html += '<li class="page-item disabled"><span class="page-link">…</span></li>';
  }
  for (let i = start; i <= end; i++) html += pageItem(i, i, false, i === page);
  if (end < pages) {
    if (end < pages - 1) html += '<li class="page-item disabled"><span class="page-link">…</span></li>';
    html += pageItem(pages, pages);
  }
  html += pageItem('&raquo;', page + 1, page === pages);
  html += '</ul>';

  elPagination.innerHTML = html;
  elPagination.querySelectorAll('.page-link[data-page]').forEach(el => {
    el.addEventListener('click', e => {
      e.preventDefault();
      const p = parseInt(el.dataset.page, 10);
      if (!isNaN(p) && p >= 1 && p <= pages) startBrowse(p);
    });
  });
}

function pageItem(label, page, disabled = false, active = false) {
  const cls = `page-item${disabled ? ' disabled' : ''}${active ? ' active' : ''}`;
  return `<li class="${cls}"><a class="page-link" href="#" data-page="${page}">${label}</a></li>`;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
// Question text may contain table rows ("| a | b |"); a "|---|---|" row under the
// first one makes it a header. All other text keeps its line breaks.
const TABLE_SEPARATOR = /^\|(\s*:?-{3,}:?\s*\|)+$/;

function questionHtml(text) {
  const blocks = [];
  for (const line of String(text).split('\n')) {
    const isRow = line.trim().startsWith('|');
    const last = blocks[blocks.length - 1];
    if (last && last.isTable === isRow) last.lines.push(line.trim());
    else blocks.push({ isTable: isRow, lines: [line.trim()] });
  }
  return blocks.map(b => (b.isTable
    ? tableHtml(b.lines)
    : `<div class="qtext">${escHtml(b.lines.join('\n'))}</div>`)).join('');
}

function tableHtml(rows) {
  const cells = row => row.replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => escHtml(c.trim()));
  const hasHeader = rows.length > 1 && TABLE_SEPARATOR.test(rows[1]);
  const head = hasHeader
    ? `<thead><tr>${cells(rows[0]).map(c => `<th>${c}</th>`).join('')}</tr></thead>` : '';
  const body = rows.slice(hasHeader ? 2 : 0).filter(r => !TABLE_SEPARATOR.test(r))
    .map(r => `<tr>${cells(r).map(c => `<td>${c}</td>`).join('')}</tr>`).join('');
  return `<div class="table-responsive"><table class="table table-bordered table-sm qtable">${head}<tbody>${body}</tbody></table></div>`;
}

// Durations: m:ss (e.g. 2:05). Countdown: mm:ss, rounded up so it never shows 00:00 early.
function fmtDuration(ms) {
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

function fmtClock(ms) {
  const s = Math.ceil(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Event listeners ───────────────────────────────────────────────────────────
btnQuiz.addEventListener('click', startQuiz);
btnBrowse.addEventListener('click', () => startBrowse(1));
elCategoryFilter.addEventListener('change', () => {
  // If a mode is already active, restart it with the new filter
  if (!elQuiz.classList.contains('d-none')) startQuiz();
  else if (!elBrowse.classList.contains('d-none')) startBrowse(1);
});
if (elPoolFilter) {
  elPoolFilter.addEventListener('change', () => {
    if (!elQuiz.classList.contains('d-none')) startQuiz();
  });
}

// Expose for inline onclick handlers
window.chooseAnswer      = chooseAnswer;
window.quizNav           = quizNav;
window.startQuiz         = startQuiz;
window.renderReview      = renderReview;
window.renderQuizResults = renderQuizResults;
window.browseAnswer      = browseAnswer;

init();

/* ══════════════════════════════════════════════════════════════════════════
   app.js — Voice Interview Agent Frontend Logic
   ══════════════════════════════════════════════════════════════════════════ */

const API = 'http://localhost:8000';

// ── State ──────────────────────────────────────────────────────────────────
let sessionId    = null;
let candidateId  = null;
let skills       = [];
let mediaRecorder = null;
let audioChunks  = [];
let isRecording  = false;
let totalSkills  = 0;
let currentSkillIdx = 0;
let questionCount = 0;
const TOTAL_QUESTIONS = 10;
let historyItems = [];

// ── DOM refs ───────────────────────────────────────────────────────────────
const landingSection  = document.getElementById('landing-section');
const setupSection     = document.getElementById('setup-section');
const interviewSection = document.getElementById('interview-section');
const summarySection   = document.getElementById('summary-section');
const dashboardSection = document.getElementById('dashboard-section');

const nameInput      = document.getElementById('name-input');
const nameContinueBtn = document.getElementById('name-continue-btn');

const navHomeBtn      = document.getElementById('nav-home-btn');
const navDashboardBtn = document.getElementById('nav-dashboard-btn');

const roleInput    = document.getElementById('role-input');
const skillInput   = document.getElementById('skill-input');
const addSkillBtn  = document.getElementById('add-skill-btn');
const skillsTags   = document.getElementById('skills-tags');
const startBtn     = document.getElementById('start-btn');

const progressText = document.getElementById('progress-text');
const progressPct  = document.getElementById('progress-pct');
const progressFill = document.getElementById('progress-fill');
const statusDot    = document.getElementById('status-dot');
const statusText   = document.getElementById('status-text');
const audioInd     = document.getElementById('audio-indicator');

const currentSkillLabel = document.getElementById('current-skill-label');
const currentQuestion   = document.getElementById('current-question');

const micBtn       = document.getElementById('mic-btn');
const micLabel     = document.getElementById('mic-label');
const waveform     = document.getElementById('waveform');

const transcriptWrap = document.getElementById('transcript-wrap');
const transcriptBox  = document.getElementById('transcript-box');
const evalWrap       = document.getElementById('eval-wrap');
const scoreBadge     = document.getElementById('score-badge');
const feedbackBox    = document.getElementById('feedback-box');

const historyCard   = document.getElementById('history-card');
const historyList   = document.getElementById('history-list');

const endBtn = document.getElementById('end-btn');

const avgScoreRing    = document.getElementById('avg-score-ring');
const avgScoreNum     = document.getElementById('avg-score-num');
const summaryText     = document.getElementById('summary-text');
const summaryHistList = document.getElementById('summary-history-list');
const restartBtn      = document.getElementById('restart-btn');

const toast = document.getElementById('toast');

// ── Toast ──────────────────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  toast.textContent = msg;
  toast.className = `toast ${type}`;
  toast.style.display = 'block';
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => { toast.style.display = 'none'; }, 4000);
}

// ── Skills Tag Management ──────────────────────────────────────────────────
function addSkill(name) {
  const s = name.trim();
  if (!s || skills.includes(s)) return;
  skills.push(s);
  renderSkills();
  skillInput.value = '';
}

function removeSkill(name) {
  skills = skills.filter(s => s !== name);
  renderSkills();
}

function renderSkills() {
  skillsTags.innerHTML = '';
  skills.forEach(s => {
    const tag = document.createElement('span');
    tag.className = 'skill-tag';
    tag.innerHTML = `${s} <button type="button" aria-label="Remove ${s}">×</button>`;
    tag.querySelector('button').addEventListener('click', () => removeSkill(s));
    skillsTags.appendChild(tag);
  });
}

addSkillBtn.addEventListener('click', () => addSkill(skillInput.value));
skillInput.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); addSkill(skillInput.value); } });

// ── Suggest Skills ─────────────────────────────────────────────────────────
const suggestSkillsBtn = document.getElementById('suggest-skills-btn');

suggestSkillsBtn.addEventListener('click', async () => {
  const role = roleInput.value.trim();
  if (!role) { showToast('Enter a target role first.', 'error'); roleInput.focus(); return; }

  suggestSkillsBtn.disabled = true;
  suggestSkillsBtn.textContent = '⏳';

  try {
    const resp = await fetch(`${API}/skills/suggest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    const data = await resp.json();
    (data.skills || []).forEach(s => addSkill(s));
    if (data.skills && data.skills.length) {
      showToast(`Added ${data.skills.length} suggested skills.`, 'success');
    }
  } catch (e) {
    showToast(`Suggest failed: ${e.message}`, 'error');
  }

  suggestSkillsBtn.disabled = false;
  suggestSkillsBtn.textContent = '✨ Suggest';
});

// ── Onboarding: Name Entry ─────────────────────────────────────────────────
nameContinueBtn.addEventListener('click', async () => {
  const name = nameInput.value.trim();
  if (!name) { showToast('Please enter your name.', 'error'); nameInput.focus(); return; }

  nameContinueBtn.disabled = true;
  nameContinueBtn.textContent = 'Registering…';

  try {
    const resp = await fetch(`${API}/candidate/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    const data = await resp.json();
    candidateId = data.id;
  } catch (e) {
    showToast(`Failed to register: ${e.message}`, 'error');
    nameContinueBtn.disabled = false;
    nameContinueBtn.textContent = 'Continue →';
    return;
  }

  nameContinueBtn.disabled = false;
  nameContinueBtn.textContent = 'Continue →';
  showSection('setup');
  roleInput.focus();
});

nameInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); nameContinueBtn.click(); }
});

// ── Section Switch ─────────────────────────────────────────────────────────
function showSection(name) {
  landingSection.style.display  = name === 'landing'   ? 'block' : 'none';
  setupSection.style.display    = name === 'setup'     ? 'block' : 'none';
  interviewSection.style.display = name === 'interview' ? 'block' : 'none';
  summarySection.style.display  = name === 'summary'   ? 'block' : 'none';
  dashboardSection.style.display = name === 'dashboard' ? 'block' : 'none';

  // Hide nav during active interview
  if (navHomeBtn) navHomeBtn.style.display = name === 'interview' ? 'none' : '';
  if (navDashboardBtn) navDashboardBtn.style.display = name === 'interview' ? 'none' : '';
}

// ── Audio Playback (base64 MP3) ────────────────────────────────────────────
function playAudioB64(b64, onEnded) {
  return new Promise(resolve => {
    const blob = b64ToBlob(b64, 'audio/mpeg');
    const url  = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.onended = () => {
      URL.revokeObjectURL(url);
      if (onEnded) onEnded();
      resolve();
    };
    audio.onerror = () => {
      URL.revokeObjectURL(url);
      if (onEnded) onEnded();
      resolve();
    };
    audio.play().catch(() => resolve());
  });
}

function b64ToBlob(b64, mime) {
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return new Blob([arr], { type: mime });
}

// ── Recording ──────────────────────────────────────────────────────────────
async function startRecording() {
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    showToast('Microphone access denied. Please allow mic permission.', 'error');
    return;
  }

  audioChunks = [];
  // Prefer webm/opus; fall back to whatever the browser offers
  const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
    ? 'audio/webm;codecs=opus'
    : MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '';

  mediaRecorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);

  mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
  mediaRecorder.onstop = () => {
    stream.getTracks().forEach(t => t.stop());
    const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
    submitAnswer(blob);
  };

  mediaRecorder.start(100); // collect data every 100ms
  isRecording = true;
  micBtn.classList.add('recording');
  micBtn.textContent = '⏹️';
  micLabel.textContent = 'Recording… click to stop';
  waveform.classList.add('active');
}

function stopRecording() {
  if (mediaRecorder && isRecording) {
    mediaRecorder.stop();
    isRecording = false;
    micBtn.classList.remove('recording');
    micBtn.textContent = '⏳';
    micBtn.disabled = true;
    micLabel.textContent = 'Processing your answer…';
    waveform.classList.remove('active');
  }
}

micBtn.addEventListener('click', () => {
  if (isRecording) stopRecording();
  else startRecording();
});

// ── Submit Answer ──────────────────────────────────────────────────────────
async function submitAnswer(blob) {
  setStatus('Transcribing & evaluating…');

  const ext = (mediaRecorder?.mimeType || 'audio/webm').includes('webm') ? 'webm' : 'wav';
  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('audio', blob, `answer.${ext}`);

  let data;
  try {
    const resp = await fetch(`${API}/session/answer`, { method: 'POST', body: formData });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    data = await resp.json();
  } catch (e) {
    showToast(`Error: ${e.message}`, 'error');
    micBtn.disabled = false;
    micBtn.textContent = '🎙️';
    micLabel.textContent = 'Click to record your answer';
    setStatus('Error — please try again');
    return;
  }

  // Show transcript
  transcriptBox.textContent = data.transcript || '(no speech detected)';
  transcriptWrap.style.display = 'block';

  // Show evaluation
  const score = data.score ?? 0;
  scoreBadge.textContent = `${score} / 10`;
  scoreBadge.className   = 'score-badge ' + (score >= 7 ? 'high' : score >= 4 ? 'mid' : 'low');
  feedbackBox.textContent = data.feedback || '—';
  evalWrap.style.display = 'block';

  // Add to local history
  historyItems.push(data);
  renderHistoryItem(data);

  if (data.is_complete) {
    finishInterview(data);
    return;
  }

  // Play next question audio
  updateProgress(data);
  await playNextQuestion(data);
}

function renderHistoryItem(data) {
  historyCard.style.display = 'block';
  const score = data.score ?? 0;
  const div = document.createElement('div');
  div.className = 'history-item';
  div.innerHTML = `
    <div class="history-item-header">
      <span class="text-muted mono">${escapeHtml(data.skill || '')}</span>
      <span class="score-badge ${score >= 7 ? 'high' : score >= 4 ? 'mid' : 'low'}">${score} / 10</span>
    </div>
    <div class="history-q">❓ ${escapeHtml(data.question || '')}</div>
    <div class="history-a">💬 ${escapeHtml(data.transcript || '')}</div>
    <div class="history-feedback">📌 ${escapeHtml(data.feedback || '')}</div>
  `;
  historyList.appendChild(div);
}

async function playNextQuestion(data) {
  const nextQ = data.next_question;
  if (!nextQ) return;

  // Update question display
  currentQuestion.textContent = nextQ;
  currentSkillLabel.textContent = data.is_followup
    ? `${data.skill || ''} — Follow-up`
    : (data.skill || '');

  setStatus('Playing question…');
  audioInd.classList.add('visible');
  micBtn.disabled = true;
  micLabel.textContent = 'Wait for the question to finish…';

  if (data.next_audio_b64) {
    await playAudioB64(data.next_audio_b64);
  }

  audioInd.classList.remove('visible');
  micBtn.disabled = false;
  micBtn.textContent = '🎙️';
  micLabel.textContent = 'Click to record your answer';
  setStatus('Ready — recording enabled');
}

function updateProgress(data) {
  questionCount = historyItems.length + 1;
  const pct = Math.round((questionCount / TOTAL_QUESTIONS) * 100);
  progressFill.style.width = `${pct}%`;
  progressText.textContent = `Question ${Math.min(questionCount, TOTAL_QUESTIONS)} of ${TOTAL_QUESTIONS}`;
  progressPct.textContent  = `${pct}%`;
}

function setStatus(msg) {
  statusText.textContent = msg;
}

// ── Finish / Summary ───────────────────────────────────────────────────────
function finishInterview(finalData) {
  progressFill.style.width = '100%';
  progressPct.textContent  = '100%';

  const allHistory = historyItems;
  const avg = allHistory.length
    ? Math.round(allHistory.reduce((a, h) => a + (h.score || 0), 0) / allHistory.length * 10) / 10
    : 0;

  avgScoreNum.textContent = avg;
  const pct = (avg / 10) * 360;
  avgScoreRing.style.setProperty('--pct', `${pct}deg`);

  summaryText.textContent = finalData.summary || 'Great effort! Review your scores above.';

  // Build full history in summary
  summaryHistList.innerHTML = '';
  allHistory.forEach(data => {
    const score = data.score ?? 0;
    const div = document.createElement('div');
    div.className = 'history-item';
    div.innerHTML = `
      <div class="history-item-header">
        <span class="text-muted mono">${escapeHtml(data.skill || '')}</span>
        <span class="score-badge ${score >= 7 ? 'high' : score >= 4 ? 'mid' : 'low'}">${score} / 10</span>
      </div>
      <div class="history-q">❓ ${escapeHtml(data.question || '')}</div>
      <div class="history-a">💬 ${escapeHtml(data.transcript || '')}</div>
      <div class="history-feedback">📌 ${escapeHtml(data.feedback || '')}</div>
    `;
    summaryHistList.appendChild(div);
  });

  showSection('summary');
}

// ── Start Interview ────────────────────────────────────────────────────────
startBtn.addEventListener('click', async () => {
  const role = roleInput.value.trim();
  if (!role) { showToast('Please enter a target role.', 'error'); roleInput.focus(); return; }
  if (!skills.length) { showToast('Please add at least one skill.', 'error'); skillInput.focus(); return; }

  startBtn.disabled = true;
  startBtn.textContent = '⏳ Starting…';

  let data;
  try {
    const resp = await fetch(`${API}/session/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_id: candidateId, role, skills }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    data = await resp.json();
  } catch (e) {
    showToast(`Failed to start: ${e.message}`, 'error');
    startBtn.disabled = false;
    startBtn.textContent = '🚀 Start Interview';
    return;
  }

  sessionId = data.session_id;
  totalSkills = skills.length;
  currentSkillIdx = 0;
  questionCount = 0;
  historyItems = [];

  // Prep interview UI
  currentSkillLabel.textContent = data.skill || skills[0];
  currentQuestion.textContent   = data.question;
  progressText.textContent = `Question 1 of ${TOTAL_QUESTIONS}`;
  progressPct.textContent  = '0%';
  progressFill.style.width = '0%';
  historyList.innerHTML    = '';
  historyCard.style.display = 'none';
  transcriptWrap.style.display = 'none';
  evalWrap.style.display = 'none';
  micBtn.textContent = '🎙️';
  micBtn.disabled = true;

  showSection('interview');
  setStatus('Playing first question…');
  audioInd.classList.add('visible');
  micLabel.textContent = 'Wait for the question to finish…';

  // Play first question
  if (data.audio_b64) {
    await playAudioB64(data.audio_b64);
  }

  audioInd.classList.remove('visible');
  micBtn.disabled = false;
  micLabel.textContent = 'Click to record your answer';
  setStatus('Ready — recording enabled');
  startBtn.disabled = false;
  startBtn.textContent = '🚀 Start Interview';
});

// ── End Early ──────────────────────────────────────────────────────────────
endBtn.addEventListener('click', async () => {
  if (!sessionId) return;
  if (!confirm('End the interview early? You will still see your results.')) return;
  try {
    await fetch(`${API}/session/end/${sessionId}`, { method: 'POST' });
  } catch (_) {}

  const avg = historyItems.length
    ? Math.round(historyItems.reduce((a, h) => a + (h.score || 0), 0) / historyItems.length * 10) / 10
    : 0;

  avgScoreNum.textContent = avg;
  summaryText.textContent = 'Interview ended early. Here are your results so far.';
  summaryHistList.innerHTML = '';
  historyItems.forEach(data => {
    const score = data.score ?? 0;
    const div = document.createElement('div');
    div.className = 'history-item';
    div.innerHTML = `
      <div class="history-item-header">
        <span class="text-muted mono">${escapeHtml(data.skill || '')}</span>
        <span class="score-badge ${score >= 7 ? 'high' : score >= 4 ? 'mid' : 'low'}">${score} / 10</span>
      </div>
      <div class="history-q">❓ ${escapeHtml(data.question || '')}</div>
      <div class="history-a">💬 ${escapeHtml(data.transcript || '')}</div>
      <div class="history-feedback">📌 ${escapeHtml(data.feedback || '')}</div>
    `;
    summaryHistList.appendChild(div);
  });
  showSection('summary');
});

// ── Restart ────────────────────────────────────────────────────────────────
restartBtn.addEventListener('click', () => {
  sessionId = null;
  candidateId = null;
  skills    = [];
  historyItems = [];
  renderSkills();
  roleInput.value  = '';
  skillInput.value = '';
  nameInput.value  = '';
  showSection('landing');
});

// ── Util ───────────────────────────────────────────────────────────────────
function escapeHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Dashboard ──────────────────────────────────────────────────────────────
async function loadDashboard() {
  document.getElementById('dashboard-candidates').innerHTML = '<p class="text-muted">Loading…</p>';

  let data;
  try {
    const resp = await fetch(`${API}/dashboard/overview`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    data = await resp.json();
  } catch (e) {
    document.getElementById('dashboard-candidates').innerHTML =
      `<p class="text-muted" style="color:var(--red)">Failed to load: ${escapeHtml(e.message)}</p>`;
    return;
  }

  // Stats
  document.getElementById('stat-candidates').textContent = data.stats.total_candidates;
  document.getElementById('stat-sessions').textContent = data.stats.total_sessions;
  document.getElementById('stat-avg').textContent = data.stats.avg_score + ' / 10';
  document.getElementById('stat-completed').textContent = data.stats.completed;

  // Candidates
  const container = document.getElementById('dashboard-candidates');
  if (!data.candidates.length) {
    container.innerHTML = '<p class="text-muted">No candidates yet.</p>';
    return;
  }

  container.innerHTML = '';
  data.candidates.forEach(c => {
    const card = document.createElement('div');
    card.className = 'dash-candidate';

    const sessionCount = c.sessions.length;
    const completedCount = c.sessions.filter(s => s.status === 'complete').length;

    card.innerHTML = `
      <div class="dash-candidate-header">
        <span class="dash-candidate-name">${escapeHtml(c.name)}</span>
        <span class="dash-candidate-meta">
          ${sessionCount} session${sessionCount !== 1 ? 's' : ''}
          &middot; ${completedCount} complete
        </span>
      </div>
    `;

    const sessionsDiv = document.createElement('div');
    sessionsDiv.className = 'dash-sessions';
    sessionsDiv.style.display = 'none';

    c.sessions.forEach(s => {
      const sessDiv = document.createElement('div');
      sessDiv.className = 'dash-session';

      const avgBadge = s.avg_score >= 7 ? 'high' : s.avg_score >= 4 ? 'mid' : 'low';
      sessDiv.innerHTML = `
        <div class="dash-session-header">
          <span class="dash-session-role">${escapeHtml(s.role)} &mdash; ${escapeHtml(s.skills.join(', '))}</span>
          <span class="score-badge ${avgBadge}">${s.avg_score}/10 avg</span>
          <span class="text-muted" style="font-size:0.72rem">${s.status === 'complete' ? 'Complete' : 'Active'}</span>
        </div>
      `;

      if (s.answers.length) {
        const answersDiv = document.createElement('div');
        answersDiv.className = 'dash-session-answers';
        answersDiv.style.display = 'none';

        let html = '<table class="dash-answer-table"><thead><tr><th>Skill</th><th>Question</th><th>Answer</th><th>Score</th><th>Feedback</th></tr></thead><tbody>';
        s.answers.forEach(a => {
          const sc = a.score ?? 0;
          html += `<tr>
            <td>${escapeHtml(a.skill)}${a.is_followup ? ' (FU)' : ''}</td>
            <td>${escapeHtml(a.question)}</td>
            <td class="transcript-cell">${escapeHtml(a.transcript || '—')}</td>
            <td><span class="score-badge ${sc >= 7 ? 'high' : sc >= 4 ? 'mid' : 'low'}">${sc}/10</span></td>
            <td>${escapeHtml(a.feedback || '—')}</td>
          </tr>`;
        });
        html += '</tbody></table>';
        answersDiv.innerHTML = html;

        sessDiv.addEventListener('click', () => {
          answersDiv.style.display = answersDiv.style.display === 'none' ? 'block' : 'none';
        });
        sessDiv.appendChild(answersDiv);
      }

      sessionsDiv.appendChild(sessDiv);
    });

    const header = card.querySelector('.dash-candidate-header');
    header.addEventListener('click', () => {
      sessionsDiv.style.display = sessionsDiv.style.display === 'none' ? 'block' : 'none';
    });

    card.appendChild(sessionsDiv);
    container.appendChild(card);
  });
}

// ── Navigation ─────────────────────────────────────────────────────────────
navDashboardBtn.addEventListener('click', () => {
  showSection('dashboard');
  loadDashboard();
});

navHomeBtn.addEventListener('click', () => {
  showSection('landing');
});

// ── Init ───────────────────────────────────────────────────────────────────
showSection('landing');

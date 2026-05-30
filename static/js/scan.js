// Scanner OMR — captura câmera ou upload, envia para o backend.
// Sem QR Code: usa marcadores OMR dos cantos e identifica a versão
// pelo melhor casamento com as versões da prova selecionada.
const video = document.getElementById('video');
const canvas = document.getElementById('snapshot');
const $start = document.getElementById('start');
const $cap = document.getElementById('capture');
const $file = document.getElementById('file');
const $res = document.getElementById('result');
const $exam = document.getElementById('exam');

let stream = null;

if ($start) $start.addEventListener('click', async () => {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' } }, audio: false });
    video.srcObject = stream;
    $cap.disabled = false; $start.textContent = '🟢 Câmera ligada';
  } catch (e) { alert('Não foi possível acessar a câmera: ' + e.message); }
});

if ($cap) $cap.addEventListener('click', () => {
  canvas.width = video.videoWidth; canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  canvas.toBlob(b => sendImage(b, 'capture.jpg'), 'image/jpeg', 0.92);
});

if ($file) $file.addEventListener('change', e => {
  const f = e.target.files[0]; if (f) sendImage(f, f.name);
});

async function sendImage(blob, name) {
  if (!$exam || !$exam.value) {
    $res.innerHTML = `<div class="flash error">Selecione a prova.</div>`;
    return;
  }
  $res.innerHTML = '<p>⏳ Analisando…</p>';
  const fd = new FormData();
  fd.append('image', blob, name);
  fd.append('student', document.getElementById('student').value || '');
  fd.append('exam_id', $exam.value);

  const r = await fetch('/api/scan', { method: 'POST', body: fd });
  const d = await r.json();
  if (d.error) {
    $res.innerHTML = `<div class="flash error">${d.error}</div>`;
    return;
  }
  const { result, version, student, exam } = d;
  const pct = result.total ? Math.round(result.correct / result.total * 100) : 0;
  const wrongHtml = result.wrong_questions && result.wrong_questions.length
    ? `<p style="margin-top:10px"><b>Questões erradas:</b> ${result.wrong_questions.join(', ')}</p>`
    : `<p style="margin-top:10px;color:var(--muted)">Nenhuma questão errada 🎉</p>`;

  $res.innerHTML = `
    <div style="text-align:center;padding:14px 0">
      <div style="font-size:42px;font-weight:800;color:var(--brand)">${result.score.toFixed(2)}/10</div>
      <p style="color:var(--muted);margin:4px 0">${result.correct} acertos de ${result.total} · ${pct}%</p>
      <span class="badge">Versão ${version.label}</span>
    </div>
    <table class="tbl" style="margin-top:10px">
      <tbody>
        <tr><td><b>Aluno</b></td><td>${student || '—'}</td></tr>
        <tr><td><b>Prova</b></td><td>${exam.title}</td></tr>
        <tr><td><b>Versão</b></td><td>${version.label}</td></tr>
        <tr><td><b>Total de questões</b></td><td>${result.total}</td></tr>
        <tr><td><b>Acertos</b></td><td>${result.correct}</td></tr>
        <tr><td><b>Erros</b></td><td>${result.wrong}</td></tr>
        <tr><td><b>Nota final</b></td><td><b>${result.score.toFixed(2)}</b></td></tr>
      </tbody>
    </table>
    ${wrongHtml}
    <details style="margin-top:12px"><summary>Detalhes por questão</summary>
      <table class="tbl"><thead><tr><th>#</th><th>Correta</th><th>Marcada</th><th></th></tr></thead><tbody>
      ${result.details.map(x => `<tr>
        <td>Q${x.q}</td>
        <td>${x.correct == null ? '—' : String.fromCharCode(65 + x.correct)}</td>
        <td>${x.marked == null ? '—' : String.fromCharCode(65 + x.marked)}</td>
        <td>${x.skipped ? '<span class="badge">—</span>' :
              (x.ok ? '<span class="badge ok">✓</span>' : '<span class="badge warn">✗</span>')}</td>
      </tr>`).join('')}
      </tbody></table>
    </details>`;
}

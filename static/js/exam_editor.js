// Editor de prova — vanilla JS
let questions = Array.isArray(window.QUESTIONS) ? window.QUESTIONS : [];

const $qs = document.getElementById('questions');

function render(){
  $qs.innerHTML = '';
  if(!questions.length){
    $qs.innerHTML = `<div class="card empty"><div class="em-ic">✍️</div>
      Adicione a primeira questão usando os botões acima.</div>`;
    return;
  }
  questions.forEach((q, idx)=>{
    const box = document.createElement('div');
    box.className = 'qbox';
    const typeLabel = {objective:'Objetiva', tf:'Verdadeiro / Falso', subjective:'Subjetiva'}[q.type];
    box.innerHTML = `
      <div class="qhead">
        <span class="qnum">Q${idx+1} · ${typeLabel}</span>
        <div style="display:flex;gap:6px">
          <button class="btn btn-sm" data-up="${idx}">↑</button>
          <button class="btn btn-sm" data-down="${idx}">↓</button>
          <button class="btn btn-sm btn-danger" data-del="${idx}">Excluir</button>
        </div>
      </div>
      <label>Enunciado</label>
      <textarea data-stmt="${idx}">${q.statement||''}</textarea>
      <div data-body="${idx}" style="margin-top:10px"></div>
    `;
    $qs.appendChild(box);
    const body = box.querySelector(`[data-body="${idx}"]`);
    if(q.type === 'objective'){
      (q.options||[]).forEach((opt,i)=>{
        const row = document.createElement('div');
        row.className = 'opt-row';
        row.innerHTML = `<input type="radio" name="correct-${idx}" ${q.correct===opt?'checked':''} data-mark="${idx}|${i}">
          <input type="text" value="${(opt||'').replace(/"/g,'&quot;')}" data-opt="${idx}|${i}" placeholder="Alternativa ${String.fromCharCode(65+i)}">
          <button class="btn btn-sm btn-danger" data-rmopt="${idx}|${i}">✕</button>`;
        body.appendChild(row);
      });
      const add = document.createElement('button');
      add.className = 'btn btn-sm'; add.textContent = '➕ Adicionar alternativa';
      add.dataset.addopt = idx;
      body.appendChild(add);
    } else if(q.type === 'tf'){
      body.innerHTML = `<label>Resposta correta</label>
        <select data-tf="${idx}">
          <option value="true" ${q.correct===true||q.correct==='true'?'selected':''}>Verdadeiro</option>
          <option value="false" ${q.correct===false||q.correct==='false'?'selected':''}>Falso</option>
        </select>`;
    } else {
      body.innerHTML = `<p style="color:var(--muted);font-size:13px">Questão dissertativa — corrigida manualmente. Será impressa com linhas para resposta.</p>`;
    }
  });
}

function addQuestion(type){
  const q = {type, statement:'', options: type==='objective'?['','','',''] : [], correct: type==='tf'? 'true':null};
  questions.push(q); render();
}

document.querySelectorAll('.tab').forEach(t=>{
  t.addEventListener('click', ()=>{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    addQuestion(t.dataset.add);
  });
});

$qs.addEventListener('input', e=>{
  const t = e.target;
  if(t.dataset.stmt!==undefined) questions[+t.dataset.stmt].statement = t.value;
  if(t.dataset.opt){ const [i,j]=t.dataset.opt.split('|').map(Number);
    questions[i].options[j] = t.value;
    // se essa alternativa estava marcada como correta, atualiza o texto-correto
    const radio = $qs.querySelector(`[data-mark="${i}|${j}"]`);
    if(radio && radio.checked) questions[i].correct = t.value;
  }
  if(t.dataset.tf!==undefined) questions[+t.dataset.tf].correct = t.value;
});
$qs.addEventListener('change', e=>{
  const t = e.target;
  if(t.dataset.mark){ const [i,j]=t.dataset.mark.split('|').map(Number);
    questions[i].correct = questions[i].options[j] || ''; }
});
$qs.addEventListener('click', e=>{
  const t = e.target;
  if(t.dataset.del!==undefined){ questions.splice(+t.dataset.del,1); render(); }
  if(t.dataset.up!==undefined){ const i=+t.dataset.up; if(i>0){[questions[i-1],questions[i]]=[questions[i],questions[i-1]]; render();} }
  if(t.dataset.down!==undefined){ const i=+t.dataset.down; if(i<questions.length-1){[questions[i+1],questions[i]]=[questions[i],questions[i+1]]; render();} }
  if(t.dataset.addopt!==undefined){ questions[+t.dataset.addopt].options.push(''); render(); }
  if(t.dataset.rmopt){ const [i,j]=t.dataset.rmopt.split('|').map(Number); questions[i].options.splice(j,1); render(); }
});

document.getElementById('save-btn').addEventListener('click', async ()=>{
  const layoutEl = document.querySelector('input[name="layout"]:checked');
  const payload = {
    id: window.EXAM_ID, title: document.getElementById('title').value,
    subject: document.getElementById('subject').value,
    grade: document.getElementById('grade').value,
    instructions: document.getElementById('instructions').value,
    layout: layoutEl ? layoutEl.value : 'single',
    questions
  };
  const r = await fetch('/api/exams/save', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  const d = await r.json();
  if(d.id && !window.EXAM_ID) location.href = `/exams/${d.id}/edit`;
  else { const t = document.createElement('div'); t.className='flash success';
    t.textContent='Prova salva ✓'; document.querySelector('.main').prepend(t);
    setTimeout(()=>t.remove(), 2200); }
});

render();

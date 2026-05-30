// Página de detalhe: like, fav, estrelas, comentário
const $ = s => document.querySelector(s);

async function post(url, body){
  const r = await fetch(url, {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: body? JSON.stringify(body):'{}'});
  return r.json();
}

$('#like')?.addEventListener('click', async e=>{
  const id = e.currentTarget.dataset.id;
  const d = await post(`/api/library/${id}/like`);
  $('#like-c').textContent = d.count;
  e.currentTarget.classList.toggle('btn-primary', d.liked);
});

$('#fav')?.addEventListener('click', async e=>{
  const id = e.currentTarget.dataset.id;
  const d = await post(`/api/library/${id}/favorite`);
  e.currentTarget.classList.toggle('btn-primary', d.favorited);
});

const stars = document.querySelectorAll('#stars span');
stars.forEach(s=>{
  s.addEventListener('click', async ()=>{
    const v = parseInt(s.dataset.v);
    const id = document.getElementById('stars').dataset.id;
    const d = await post(`/api/library/${id}/rate`, {stars:v});
    stars.forEach((x,i)=> x.classList.toggle('off', (i+1)>v));
    $('#avg').textContent = d.avg;
  });
});

$('#comment-form')?.addEventListener('submit', async e=>{
  e.preventDefault();
  const id = e.target.dataset.id;
  const body = $('#comment-body').value.trim();
  if(!body) return;
  const d = await post(`/api/library/${id}/comment`, {body});
  $('#comment-body').value='';
  const el = document.createElement('div');
  el.style.cssText = 'border-bottom:1px solid var(--line);padding-bottom:10px';
  el.innerHTML = `<b>${d.user}</b> <span style="color:var(--muted);font-size:12px">${d.created_at}</span>
    <p style="margin:4px 0 0"></p>`;
  el.querySelector('p').textContent = d.body;
  $('#comments').prepend(el);
});

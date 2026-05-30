// Like + Favoritar a partir dos cards da biblioteca
document.querySelectorAll('.icon-btn.like').forEach(b=>{
  b.addEventListener('click', async e=>{
    e.preventDefault();
    const id=b.dataset.id;
    const r=await fetch(`/api/library/${id}/like`,{method:'POST'});
    const d=await r.json();
    b.classList.toggle('active', d.liked);
    b.querySelector('span').textContent = d.count;
  });
});
document.querySelectorAll('.icon-btn.fav').forEach(b=>{
  b.addEventListener('click', async e=>{
    e.preventDefault();
    const id=b.dataset.id;
    const r=await fetch(`/api/library/${id}/favorite`,{method:'POST'});
    const d=await r.json();
    b.classList.toggle('active', d.favorited);
  });
});

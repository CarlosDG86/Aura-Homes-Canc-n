// Aura Homes Cancún — showcase interactions
(function(){
  // Gallery lightbox
  var lb = document.querySelector('.lightbox');
  if(lb){
    var lbImg = lb.querySelector('img');
    function open(src){ lbImg.src = src; lb.classList.add('open'); }
    function close(){ lb.classList.remove('open'); }
    document.querySelectorAll('[data-full]').forEach(function(el){
      el.addEventListener('click', function(){ open(el.getAttribute('data-full')); });
    });
    lb.addEventListener('click', close);
    document.addEventListener('keydown', function(e){ if(e.key==='Escape') close(); });
    // thumbnails swap the lead image
    var lead = document.querySelector('.gallery-lead img');
    document.querySelectorAll('.thumbs img').forEach(function(t){
      t.addEventListener('click', function(){ if(lead){ lead.src = t.src; } });
    });
    if(lead){ lead.style.cursor='zoom-in'; lead.addEventListener('click', function(){ open(lead.src); }); }
  }

  // Contact form -> compose email (no backend). A form service can be wired later
  // by setting data-endpoint on the <form> (see README).
  document.querySelectorAll('form[data-contact]').forEach(function(f){
    f.addEventListener('submit', function(e){
      e.preventDefault();
      var endpoint = f.getAttribute('data-endpoint');
      var to = f.getAttribute('data-email');
      var subj = f.getAttribute('data-subject') || 'Consulta — Aura Homes Cancún';
      var d = new FormData(f);
      var body = 'Nombre: '+(d.get('name')||'')+'\n'+
                 'Email: '+(d.get('email')||'')+'\n'+
                 'Teléfono: '+(d.get('phone')||'')+'\n\n'+
                 (d.get('message')||'');
      if(endpoint){
        fetch(endpoint,{method:'POST',body:d,headers:{'Accept':'application/json'}})
          .then(function(){ f.reset(); alert(f.getAttribute('data-ok')||'¡Enviado! Te contactaremos pronto.'); })
          .catch(function(){ window.location.href='mailto:'+to+'?subject='+encodeURIComponent(subj)+'&body='+encodeURIComponent(body); });
      } else {
        window.location.href='mailto:'+to+'?subject='+encodeURIComponent(subj)+'&body='+encodeURIComponent(body);
      }
    });
  });
})();

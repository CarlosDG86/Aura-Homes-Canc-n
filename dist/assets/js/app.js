// Aura Homes Cancún — showcase interactions
(function(){
  // Gallery lightbox with prev/next navigation
  var lb = document.querySelector('.lightbox');
  if(lb){
    var lbImg = lb.querySelector('img');
    var lead = document.querySelector('.gallery-lead img');
    var images = [];
    var idx = 0;

    if(lead){ images.push(lead.src); }
    document.querySelectorAll('.thumbs img').forEach(function(t){ images.push(t.src); });

    // prev/next buttons, added once
    var prevBtn = document.createElement('button');
    prevBtn.type = 'button'; prevBtn.className = 'lb-nav lb-prev'; prevBtn.setAttribute('aria-label','Previous image');
    prevBtn.innerHTML = '&#10094;';
    var nextBtn = document.createElement('button');
    nextBtn.type = 'button'; nextBtn.className = 'lb-nav lb-next'; nextBtn.setAttribute('aria-label','Next image');
    nextBtn.innerHTML = '&#10095;';
    lb.appendChild(prevBtn);
    lb.appendChild(nextBtn);

    function show(i){
      if(images.length === 0) return;
      idx = (i + images.length) % images.length;
      lbImg.src = images[idx];
    }
    function open(src){
      var found = images.indexOf(src);
      idx = found >= 0 ? found : 0;
      show(idx);
      lb.classList.add('open');
    }
    function close(){ lb.classList.remove('open'); }
    function stop(e){ e.stopPropagation(); }

    document.querySelectorAll('[data-full]').forEach(function(el){
      el.addEventListener('click', function(){ open(el.getAttribute('data-full')); });
    });
    lb.addEventListener('click', close);
    prevBtn.addEventListener('click', function(e){ stop(e); show(idx - 1); });
    nextBtn.addEventListener('click', function(e){ stop(e); show(idx + 1); });
    document.addEventListener('keydown', function(e){
      if(!lb.classList.contains('open')) return;
      if(e.key==='Escape') close();
      if(e.key==='ArrowLeft') show(idx - 1);
      if(e.key==='ArrowRight') show(idx + 1);
    });
    // thumbnails swap the lead image and open the lightbox on that image
    document.querySelectorAll('.thumbs img').forEach(function(t, i){
      t.addEventListener('click', function(){ if(lead){ lead.src = t.src; } open(t.src); });
    });
    if(lead){ lead.style.cursor='zoom-in'; lead.addEventListener('click', function(){ open(lead.src); }); }
  }

  // Property list filters (zone / beds / price) — client-side, no reload
  var filterSelects = document.querySelectorAll('[data-filter]');
  if(filterSelects.length){
    var grid = document.querySelector('.grid[data-results-none-label]');
    var cards = grid ? Array.prototype.slice.call(grid.querySelectorAll('.card')) : [];
    var countEl = document.querySelector('[data-results-count]');
    var labelEl = document.querySelector('[data-results-label]');
    var defaultLabel = labelEl ? labelEl.textContent : '';
    var noneLabel = grid ? grid.getAttribute('data-results-none-label') : '';

    function applyFilters(){
      var zone = (document.querySelector('[data-filter="zone"]') || {}).value || '';
      var beds = (document.querySelector('[data-filter="beds"]') || {}).value || '';
      var price = (document.querySelector('[data-filter="price"]') || {}).value || '';
      var visible = 0;
      cards.forEach(function(c){
        var okZone = !zone || c.getAttribute('data-zone') === zone;
        var okBeds = !beds || Number(c.getAttribute('data-beds')) >= Number(beds);
        var okPrice = !price || c.getAttribute('data-price') === price;
        var show = okZone && okBeds && okPrice;
        c.style.display = show ? '' : 'none';
        if(show) visible++;
      });
      if(visible === 0){
        if(countEl){ countEl.style.display = 'none'; }
        if(labelEl){ labelEl.textContent = noneLabel; }
      } else {
        if(countEl){ countEl.style.display = ''; countEl.textContent = visible; }
        if(labelEl){ labelEl.textContent = defaultLabel; }
      }
    }
    filterSelects.forEach(function(sel){ sel.addEventListener('change', applyFilters); });
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

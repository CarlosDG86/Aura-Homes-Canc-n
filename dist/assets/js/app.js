// Aura Homes Cancún — showcase interactions
(function(){
  // Gallery lightbox with prev/next navigation
  var lb = document.querySelector('.lightbox');
  if(lb){
    var lbImg = lb.querySelector('img');
    var lead = document.querySelector('.gallery-lead img');
    var images = [], alts = [];
    var idx = 0, opener = null;
    var closeBtn = lb.querySelector('.x');

    if(lead){ images.push(lead.src); alts.push(lead.alt); }
    document.querySelectorAll('.thumbs img').forEach(function(t){ images.push(t.src); alts.push(t.alt); });

    // prev/next buttons, added once
    var prevBtn = document.createElement('button');
    prevBtn.type = 'button'; prevBtn.className = 'lb-nav lb-prev'; prevBtn.setAttribute('aria-label', lb.getAttribute('data-prev') || 'Previous image');
    prevBtn.innerHTML = '&#10094;';
    var nextBtn = document.createElement('button');
    nextBtn.type = 'button'; nextBtn.className = 'lb-nav lb-next'; nextBtn.setAttribute('aria-label', lb.getAttribute('data-next') || 'Next image');
    nextBtn.innerHTML = '&#10095;';
    lb.appendChild(prevBtn);
    lb.appendChild(nextBtn);

    function show(i){
      if(images.length === 0) return;
      idx = (i + images.length) % images.length;
      lbImg.src = images[idx];
      lbImg.alt = alts[idx] || '';
    }
    function open(src){
      var found = images.indexOf(src);
      idx = found >= 0 ? found : 0;
      show(idx);
      opener = document.activeElement;
      lb.classList.add('open');
      if(closeBtn){ closeBtn.focus(); }
    }
    function close(){
      lb.classList.remove('open');
      if(opener && opener.focus){ opener.focus(); }
    }
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
      if(e.key==='Tab'){
        // el foco no se escapa del diálogo mientras está abierto
        var f = [closeBtn, prevBtn, nextBtn].filter(Boolean);
        var i = f.indexOf(document.activeElement);
        e.preventDefault();
        f[(i + (e.shiftKey ? -1 : 1) + f.length) % f.length].focus();
      }
      if(e.key==='ArrowLeft') show(idx - 1);
      if(e.key==='ArrowRight') show(idx + 1);
    });
    // thumbnails swap the lead image and open the lightbox on that image
    document.querySelectorAll('.thumbs img').forEach(function(t, i){
      t.addEventListener('click', function(){ if(lead){ lead.src = t.src; } open(t.src); });
      t.addEventListener('keydown', function(e){
        if(e.key==='Enter' || e.key===' '){ e.preventDefault(); open(t.src); }
      });
    });
    if(closeBtn){ closeBtn.addEventListener('click', function(e){ stop(e); close(); }); }
    if(lead){ lead.classList.add('zoomable'); lead.addEventListener('click', function(){ open(lead.src); });
      lead.addEventListener('keydown', function(e){ if(e.key==='Enter' || e.key===' '){ e.preventDefault(); open(lead.src); } }); }
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

  // Header nav: mark the current item so CSS can render it UPPERCASE + underlined.
  // - On the property listing / detail pages, "Propiedades" is the active item.
  // - On the home page, scroll-spy the sections that have a matching nav anchor
  //   (#como, #contacto) and light up whichever one you're currently reading.
  (function(){
    var links = document.querySelectorAll('.nav-links a[data-nav]');
    if(!links.length) return;
    function setActive(key){
      links.forEach(function(a){ a.classList.toggle('active', a.getAttribute('data-nav') === key); });
    }
    if(/\/(propiedades|properties)\//.test(location.pathname)){ setActive('props'); return; }

    var sections = ['como','contacto']
      .map(function(k){ var el = document.getElementById(k); return el ? {key:k, el:el} : null; })
      .filter(Boolean);
    if(!sections.length) return;

    var topbar = document.querySelector('.topbar');
    function top(el){ return el.getBoundingClientRect().top + window.scrollY; }
    function onScroll(){
      var line = window.scrollY + (topbar ? topbar.offsetHeight : 0) + 24;
      var key = '';
      sections.forEach(function(s){ if(top(s.el) <= line){ key = s.key; } });
      setActive(key); // '' clears all when you're above the first tracked section
    }
    window.addEventListener('scroll', onScroll, {passive:true});
    window.addEventListener('resize', onScroll);
    onScroll();
  })();

  // Aviso de cookies y medición (D-034).
  //
  // La elección vive en localStorage —no es una cookie y no sale del equipo—.
  // Sin elección guardada se muestra el aviso; la medición (Cloudflare Web
  // Analytics, sin cookies) se carga SOLO con «granted» y SOLO si hay token en
  // site.json. Cualquier fallo del almacenamiento (modo privado) cuenta como
  // «sin elección»: se vuelve a preguntar, nunca se asume un sí.
  (function(){
    var banner = document.querySelector('[data-cookie-banner]');
    if(!banner) return;
    var KEY = 'aura-consent';
    var token = banner.getAttribute('data-token');
    function get(){ try { return localStorage.getItem(KEY); } catch(e){ return null; } }
    function set(v){ try { localStorage.setItem(KEY, v); } catch(e){} }
    function loadAnalytics(){
      if(!token || document.querySelector('script[data-cf-beacon]')) return;
      var sc = document.createElement('script');
      sc.defer = true;
      sc.src = 'https://static.cloudflareinsights.com/beacon.min.js';
      sc.setAttribute('data-cf-beacon', JSON.stringify({token: token}));
      document.body.appendChild(sc);
    }
    function decide(v){
      var before = get();
      set(v);
      banner.hidden = true;
      if(v === 'granted'){ loadAnalytics(); }
      // retirar el permiso no puede descargar un script ya cargado: se recarga
      else if(before === 'granted'){ location.reload(); }
    }
    banner.querySelectorAll('[data-consent]').forEach(function(b){
      b.addEventListener('click', function(){ decide(b.getAttribute('data-consent')); });
    });
    document.querySelectorAll('[data-cookie-prefs]').forEach(function(b){
      b.addEventListener('click', function(){
        banner.hidden = false;
        var first = banner.querySelector('button');
        if(first){ first.focus(); }
      });
    });
    var c = get();
    if(c === 'granted'){ loadAnalytics(); }
    else if(c !== 'denied'){ banner.hidden = false; }
  })();
})();

#!/usr/bin/env python3
# Aura Homes Cancún — static site generator (showcase MVP)
import json, os, shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
site = json.load(open(os.path.join(ROOT, "data/site.json"), encoding="utf-8"))
props = json.load(open(os.path.join(ROOT, "data/properties.json"), encoding="utf-8"))
B = site["brand"]
LIVE = [p for p in props if not p.get("placeholder")]  # only real inventory renders on the live site

HOUSE = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
         'stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/>'
         '<path d="M5 9.5V21h14V9.5"/><path d="M9.5 21v-6h5v6"/></svg>')
WA = ('<svg viewBox="0 0 24 24" fill="currentColor"><path d="M17.5 14.4c-.3-.15-1.7-.84-2-.94-.26-.1-.45-.15-.64.15'
      '-.19.29-.74.94-.9 1.13-.17.19-.33.22-.62.07-.29-.15-1.23-.45-2.34-1.44-.86-.77-1.44-1.72-1.6-2-.17-.3-.02-.45.12-.6'
      '.13-.13.29-.33.44-.5.15-.16.19-.28.29-.47.1-.19.05-.36-.02-.5-.08-.15-.64-1.55-.88-2.12-.23-.55-.47-.48-.64-.49h-.55'
      'c-.19 0-.5.07-.76.36-.26.29-1 .98-1 2.4 0 1.42 1.02 2.79 1.17 2.98.14.19 2.02 3.08 4.9 4.32.68.29 1.22.47 1.63.6'
      '.69.22 1.31.19 1.8.11.55-.08 1.7-.69 1.94-1.37.24-.67.24-1.25.17-1.37-.07-.12-.26-.19-.55-.34z"/>'
      '<path d="M12 2a10 10 0 0 0-8.5 15.3L2 22l4.8-1.5A10 10 0 1 0 12 2zm0 18a8 8 0 0 1-4.1-1.1l-.3-.2-2.9.9.9-2.8-.2-.3'
      'A8 8 0 1 1 12 20z"/></svg>')
CHECK = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" '
         'stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>')

def money_mxn(n): return "$" + format(n, ",d") + " MXN"
def money_usd(n): return "\u2248 $" + format(int(round(n / B["fxRate"] / 50.0) * 50), ",d") + " USD"

def other_home(lang): return "../index.html" if False else ("../" + site["ui"][lang]["other"] + "/")

def mark(color_class=""):
    return (f'<div class="mark {color_class}"><span class="m1">{HOUSE}{B["name"]}</span>'
            f'<span class="m2">{B["city"]}</span></div>')

def wa_link(text=""):
    msg = "Hola, me interesa una propiedad de Aura Homes Cancún"
    return f'https://wa.me/{B["whatsapp"].lstrip("+")}?text=' + msg.replace(" ", "%20")

def topbar(lang, page, prop=None):
    t = site["ui"][lang]; o = t["other"]
    # language toggle targets
    if page == "home":
        es_url, en_url = "../es/", "../en/"
    elif page == "index":
        es_url, en_url = "../../es/propiedades/", "../../en/properties/"
    else:
        es_url = f'../../es/propiedades/{prop["slug"]["es"]}.html'
        en_url = f'../../en/properties/{prop["slug"]["en"]}.html'
    home = "../es/" if lang == "es" else "../en/"
    if page != "home":
        home = "../../es/" if lang == "es" else "../../en/"
    plist = ("../propiedades/" if lang=="es" else "../properties/") if page!="home" else ("propiedades/" if lang=="es" else "properties/")
    nav = t["nav"]
    links = (f'<nav class="nav-links"><a href="{plist}">{nav["props"]}</a>'
             f'<a href="{home}#zonas">{nav["zones"]}</a><a href="{home}#como">{nav["how"]}</a>'
             f'<a href="{home}#contacto">{nav["contact"]}</a></nav>')
    lang_tog = (f'<span class="lang"><a href="{es_url}" class="{"on" if lang=="es" else ""}">ES</a>'
                f'<a href="{en_url}" class="{"on" if lang=="en" else ""}">EN</a></span>')
    return (f'<header class="topbar"><div class="wrap"><a href="{home}">{mark()}</a>'
            f'{links}<div class="topbar-right">{lang_tog}'
            f'<a class="wa-icon" href="{wa_link()}" aria-label="WhatsApp">{WA}</a>'
            f'<a class="wa-pill" href="{wa_link()}">{WA}{t["wa"]}</a></div></div></header>')

def footer(lang, page):
    t = site["ui"][lang]
    home = ("../es/" if lang=="es" else "../en/") if page=="home" else ("../../es/" if lang=="es" else "../../en/")
    plist = ("propiedades/" if lang=="es" else "properties/") if page=="home" else ("../propiedades/" if lang=="es" else "../properties/")
    return f'''<footer class="footer"><div class="wrap"><div class="cols">
      <div class="brandcol">{mark()}<p>{t["footer_tagline"]}</p></div>
      <div><h4>{t["footer_explore"]}</h4><ul><li><a href="{plist}">{t["nav"]["props"]}</a></li>
        <li><a href="{home}#zonas">{t["nav"]["zones"]}</a></li><li><a href="{home}#como">{t["nav"]["how"]}</a></li></ul></div>
      <div><h4>{t["footer_legal"]}</h4><ul><li><a href="#">{t["privacy"]}</a></li><li><a href="#">{t["terms"]}</a></li></ul></div>
      <div><h4>{t["footer_contact"]}</h4><ul><li><a href="{wa_link()}">WhatsApp</a></li>
        <li><a href="mailto:{B["email"]}">{B["email"]}</a></li></ul></div></div>
      <div class="footer-bottom"><span>© 2026 {B["name"]} {B["city"].title()}</span><span>{t["made"]}</span></div>
    </div></footer>'''

def card(p, lang, base):
    t = site["ui"][lang]
    detail = (f'{p["slug"][lang]}.html') if base=="index" else (("propiedades/" if lang=="es" else "properties/") + f'{p["slug"][lang]}.html')
    img = f'{"../.." if base=="index" else ".."}/assets/img/aur-001/{p["hero"]}'
    rented = p["status"] == "rented"
    seal = f'<span class="seal">{t["rented"]}</span>' if rented else ""
    tag = "" if rented else f'<span class="card-tag">{t["hero_eyebrow"].split("·")[0].strip()}</span>'
    usd = f'<span class="sub">{money_usd(p["priceMXN"])} {t["per"]}</span>' if lang=="en" else ""
    price = money_mxn(p["priceMXN"]) if lang=="es" else money_usd(p["priceMXN"])
    persub = "" if lang=="en" else ""
    price_html = (f'<div class="card-price">{money_mxn(p["priceMXN"])} <span class="per">{t["per"]}</span></div>' if lang=="es"
                  else f'<div class="card-price">{money_usd(p["priceMXN"])} <span class="per">{t["per"]}</span></div>')
    specs = f'{p["beds"]} {("rec" if lang=="es" else "bd")} · {p["baths"]} {("baños" if lang=="es" else "ba")} · {p["area"]} m²'
    inner = (f'<div class="card-img">{seal}{tag}<img src="{img}" alt="{p["title"][lang]}" loading="lazy"></div>'
             f'<div class="card-body"><div class="card-title">{p["title"][lang]}</div>{price_html}'
             f'<div class="card-zone">{p["zone"]} · Cancún</div><div class="card-specs">{specs}</div></div>')
    cls = "card rented" if rented else "card"
    if rented:
        return f'<div class="{cls}">{inner}</div>'
    return f'<div class="{cls}"><a href="{detail}">{inner}</a></div>'

def page_shell(lang, title, body, page):
    t = site["ui"][lang]
    css = "../assets/css/styles.css" if page=="home" else "../../assets/css/styles.css"
    js = css.replace("css/styles.css", "js/app.js")
    return f'''<!doctype html><html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><meta name="description" content="{t["hero_sub"]}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{css}"></head><body>{body}
<div class="lightbox"><span class="x">&times;</span><img alt=""></div>
<script src="{js}"></script></body></html>'''

# ---------- HOME ----------
def build_home(lang):
    t = site["ui"][lang]
    featured = [p for p in LIVE if p.get("featured")]
    hero_img = "../assets/img/aur-001/vistaFrente.jpg"
    cards = "".join(card(p, lang, "home") for p in featured)
    trust = "".join(f'<div class="trust-item"><div class="ic">{HOUSE}</div><h3>{a}</h3><p>{b}</p></div>' for a,b in t["trust"])
    steps = "".join(f'<div class="step"><div class="n">{i+1}</div><div><h3>{a}</h3><p>{b}</p></div></div>' for i,(a,b) in enumerate(t["how"]))
    body = f'''{topbar(lang,"home")}
<main class="page">
  <section class="hero"><div class="wrap hero-inner">
    <div><div class="eyebrow hero-eyebrow">{t["hero_eyebrow"]}</div>
      <h1>{t["hero_title"]}</h1><p class="sub">{t["hero_sub"]}</p>
      <div class="hero-actions"><a class="btn btn-cta" href="{("propiedades/" if lang=="es" else "properties/")}">{t["hero_cta"]}</a>
        <a class="btn btn-wa" href="{wa_link()}">{WA}{t["wa"]}</a></div>
      <div class="hero-note"><span class="dot"></span>{t["reply_note"]}</div></div>
    <div class="hero-media"><img src="{hero_img}" alt="{t["hero_title"]}"></div>
  </div></section>

  <section class="section"><div class="wrap">
    <div class="section-head"><h2>{t["featured"]}</h2><a href="{("propiedades/" if lang=="es" else "properties/")}">{t["see_all"]} →</a></div>
    <div class="grid">{cards}</div></div></section>

  <section class="section" id="zonas"><div class="wrap">
    <div class="section-head"><h2>{t["trust_title"]}</h2></div>
    <div class="trust-grid">{trust}</div></div></section>

  <section class="section section-teal" id="como"><div class="wrap">
    <div class="section-head"><h2>{t["how_title"]}</h2></div><div class="steps">{steps}</div></div></section>

  <section class="section" id="contacto"><div class="wrap contact-two">
    <div><div class="eyebrow">{t["nav"]["contact"]}</div><h2 style="font-size:28px;margin:8px 0 10px">{t["contact_title"]}</h2>
      <p style="color:var(--text-2);max-width:44ch">{t["contact_sub"]}</p>
      <div class="hero-note"><span class="dot"></span>{t["reply_note"]}</div></div>
    <div class="contact-card">
      <form data-contact data-email="{B["email"]}" data-subject="Consulta — Aura Homes Cancún">
        <div class="field"><label>{t["form_name"]}</label><input name="name" required></div>
        <div class="field"><label>{t["form_email"]}</label><input type="email" name="email" required></div>
        <div class="field"><label>{t["form_phone"]}</label><input name="phone"></div>
        <div class="field"><label>{t["form_msg"]}</label><textarea name="message"></textarea></div>
        <button class="btn btn-cta btn-block" type="submit">{t["form_send"]}</button>
      </form>
      <div class="or">{t["or"]}</div>
      <div class="contact-alt"><a class="btn btn-wa btn-block" href="{wa_link()}">{WA}{t["wa_btn"]}</a>
        <a class="btn btn-outline btn-block" href="mailto:{B["email"]}">{t["email_btn"]}</a></div>
    </div></div></section>
</main>
{footer(lang,"home")}
<a class="fab-wa" href="{wa_link()}" aria-label="WhatsApp">{WA}</a>'''
    return page_shell(lang, f'{B["name"]} {B["city"].title()} — {t["hero_title"]}', body, "home")

# ---------- INDEX ----------
def build_index(lang):
    t = site["ui"][lang]
    cards = "".join(card(p, lang, "index") for p in LIVE)
    body = f'''{topbar(lang,"index")}
<main class="page"><div class="wrap">
  <div class="pagehead"><h1>{t["index_title"]}</h1><div class="sub">{t["index_sub"]}</div></div>
  <div class="filters"><span class="chip">{t["filter_zone"]} ▾</span><span class="chip">{t["filter_beds"]} ▾</span><span class="chip">{t["filter_price"]} ▾</span></div>
  <div class="results">{len(LIVE)} {t["results"]}</div>
  <div class="grid" style="padding-bottom:48px">{cards}</div>
</div></main>{footer(lang,"index")}
<a class="fab-wa" href="{wa_link()}" aria-label="WhatsApp">{WA}</a>'''
    return page_shell(lang, f'{t["index_title"]} — {B["name"]} {B["city"].title()}', body, "index")

# ---------- DETAIL ----------
def build_detail(p, lang):
    t = site["ui"][lang]
    imgbase = "../../assets/img/aur-001/"
    lead = imgbase + p["gallery"][0]
    thumbs = "".join(f'<img src="{imgbase}{g}" alt="{p["title"][lang]}" loading="lazy">' for g in p["gallery"][1:13])
    specs = [
        (str(p["beds"]), t["specs_beds"]), (str(p["baths"]), t["specs_baths"]), (str(p["area"]), t["specs_area"]),
        ("—" if not p["furnished"] else "✓", t["specs_furnished"]),
        (str(p["parking"]), t["specs_parking"]), ("✓" if p["pets"] else "—", t["specs_pets"]),
    ]
    specs_html = "".join(f'<div class="spec"><span class="v">{v}</span><span class="l">{l}</span></div>' for v,l in specs)
    amen = "".join(f'<li>{CHECK}<span>{a}</span></li>' for a in p["amenities"][lang])
    contract = "".join(f'<div class="row"><span class="k">{k}</span><span class="v">{v}</span></div>' for k,v in p["contract"][lang])
    reqs = "".join(f'<li><span class="n">{i+1}</span><span>{r}</span></li>' for i,r in enumerate(p["requirements"][lang]))
    poi = "".join(f'<div class="row"><b>{n}</b><span>{d}</span></div>' for n,d in p["poi"][lang])
    similar = [x for x in LIVE if x["id"] != p["id"]][:3]
    sim_cards = "".join(card(x, lang, "index") for x in similar)
    sim_section = (f'<section class="section"><div class="section-head"><h2 style="font-size:24px">{t["similar"]}</h2></div>'
                   f'<div class="similar" style="padding-bottom:80px">{sim_cards}</div></section>') if similar else '<div style="height:60px"></div>'
    price_main = (f'<div class="detail-price">{money_mxn(p["priceMXN"])} <span class="per">{t["per"]}</span></div>' if lang=="es"
                  else f'<div class="detail-price">{money_usd(p["priceMXN"])} <span class="per">{t["per"]}</span>'
                       f'<span class="sub">{money_mxn(p["priceMXN"])} {t["per"]}</span></div>')
    plist = "../../es/propiedades/" if lang=="es" else "../../en/properties/"
    contact = f'''<div class="contact-card detail-contact">
      <form data-contact data-email="{B["email"]}" data-subject="{p["title"][lang]} — {p["id"]}">
        <div class="field"><label>{t["form_name"]}</label><input name="name" required></div>
        <div class="field"><label>{t["form_email"]}</label><input type="email" name="email" required></div>
        <div class="field"><label>{t["form_phone"]}</label><input name="phone"></div>
        <div class="field"><label>{t["form_msg"]}</label><textarea name="message">{p["title"][lang]} ({p["id"]}) — </textarea></div>
        <button class="btn btn-cta btn-block" type="submit">{t["form_send"]}</button>
      </form><div class="or">{t["or"]}</div>
      <div class="contact-alt"><a class="btn btn-wa btn-block" href="{wa_link()}">{WA}{t["wa_btn"]}</a>
        <a class="btn btn-outline btn-block" href="mailto:{B["email"]}">{t["email_btn"]}</a></div>
      <div class="note">{t["reply_note"]}</div></div>'''
    body = f'''{topbar(lang,"detail",p)}
<main class="page"><div class="wrap">
  <a class="back-link" href="{plist}">← {t["back"]}</a>
  <div class="detail-grid">
    <div>
      <div class="gallery-lead"><img src="{lead}" alt="{p["title"][lang]}"></div>
      <div class="thumbs">{thumbs}</div>
    </div>
    <div>
      <div class="detail-head"><span class="pill">{t["hero_eyebrow"].split("·")[0].strip()}</span>
        <h1>{p["title"][lang]}</h1><div class="zone">{p["zone"]} · Cancún</div>
        {price_main}<div class="avail"><span class="dot"></span>{p["avail"][lang]}</div></div>
      <div class="specs-row">{specs_html}</div>
      {contact}
    </div>
  </div>

  <div class="detail-body" style="max-width:820px">
    <div class="block"><h2>{t["h_desc"]}</h2><p>{p["desc"][lang]}</p></div>
    <div class="block"><h2>{t["h_amen"]}</h2><ul class="amen">{amen}</ul></div>
    <div class="block"><h2>{t["h_contract"]}</h2><div class="kv">{contract}</div></div>
    <div class="block"><h2>{t["h_req"]}</h2><p style="color:var(--text-2);margin-bottom:12px">{t["req_intro"]}</p>
      <ul class="req-list">{reqs}</ul><div class="note">{t["req_note"]}</div></div>
    <div class="block"><h2>{t["h_loc"]}</h2>
      <div class="map"><div class="blob"></div><div class="lbl">{t["map_label"]}</div></div>
      <div class="poi">{poi}</div><div class="note">{t["loc_note"]}</div></div>
  </div>

  {sim_section}
</div></main>
{footer(lang,"detail")}
<div class="sticky-bar"><div class="p">{money_mxn(p["priceMXN"]) if lang=="es" else money_usd(p["priceMXN"])} <span class="per">{t["per"]}</span></div>
  <a class="btn btn-outline" href="#contacto">{t["sticky_write"]}</a><a class="btn btn-wa" href="{wa_link()}">{WA}{t["wa"]}</a></div>'''
    return page_shell(lang, f'{p["title"][lang]} — {B["name"]} {B["city"].title()}', body, "detail")

# ---------- WRITE ----------
def w(path, html):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(html)

for lang, seg in (("es","propiedades"), ("en","properties")):
    w(os.path.join(DIST, lang, "index.html"), build_home(lang))
    w(os.path.join(DIST, lang, seg, "index.html"), build_index(lang))
    for p in props:
        if p.get("placeholder"):  # placeholders only appear as cards, no detail page except AUR-001
            continue
        w(os.path.join(DIST, lang, seg, f'{p["slug"][lang]}.html'), build_detail(p, lang))

# root redirect to Spanish (default)
w(os.path.join(DIST, "index.html"),
  '<!doctype html><meta charset="utf-8"><title>Aura Homes Cancún</title>'
  '<meta http-equiv="refresh" content="0; url=./es/">'
  '<link rel="alternate" hreflang="es" href="./es/"><link rel="alternate" hreflang="en" href="./en/">'
  '<a href="./es/">Aura Homes Cancún</a>')

print("Build complete.")
for r,_,fs in os.walk(DIST):
    for f in fs:
        if f.endswith(".html"):
            print(" ", os.path.relpath(os.path.join(r,f), DIST))

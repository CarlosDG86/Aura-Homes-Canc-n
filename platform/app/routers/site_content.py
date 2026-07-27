"""Real Properties CRUD for the public showcase site — Admin role only.

Unlike routers/admin.py (which reads/writes the SQLite `properties` table,
scoped for future 2b/2c owner-account work and currently empty/unrelated to
the live site), this router edits the ACTUAL site content:

  - ../data/properties.json (repo root, one level up from platform/) is the
    single source of truth for every property shown on the public site.
  - Uploaded photos are written under ../dist/assets/img/<id-lower>/.
  - Every create/edit/delete re-runs ../build.py so dist/ regenerates
    immediately.

The SQLite Property model/table is intentionally left untouched by this
file — it is not read or written here.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import RoleEnum, User
from .pages import _current_user_or_none, _home_for

router = APIRouter(tags=["site-content"], include_in_schema=False)

# --- Paths -------------------------------------------------------------

_THIS_FILE = os.path.abspath(__file__)
ROUTERS_DIR = os.path.dirname(_THIS_FILE)
APP_DIR = os.path.dirname(ROUTERS_DIR)
PLATFORM_DIR = os.path.dirname(APP_DIR)
REPO_ROOT = os.path.dirname(PLATFORM_DIR)

DATA_PATH = os.path.join(REPO_ROOT, "data", "properties.json")
DIST_IMG_DIR = os.path.join(REPO_ROOT, "dist", "assets", "img")
BUILD_SCRIPT = os.path.join(REPO_ROOT, "build.py")

templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))

# --- Constants / validation ---------------------------------------------

ID_RE = re.compile(r"^[A-Za-z0-9-]+$")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".svg"}
ALLOWED_STATUSES = ("available", "rented")


# --- Auth helper (mirrors pages.py's redirect-based gating) -------------


def _admin_or_redirect(request: Request, db: Session) -> Tuple[Optional[User], Optional[RedirectResponse]]:
    user = _current_user_or_none(request, db)
    if not user:
        return None, RedirectResponse(url="/login", status_code=302)
    if user.role != RoleEnum.admin:
        return None, RedirectResponse(url=_home_for(user), status_code=302)
    return user, None


# --- data/properties.json read/write ------------------------------------


def _load_properties() -> List[dict]:
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_properties_atomic(props: List[dict]) -> None:
    """Write to a temp file in the same directory, then atomically replace
    the original — avoids corrupting properties.json if the process dies
    mid-write."""
    dir_ = os.path.dirname(DATA_PATH)
    fd, tmp_path = tempfile.mkstemp(dir=dir_, prefix=".properties-", suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(props, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_path, DATA_PATH)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def _run_build() -> subprocess.CompletedProcess:
    python = sys.executable or "python"
    return subprocess.run(
        [python, BUILD_SCRIPT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def _write_and_build(new_props: List[dict]) -> Tuple[bool, Optional[str]]:
    """Write properties.json then run build.py. If the build fails, restore
    the previous properties.json content so the source of truth never sits
    in a state that breaks the static-site generator, and return the build
    output so the caller can show it to the CEO."""
    original_bytes = None
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "rb") as f:
            original_bytes = f.read()

    _save_properties_atomic(new_props)
    result = _run_build()

    if result.returncode != 0:
        if original_bytes is not None:
            dir_ = os.path.dirname(DATA_PATH)
            fd, tmp_path = tempfile.mkstemp(dir=dir_, prefix=".properties-", suffix=".json.tmp")
            with os.fdopen(fd, "wb") as f:
                f.write(original_bytes)
            os.replace(tmp_path, DATA_PATH)
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        return False, output.strip()

    return True, None


# --- form <-> data helpers ------------------------------------------------


def _lines_to_text(items: List[str]) -> str:
    return "\n".join(items or [])


def _pairs_to_text(pairs: List[List[str]]) -> str:
    return "\n".join(f"{a} | {b}" for a, b in (pairs or []))


def _parse_lines(text: str) -> List[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def _parse_pairs(text: str, field_label: str, errors: List[str]) -> List[List[str]]:
    pairs: List[List[str]] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "|" not in line:
            errors.append(f"{field_label}: cada línea debe tener el formato 'Etiqueta | Valor' — línea inválida: '{line}'")
            continue
        label, _, value = line.partition("|")
        label, value = label.strip(), value.strip()
        if not label or not value:
            errors.append(f"{field_label}: cada línea debe tener el formato 'Etiqueta | Valor' — línea inválida: '{line}'")
            continue
        pairs.append([label, value])
    return pairs


def _parse_number(text: str, field_label: str, errors: List[str]):
    text = (text or "").strip()
    if not text:
        errors.append(f"{field_label} es obligatorio.")
        return None
    try:
        value = float(text)
    except ValueError:
        errors.append(f"{field_label} debe ser un número.")
        return None
    if value.is_integer():
        return int(value)
    return value


def _require_bilingual(es_value: str, en_value: str, field_label: str, errors: List[str]) -> None:
    if not (es_value or "").strip():
        errors.append(f"{field_label} (ES) es obligatorio.")
    if not (en_value or "").strip():
        errors.append(f"{field_label} (EN) es obligatorio.")


def _require_bilingual_list(es_list: list, en_list: list, field_label: str, errors: List[str]) -> None:
    if not es_list:
        errors.append(f"{field_label} (ES): agrega al menos un elemento.")
    if not en_list:
        errors.append(f"{field_label} (EN): agrega al menos un elemento.")


def _blank_values() -> Dict[str, object]:
    return {
        "id": "", "slug_es": "", "slug_en": "", "status": "available", "featured": False,
        "priceMXN": "", "zone": "", "beds": "", "baths": "", "area": "",
        "furnished": False, "parking": "", "pets": False,
        "mapLat": "", "mapLng": "",
        "title_es": "", "title_en": "", "avail_es": "", "avail_en": "",
        "desc_es": "", "desc_en": "",
        "amenities_es": "", "amenities_en": "",
        "contract_es": "", "contract_en": "",
        "requirements_es": "", "requirements_en": "",
        "poi_es": "", "poi_en": "",
    }


def _values_from_property(p: dict) -> Dict[str, object]:
    mc = p.get("mapCenter", {}) or {}
    return {
        "id": p.get("id", ""),
        "slug_es": (p.get("slug") or {}).get("es", ""),
        "slug_en": (p.get("slug") or {}).get("en", ""),
        "status": p.get("status", "available"),
        "featured": bool(p.get("featured")),
        "priceMXN": p.get("priceMXN", ""),
        "zone": p.get("zone", ""),
        "beds": p.get("beds", ""),
        "baths": p.get("baths", ""),
        "area": p.get("area", ""),
        "furnished": bool(p.get("furnished")),
        "parking": p.get("parking", ""),
        "pets": bool(p.get("pets")),
        "mapLat": mc.get("lat", ""),
        "mapLng": mc.get("lng", ""),
        "title_es": (p.get("title") or {}).get("es", ""),
        "title_en": (p.get("title") or {}).get("en", ""),
        "avail_es": (p.get("avail") or {}).get("es", ""),
        "avail_en": (p.get("avail") or {}).get("en", ""),
        "desc_es": (p.get("desc") or {}).get("es", ""),
        "desc_en": (p.get("desc") or {}).get("en", ""),
        "amenities_es": _lines_to_text((p.get("amenities") or {}).get("es", [])),
        "amenities_en": _lines_to_text((p.get("amenities") or {}).get("en", [])),
        "contract_es": _pairs_to_text((p.get("contract") or {}).get("es", [])),
        "contract_en": _pairs_to_text((p.get("contract") or {}).get("en", [])),
        "requirements_es": _lines_to_text((p.get("requirements") or {}).get("es", [])),
        "requirements_en": _lines_to_text((p.get("requirements") or {}).get("en", [])),
        "poi_es": _pairs_to_text((p.get("poi") or {}).get("es", [])),
        "poi_en": _pairs_to_text((p.get("poi") or {}).get("en", [])),
    }


# --- image upload safety -------------------------------------------------


def _img_dir_for(prop_id: str) -> str:
    return os.path.join(DIST_IMG_DIR, prop_id.lower())


def _validate_upload_filename(filename: str) -> str:
    """Reject path-traversal-shaped names outright (never silently
    sanitize a name that tries to escape its directory); otherwise sanitize
    the basename and enforce an image-only extension allowlist."""
    if not filename or not filename.strip():
        raise ValueError("Uno de los archivos no tiene nombre.")
    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError(f"Nombre de archivo no permitido: '{filename}'")
    base = os.path.basename(filename)
    name, ext = os.path.splitext(base)
    ext = ext.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Tipo de archivo no permitido: '{filename}' (solo se aceptan .jpg, .jpeg, .png, .webp, .svg)"
        )
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-") or "img"
    return f"{safe_name}{ext}"


def _unique_name(name: str, taken: set) -> str:
    if name not in taken:
        return name
    stem, ext = os.path.splitext(name)
    for _ in range(1000):
        candidate = f"{stem}-{uuid.uuid4().hex[:6]}{ext}"
        if candidate not in taken:
            return candidate
    raise RuntimeError("No se pudo generar un nombre de archivo único.")


# --- routes: list ----------------------------------------------------------


@router.get("/admin/properties", response_class=HTMLResponse)
def list_properties_page(request: Request, db: Session = Depends(get_db)):
    user, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect
    properties = _load_properties()
    return templates.TemplateResponse(
        request=request,
        name="admin_properties_list.html",
        context={"user": user, "properties": properties, "build_error": None},
    )


# --- routes: new -------------------------------------------------------


@router.get("/admin/properties/new", response_class=HTMLResponse)
def new_property_page(request: Request, db: Session = Depends(get_db)):
    user, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        request=request,
        name="admin_property_form.html",
        context={
            "user": user, "mode": "new", "errors": [], "build_error": None,
            "values": _blank_values(), "existing_gallery": [], "removed_set": set(), "prop_id": "",
        },
    )


@router.post("/admin/properties/new", response_class=HTMLResponse)
async def create_property_submit(
    request: Request,
    db: Session = Depends(get_db),
    id: str = Form(...),
    slug_es: str = Form(""),
    slug_en: str = Form(""),
    status: str = Form("available"),
    featured: Optional[str] = Form(None),
    priceMXN: str = Form(""),
    zone: str = Form(""),
    beds: str = Form(""),
    baths: str = Form(""),
    area: str = Form(""),
    furnished: Optional[str] = Form(None),
    parking: str = Form(""),
    pets: Optional[str] = Form(None),
    mapLat: str = Form(""),
    mapLng: str = Form(""),
    title_es: str = Form(""),
    title_en: str = Form(""),
    avail_es: str = Form(""),
    avail_en: str = Form(""),
    desc_es: str = Form(""),
    desc_en: str = Form(""),
    amenities_es: str = Form(""),
    amenities_en: str = Form(""),
    contract_es: str = Form(""),
    contract_en: str = Form(""),
    requirements_es: str = Form(""),
    requirements_en: str = Form(""),
    poi_es: str = Form(""),
    poi_en: str = Form(""),
    images: List[UploadFile] = File(default=[]),
):
    user, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect

    values = {
        "id": id, "slug_es": slug_es, "slug_en": slug_en, "status": status,
        "featured": bool(featured), "priceMXN": priceMXN, "zone": zone,
        "beds": beds, "baths": baths, "area": area,
        "furnished": bool(furnished), "parking": parking, "pets": bool(pets),
        "mapLat": mapLat, "mapLng": mapLng,
        "title_es": title_es, "title_en": title_en,
        "avail_es": avail_es, "avail_en": avail_en,
        "desc_es": desc_es, "desc_en": desc_en,
        "amenities_es": amenities_es, "amenities_en": amenities_en,
        "contract_es": contract_es, "contract_en": contract_en,
        "requirements_es": requirements_es, "requirements_en": requirements_en,
        "poi_es": poi_es, "poi_en": poi_en,
    }

    errors: List[str] = []

    id_clean = (id or "").strip()
    props = _load_properties()
    if not ID_RE.match(id_clean or ""):
        errors.append(
            "El ID solo puede contener letras, números y guiones (sin puntos, espacios ni diagonales) — "
            f"valor recibido: '{id_clean}'"
        )
    elif any(p["id"] == id_clean for p in props):
        errors.append(f"Ya existe una propiedad con el ID '{id_clean}'.")

    if status not in ALLOWED_STATUSES:
        errors.append("Estatus inválido.")

    _require_bilingual(slug_es, slug_en, "Slug", errors)
    _require_bilingual(title_es, title_en, "Título", errors)
    _require_bilingual(avail_es, avail_en, "Disponibilidad", errors)
    _require_bilingual(desc_es, desc_en, "Descripción", errors)

    if not (zone or "").strip():
        errors.append("Zona es obligatoria.")

    price_val = _parse_number(priceMXN, "Precio mensual (MXN)", errors)
    beds_val = _parse_number(beds, "Recámaras", errors)
    baths_val = _parse_number(baths, "Baños", errors)
    area_val = _parse_number(area, "Área (m²)", errors)
    parking_val = _parse_number(parking, "Estacionamiento", errors)
    lat_val = _parse_number(mapLat, "Latitud", errors)
    lng_val = _parse_number(mapLng, "Longitud", errors)

    amenities_es_list = _parse_lines(amenities_es)
    amenities_en_list = _parse_lines(amenities_en)
    _require_bilingual_list(amenities_es_list, amenities_en_list, "Amenidades", errors)

    requirements_es_list = _parse_lines(requirements_es)
    requirements_en_list = _parse_lines(requirements_en)
    _require_bilingual_list(requirements_es_list, requirements_en_list, "Requisitos", errors)

    contract_es_pairs = _parse_pairs(contract_es, "Contrato (ES)", errors)
    contract_en_pairs = _parse_pairs(contract_en, "Contrato (EN)", errors)
    _require_bilingual_list(contract_es_pairs, contract_en_pairs, "Contrato", errors)

    poi_es_pairs = _parse_pairs(poi_es, "Puntos de interés (ES)", errors)
    poi_en_pairs = _parse_pairs(poi_en, "Puntos de interés (EN)", errors)
    _require_bilingual_list(poi_es_pairs, poi_en_pairs, "Puntos de interés", errors)

    # Validate uploaded filenames without writing anything yet.
    safe_filenames: List[str] = []
    taken: set = set()
    for img in images:
        if not img.filename:
            continue
        try:
            safe = _validate_upload_filename(img.filename)
            safe = _unique_name(safe, taken)
            taken.add(safe)
            safe_filenames.append(safe)
        except ValueError as e:
            errors.append(str(e))

    if not safe_filenames:
        errors.append("Agrega al menos una fotografía.")

    if errors:
        return templates.TemplateResponse(
            request=request,
            name="admin_property_form.html",
            context={
                "user": user, "mode": "new", "errors": errors, "build_error": None,
                "values": values, "existing_gallery": [], "removed_set": set(), "prop_id": "",
            },
            status_code=400,
        )

    # Everything validated — now write the uploaded files to disk.
    img_dir = _img_dir_for(id_clean)
    os.makedirs(img_dir, exist_ok=True)
    for img, safe_name in zip([i for i in images if i.filename], safe_filenames):
        content = await img.read()
        with open(os.path.join(img_dir, safe_name), "wb") as f:
            f.write(content)

    new_prop = {
        "id": id_clean,
        "slug": {"es": slug_es.strip(), "en": slug_en.strip()},
        "status": status,
        "featured": bool(featured),
        "priceMXN": price_val,
        "zone": zone.strip(),
        "beds": beds_val, "baths": baths_val, "area": area_val,
        "furnished": bool(furnished), "parking": parking_val, "pets": bool(pets),
        "mapCenter": {"lat": lat_val, "lng": lng_val},
        "title": {"es": title_es.strip(), "en": title_en.strip()},
        "avail": {"es": avail_es.strip(), "en": avail_en.strip()},
        "hero": safe_filenames[0],
        "gallery": safe_filenames,
        "desc": {"es": desc_es.strip(), "en": desc_en.strip()},
        "amenities": {"es": amenities_es_list, "en": amenities_en_list},
        "contract": {"es": contract_es_pairs, "en": contract_en_pairs},
        "requirements": {"es": requirements_es_list, "en": requirements_en_list},
        "poi": {"es": poi_es_pairs, "en": poi_en_pairs},
    }
    props.append(new_prop)

    ok, build_error = _write_and_build(props)
    if not ok:
        # this property never actually saved — don't leave its freshly-uploaded
        # photos orphaned on disk (they'd otherwise stay world-readable via /site-images)
        shutil.rmtree(img_dir, ignore_errors=True)
        errors.append("La compilación del sitio falló. La propiedad NO se guardó (los cambios se revirtieron).")
        return templates.TemplateResponse(
            request=request,
            name="admin_property_form.html",
            context={
                "user": user, "mode": "new", "errors": errors, "build_error": build_error,
                "values": values, "existing_gallery": [], "removed_set": set(), "prop_id": "",
            },
            status_code=500,
        )

    return RedirectResponse(url="/admin/properties", status_code=302)


# --- routes: edit ----------------------------------------------------------


@router.get("/admin/properties/{id}/edit", response_class=HTMLResponse)
def edit_property_page(id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect
    props = _load_properties()
    prop = next((p for p in props if p["id"] == id), None)
    if not prop:
        return RedirectResponse(url="/admin/properties", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="admin_property_form.html",
        context={
            "user": user, "mode": "edit", "errors": [], "build_error": None,
            "values": _values_from_property(prop),
            "existing_gallery": prop.get("gallery", []),
            "removed_set": set(),
            "prop_id": id,
        },
    )


@router.post("/admin/properties/{id}/edit", response_class=HTMLResponse)
async def edit_property_submit(
    id: str,
    request: Request,
    db: Session = Depends(get_db),
    slug_es: str = Form(""),
    slug_en: str = Form(""),
    status: str = Form("available"),
    featured: Optional[str] = Form(None),
    priceMXN: str = Form(""),
    zone: str = Form(""),
    beds: str = Form(""),
    baths: str = Form(""),
    area: str = Form(""),
    furnished: Optional[str] = Form(None),
    parking: str = Form(""),
    pets: Optional[str] = Form(None),
    mapLat: str = Form(""),
    mapLng: str = Form(""),
    title_es: str = Form(""),
    title_en: str = Form(""),
    avail_es: str = Form(""),
    avail_en: str = Form(""),
    desc_es: str = Form(""),
    desc_en: str = Form(""),
    amenities_es: str = Form(""),
    amenities_en: str = Form(""),
    contract_es: str = Form(""),
    contract_en: str = Form(""),
    requirements_es: str = Form(""),
    requirements_en: str = Form(""),
    poi_es: str = Form(""),
    poi_en: str = Form(""),
    remove_images: List[str] = Form(default=[]),
    images: List[UploadFile] = File(default=[]),
):
    user, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect

    props = _load_properties()
    existing = next((p for p in props if p["id"] == id), None)
    if not existing:
        return RedirectResponse(url="/admin/properties", status_code=302)

    values = {
        "id": id, "slug_es": slug_es, "slug_en": slug_en, "status": status,
        "featured": bool(featured), "priceMXN": priceMXN, "zone": zone,
        "beds": beds, "baths": baths, "area": area,
        "furnished": bool(furnished), "parking": parking, "pets": bool(pets),
        "mapLat": mapLat, "mapLng": mapLng,
        "title_es": title_es, "title_en": title_en,
        "avail_es": avail_es, "avail_en": avail_en,
        "desc_es": desc_es, "desc_en": desc_en,
        "amenities_es": amenities_es, "amenities_en": amenities_en,
        "contract_es": contract_es, "contract_en": contract_en,
        "requirements_es": requirements_es, "requirements_en": requirements_en,
        "poi_es": poi_es, "poi_en": poi_en,
    }

    errors: List[str] = []

    if status not in ALLOWED_STATUSES:
        errors.append("Estatus inválido.")

    _require_bilingual(slug_es, slug_en, "Slug", errors)
    _require_bilingual(title_es, title_en, "Título", errors)
    _require_bilingual(avail_es, avail_en, "Disponibilidad", errors)
    _require_bilingual(desc_es, desc_en, "Descripción", errors)

    if not (zone or "").strip():
        errors.append("Zona es obligatoria.")

    price_val = _parse_number(priceMXN, "Precio mensual (MXN)", errors)
    beds_val = _parse_number(beds, "Recámaras", errors)
    baths_val = _parse_number(baths, "Baños", errors)
    area_val = _parse_number(area, "Área (m²)", errors)
    parking_val = _parse_number(parking, "Estacionamiento", errors)
    lat_val = _parse_number(mapLat, "Latitud", errors)
    lng_val = _parse_number(mapLng, "Longitud", errors)

    amenities_es_list = _parse_lines(amenities_es)
    amenities_en_list = _parse_lines(amenities_en)
    _require_bilingual_list(amenities_es_list, amenities_en_list, "Amenidades", errors)

    requirements_es_list = _parse_lines(requirements_es)
    requirements_en_list = _parse_lines(requirements_en)
    _require_bilingual_list(requirements_es_list, requirements_en_list, "Requisitos", errors)

    contract_es_pairs = _parse_pairs(contract_es, "Contrato (ES)", errors)
    contract_en_pairs = _parse_pairs(contract_en, "Contrato (EN)", errors)
    _require_bilingual_list(contract_es_pairs, contract_en_pairs, "Contrato", errors)

    poi_es_pairs = _parse_pairs(poi_es, "Puntos de interés (ES)", errors)
    poi_en_pairs = _parse_pairs(poi_en, "Puntos de interés (EN)", errors)
    _require_bilingual_list(poi_es_pairs, poi_en_pairs, "Puntos de interés", errors)

    current_gallery = existing.get("gallery", [])
    removed_set = set(remove_images)
    kept = [g for g in current_gallery if g not in removed_set]

    safe_filenames: List[str] = []
    taken = set(kept)
    for img in images:
        if not img.filename:
            continue
        try:
            safe = _validate_upload_filename(img.filename)
            safe = _unique_name(safe, taken)
            taken.add(safe)
            safe_filenames.append(safe)
        except ValueError as e:
            errors.append(str(e))

    final_gallery = kept + safe_filenames
    if not final_gallery:
        errors.append("Debe quedar al menos una fotografía en la galería.")

    if errors:
        return templates.TemplateResponse(
            request=request,
            name="admin_property_form.html",
            context={
                "user": user, "mode": "edit", "errors": errors, "build_error": None,
                "values": values, "existing_gallery": current_gallery,
                "removed_set": removed_set, "prop_id": id,
            },
            status_code=400,
        )

    img_dir = _img_dir_for(id)
    os.makedirs(img_dir, exist_ok=True)
    for img, safe_name in zip([i for i in images if i.filename], safe_filenames):
        content = await img.read()
        with open(os.path.join(img_dir, safe_name), "wb") as f:
            f.write(content)

    updated_prop = {
        "id": id,
        "slug": {"es": slug_es.strip(), "en": slug_en.strip()},
        "status": status,
        "featured": bool(featured),
        "priceMXN": price_val,
        "zone": zone.strip(),
        "beds": beds_val, "baths": baths_val, "area": area_val,
        "furnished": bool(furnished), "parking": parking_val, "pets": bool(pets),
        "mapCenter": {"lat": lat_val, "lng": lng_val},
        "title": {"es": title_es.strip(), "en": title_en.strip()},
        "avail": {"es": avail_es.strip(), "en": avail_en.strip()},
        "hero": final_gallery[0],
        "gallery": final_gallery,
        "desc": {"es": desc_es.strip(), "en": desc_en.strip()},
        "amenities": {"es": amenities_es_list, "en": amenities_en_list},
        "contract": {"es": contract_es_pairs, "en": contract_en_pairs},
        "requirements": {"es": requirements_es_list, "en": requirements_en_list},
        "poi": {"es": poi_es_pairs, "en": poi_en_pairs},
    }

    new_props = [updated_prop if p["id"] == id else p for p in props]
    ok, build_error = _write_and_build(new_props)
    if not ok:
        # only remove files uploaded in THIS failed submission — kept/pre-existing
        # gallery photos still belong to the property, which still exists
        for safe_name in safe_filenames:
            try:
                os.remove(os.path.join(img_dir, safe_name))
            except OSError:
                pass
        errors.append("La compilación del sitio falló. Los cambios NO se guardaron (se revirtieron).")
        return templates.TemplateResponse(
            request=request,
            name="admin_property_form.html",
            context={
                "user": user, "mode": "edit", "errors": errors, "build_error": build_error,
                "values": values, "existing_gallery": current_gallery,
                "removed_set": removed_set, "prop_id": id,
            },
            status_code=500,
        )

    return RedirectResponse(url="/admin/properties", status_code=302)


# --- routes: delete ----------------------------------------------------


@router.post("/admin/properties/{id}/delete", response_class=HTMLResponse)
def delete_property_submit(id: str, request: Request, db: Session = Depends(get_db)):
    user, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect

    props = _load_properties()
    filtered = [p for p in props if p["id"] != id]
    if len(filtered) == len(props):
        return RedirectResponse(url="/admin/properties", status_code=302)

    ok, build_error = _write_and_build(filtered)
    if not ok:
        current = _load_properties()  # reverted by _write_and_build back to the original
        return templates.TemplateResponse(
            request=request,
            name="admin_properties_list.html",
            context={
                "user": user, "properties": current,
                "build_error": f"No se pudo eliminar '{id}': la compilación del sitio falló. "
                                f"El cambio NO se aplicó (se revirtió).\n\n{build_error}",
            },
            status_code=500,
        )

    return RedirectResponse(url="/admin/properties", status_code=302)

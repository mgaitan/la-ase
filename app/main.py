from __future__ import annotations

from pathlib import Path
import os
import re
import unicodedata

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markdown import markdown
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload
from starlette.middleware.sessions import SessionMiddleware

from app.db import Base, SessionLocal, engine, get_db
from app.models import Category, Comment, Entry, MenuItem, Page, Tag, User
from app.settings import load_env_file, require_env
from app.seed import ensure_seed_data
from app.security import hash_password, verify_password
from app.storage import (
    StorageNotConfiguredError,
    StorageUploadError,
    fetch_object,
    is_r2_configured,
    upload_image,
)


APP_DIR = Path(__file__).resolve().parent
BASE_DIR = APP_DIR.parent
load_env_file()
STATIC_DIR = APP_DIR / "static"


def compute_asset_version() -> str:
    latest_mtime = max(
        path.stat().st_mtime
        for path in STATIC_DIR.rglob("*")
        if path.is_file()
    )
    return str(int(latest_mtime))


ASSET_VERSION = compute_asset_version()

app = FastAPI(title="Asociacion Secreta de Escritores")
app.add_middleware(
    SessionMiddleware,
    secret_key=require_env("SESSION_SECRET"),
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.lower()).strip("-")
    return cleaned or "sin-titulo"


def render_markdown(value: str) -> str:
    return markdown(value, extensions=["extra", "sane_lists"])


def unique_slug(db: Session, model: type[Entry] | type[Page] | type[Category] | type[Tag], base_value: str, current_id: int | None = None) -> str:
    base_slug = slugify(base_value)
    candidate = base_slug
    counter = 2
    while True:
        stmt = select(model).where(model.slug == candidate)
        item = db.scalar(stmt)
        if item is None or getattr(item, "id", None) == current_id:
            return candidate
        candidate = f"{base_slug}-{counter}"
        counter += 1


def build_context(request: Request, db: Session, **extra: object) -> dict[str, object]:
    menu_items = db.scalars(select(MenuItem).order_by(MenuItem.position, MenuItem.id)).all()
    popular_tags = db.scalars(select(Tag).order_by(Tag.name)).all()
    current_user = get_current_user(request, db)
    context = {
        "request": request,
        "menu_items": menu_items,
        "popular_tags": popular_tags,
        "site_name": "A.S.E.",
        "current_user": current_user,
        "asset_version": ASSET_VERSION,
    }
    context.update(extra)
    return context


def get_current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)


def require_admin(request: Request, db: Session) -> User:
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/login"})
    return user


def require_user(request: Request, db: Session) -> User:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/login"})
    return user


def get_author_users(db: Session) -> list[User]:
    return db.scalars(select(User).where(User.is_admin.is_(False)).order_by(User.display_name)).all()


def can_manage_entry(user: User, entry: Entry) -> bool:
    return user.is_admin or entry.author_name == user.display_name


def assign_tags(db: Session, tag_names: str) -> list[Tag]:
    tags: list[Tag] = []
    seen: set[str] = set()
    for raw_name in tag_names.split(","):
        name = raw_name.strip()
        if not name:
            continue
        normalized = name.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        slug = slugify(name)
        tag = db.scalar(select(Tag).where(func.lower(Tag.slug) == slug.lower()))
        if not tag:
            tag = Tag(name=name.title(), slug=unique_slug(db, Tag, name))
            db.add(tag)
            db.flush()
        tags.append(tag)
    return tags


def get_or_create_category(db: Session, category_name: str) -> Category | None:
    category_name = category_name.strip()
    if not category_name:
        return None
    slug = slugify(category_name)
    category = db.scalar(select(Category).where(func.lower(Category.slug) == slug.lower()))
    if category:
        return category
    category = Category(name=category_name.title(), slug=unique_slug(db, Category, category_name))
    db.add(category)
    db.flush()
    return category


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        ensure_seed_data(db)


@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    featured_entries = db.scalars(
        select(Entry)
        .options(joinedload(Entry.category), selectinload(Entry.tags))
        .where(Entry.is_published.is_(True), Entry.featured.is_(True))
        .order_by(Entry.created_at.desc())
        .limit(4)
    ).all()
    latest_blog = db.scalars(
        select(Entry)
        .options(joinedload(Entry.category), selectinload(Entry.tags))
        .where(Entry.is_published.is_(True), Entry.kind == "blog")
        .order_by(Entry.created_at.desc())
        .limit(3)
    ).all()
    latest_publications = db.scalars(
        select(Entry)
        .options(joinedload(Entry.category), selectinload(Entry.tags))
        .where(Entry.is_published.is_(True), Entry.kind == "publication")
        .order_by(Entry.created_at.desc())
        .limit(6)
    ).all()
    story_page = db.scalar(select(Page).where(Page.slug == "nuestra-historia"))
    return templates.TemplateResponse(
        request,
        "home.html",
        build_context(
            request,
            db,
            featured_entries=featured_entries,
            latest_blog=latest_blog,
            latest_publications=latest_publications,
            story_page=story_page,
        ),
    )


@app.get("/blog")
def blog_listing(request: Request, db: Session = Depends(get_db)):
    entries = db.scalars(
        select(Entry)
        .options(joinedload(Entry.category), selectinload(Entry.tags))
        .where(Entry.is_published.is_(True), Entry.kind == "blog")
        .order_by(Entry.created_at.desc())
    ).all()
    return templates.TemplateResponse(
        request,
        "listing.html",
        build_context(
            request,
            db,
            title="Blog",
            subtitle="Notas, novedades y el detrás de escena de la Asociación Secreta de Escritores.",
            entries=entries,
            current_filter=None,
            section="blog",
        ),
    )


@app.get("/publicaciones")
def publications_listing(request: Request, category: str | None = None, db: Session = Depends(get_db)):
    stmt = (
        select(Entry)
        .options(joinedload(Entry.category), selectinload(Entry.tags))
        .where(Entry.is_published.is_(True), Entry.kind == "publication")
        .order_by(Entry.created_at.desc())
    )
    current_filter = None
    if category:
        stmt = stmt.join(Entry.category).where(Category.slug == category)
        current_filter = db.scalar(select(Category).where(Category.slug == category))
    entries = db.scalars(stmt).all()
    categories = db.scalars(select(Category).order_by(Category.name)).all()
    return templates.TemplateResponse(
        request,
        "listing.html",
        build_context(
            request,
            db,
            title="Publicaciones",
            subtitle="Cuentos, poemas y otros textos creados por A.S.E.",
            entries=entries,
            categories=categories,
            current_filter=current_filter,
            section="publicaciones",
        ),
    )


@app.get("/etiquetas/{slug}")
def tag_listing(request: Request, slug: str, db: Session = Depends(get_db)):
    tag = db.scalar(
        select(Tag)
        .options(selectinload(Tag.entries).selectinload(Entry.tags), selectinload(Tag.entries).joinedload(Entry.category))
        .where(Tag.slug == slug)
    )
    if not tag:
        raise HTTPException(status_code=404, detail="Etiqueta no encontrada")
    entries = [entry for entry in tag.entries if entry.is_published]
    entries.sort(key=lambda item: item.created_at, reverse=True)
    return templates.TemplateResponse(
        request,
        "listing.html",
        build_context(
            request,
            db,
            title=f"Etiqueta: {tag.name}",
            subtitle="Textos relacionados con esta etiqueta.",
            entries=entries,
            current_filter=tag,
            section="tags",
        ),
    )


@app.get("/blog/{slug}")
def blog_detail(request: Request, slug: str, db: Session = Depends(get_db)):
    entry = db.scalar(
        select(Entry)
        .options(joinedload(Entry.category), selectinload(Entry.tags), selectinload(Entry.comments))
        .where(Entry.slug == slug, Entry.kind == "blog", Entry.is_published.is_(True))
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")
    approved_comments = [comment for comment in entry.comments if comment.is_approved]
    return templates.TemplateResponse(
        request,
        "entry_detail.html",
        build_context(request, db, entry=entry, body_html=render_markdown(entry.content), comments=approved_comments),
    )


@app.post("/blog/{slug}/comentarios")
def submit_comment(
    slug: str,
    author_name: str = Form(...),
    content: str = Form(...),
    db: Session = Depends(get_db),
):
    entry = db.scalar(select(Entry).where(Entry.slug == slug, Entry.kind == "blog", Entry.is_published.is_(True)))
    if not entry:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")
    comment = Comment(author_name=author_name.strip(), content=content.strip(), entry=entry, is_approved=False)
    db.add(comment)
    db.commit()
    return RedirectResponse(url=f"/blog/{slug}?comentario=pendiente", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/publicaciones/{slug}")
def publication_detail(request: Request, slug: str, db: Session = Depends(get_db)):
    entry = db.scalar(
        select(Entry)
        .options(joinedload(Entry.category), selectinload(Entry.tags))
        .where(Entry.slug == slug, Entry.kind == "publication", Entry.is_published.is_(True))
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Publicacion no encontrada")
    return templates.TemplateResponse(
        request,
        "entry_detail.html",
        build_context(request, db, entry=entry, body_html=render_markdown(entry.content), comments=[]),
    )


@app.get("/paginas/{slug}")
def page_detail(request: Request, slug: str, db: Session = Depends(get_db)):
    page = db.scalar(select(Page).where(Page.slug == slug, Page.is_published.is_(True)))
    if not page:
        raise HTTPException(status_code=404, detail="Pagina no encontrada")
    return templates.TemplateResponse(
        request,
        "page.html",
        build_context(request, db, page=page, body_html=render_markdown(page.content)),
    )


@app.get("/media/{object_key:path}")
def media_object(object_key: str):
    if not is_r2_configured():
        raise HTTPException(status_code=503, detail="R2 no está configurado.")
    try:
        body, content_type = fetch_object(object_key)
    except StorageUploadError:
        raise HTTPException(status_code=404, detail="Imagen no encontrada") from None
    return StreamingResponse(
        body,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@app.get("/admin/login")
def admin_login(request: Request, db: Session = Depends(get_db)):
    if get_current_user(request, db):
        return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "admin_login.html", build_context(request, db, error=None))


@app.post("/admin/login")
def admin_login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.username == username.strip()))
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "admin_login.html",
            build_context(request, db, error="Usuario o contraseña incorrectos."),
            status_code=400,
        )
    request.session["user_id"] = user.id
    return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/admin/logout")
def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/admin")
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    entry_stmt = select(Entry).options(joinedload(Entry.category)).order_by(Entry.updated_at.desc())
    if not user.is_admin:
        entry_stmt = entry_stmt.where(Entry.author_name == user.display_name)
    entries = db.scalars(entry_stmt).all()
    pages = db.scalars(select(Page).order_by(Page.updated_at.desc())).all() if user.is_admin else []
    menu_items = db.scalars(select(MenuItem).order_by(MenuItem.position, MenuItem.id)).all() if user.is_admin else []
    pending_comments = (
        db.scalars(
            select(Comment)
            .options(joinedload(Comment.entry))
            .where(Comment.is_approved.is_(False))
            .order_by(Comment.created_at.desc())
        ).all()
        if user.is_admin
        else []
    )
    author_users = get_author_users(db)
    users = db.scalars(select(User).order_by(User.is_admin.desc(), User.display_name)).all() if user.is_admin else []
    return templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        build_context(
            request,
            db,
            user=user,
            entries=entries,
            pages=pages,
            menu_items=menu_items,
            pending_comments=pending_comments,
            author_users=author_users,
            users=users,
        ),
    )


@app.get("/admin/entries/new")
def admin_new_entry(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    categories = db.scalars(select(Category).order_by(Category.name)).all()
    author_users = get_author_users(db)
    return templates.TemplateResponse(
        request,
        "admin_entry_form.html",
        build_context(request, db, entry=None, categories=categories, author_users=author_users, user=user),
    )


@app.get("/admin/entries/{entry_id}/edit")
def admin_edit_entry(request: Request, entry_id: int, db: Session = Depends(get_db)):
    user = require_user(request, db)
    entry = db.scalar(select(Entry).options(selectinload(Entry.tags), joinedload(Entry.category)).where(Entry.id == entry_id))
    if not entry:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")
    if not can_manage_entry(user, entry):
        raise HTTPException(status_code=403, detail="No tenes permisos para editar esta entrada")
    categories = db.scalars(select(Category).order_by(Category.name)).all()
    author_users = get_author_users(db)
    return templates.TemplateResponse(
        request,
        "admin_entry_form.html",
        build_context(request, db, entry=entry, categories=categories, author_users=author_users, user=user),
    )


@app.post("/admin/entries/save")
def admin_save_entry(
    request: Request,
    entry_id: int | None = Form(None),
    title: str = Form(...),
    summary: str = Form(""),
    content: str = Form(...),
    kind: str = Form(...),
    author_name: str = Form(""),
    category_name: str = Form(""),
    tag_names: str = Form(""),
    is_published: bool = Form(False),
    featured: bool = Form(False),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    entry = db.get(Entry, entry_id) if entry_id else Entry()
    if entry_id and not entry:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")
    if entry.id and not can_manage_entry(user, entry):
        raise HTTPException(status_code=403, detail="No tenes permisos para editar esta entrada")
    db.add(entry)
    entry.title = title.strip()
    entry.slug = unique_slug(db, Entry, title, current_id=entry.id if entry.id else None)
    entry.summary = summary.strip()
    entry.content = content.strip()
    entry.kind = kind
    if user.is_admin:
        available_names = {author.display_name for author in get_author_users(db)}
        entry.author_name = author_name.strip() if author_name.strip() in available_names else "A.S.E."
    else:
        entry.author_name = user.display_name
    entry.is_published = is_published
    entry.featured = featured
    entry.category = get_or_create_category(db, category_name)
    entry.tags = assign_tags(db, tag_names)
    db.commit()
    return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/entries/{entry_id}/delete")
def admin_delete_entry(request: Request, entry_id: int, db: Session = Depends(get_db)):
    user = require_user(request, db)
    entry = db.get(Entry, entry_id)
    if entry and can_manage_entry(user, entry):
        db.delete(entry)
        db.commit()
    return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/admin/pages/new")
def admin_new_page(request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    return templates.TemplateResponse(request, "admin_page_form.html", build_context(request, db, page=None))


@app.get("/admin/pages/{page_id}/edit")
def admin_edit_page(request: Request, page_id: int, db: Session = Depends(get_db)):
    require_admin(request, db)
    page = db.get(Page, page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Pagina no encontrada")
    return templates.TemplateResponse(request, "admin_page_form.html", build_context(request, db, page=page))


@app.post("/admin/pages/save")
def admin_save_page(
    request: Request,
    page_id: int | None = Form(None),
    title: str = Form(...),
    excerpt: str = Form(""),
    content: str = Form(...),
    is_published: bool = Form(False),
    db: Session = Depends(get_db),
):
    require_admin(request, db)
    page = db.get(Page, page_id) if page_id else Page()
    if page_id and not page:
        raise HTTPException(status_code=404, detail="Pagina no encontrada")
    page.title = title.strip()
    page.slug = unique_slug(db, Page, title, current_id=page.id if page.id else None)
    page.excerpt = excerpt.strip()
    page.content = content.strip()
    page.is_published = is_published
    db.add(page)
    db.commit()
    return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/pages/{page_id}/delete")
def admin_delete_page(request: Request, page_id: int, db: Session = Depends(get_db)):
    require_admin(request, db)
    page = db.get(Page, page_id)
    if page:
        db.delete(page)
        db.commit()
    return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/admin/menu/new")
def admin_new_menu_item(request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    return templates.TemplateResponse(request, "admin_menu_form.html", build_context(request, db, menu_item=None))


@app.get("/admin/menu/{item_id}/edit")
def admin_edit_menu_item(request: Request, item_id: int, db: Session = Depends(get_db)):
    require_admin(request, db)
    menu_item = db.get(MenuItem, item_id)
    if not menu_item:
        raise HTTPException(status_code=404, detail="Item de menu no encontrado")
    return templates.TemplateResponse(request, "admin_menu_form.html", build_context(request, db, menu_item=menu_item))


@app.post("/admin/menu/save")
def admin_save_menu_item(
    request: Request,
    item_id: int | None = Form(None),
    label: str = Form(...),
    url: str = Form(...),
    position: int = Form(0),
    db: Session = Depends(get_db),
):
    require_admin(request, db)
    menu_item = db.get(MenuItem, item_id) if item_id else MenuItem()
    if item_id and not menu_item:
        raise HTTPException(status_code=404, detail="Item de menu no encontrado")
    menu_item.label = label.strip()
    menu_item.url = url.strip()
    menu_item.position = position
    db.add(menu_item)
    db.commit()
    return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/menu/{item_id}/delete")
def admin_delete_menu_item(request: Request, item_id: int, db: Session = Depends(get_db)):
    require_admin(request, db)
    menu_item = db.get(MenuItem, item_id)
    if menu_item:
        db.delete(menu_item)
        db.commit()
    return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/comments/{comment_id}/toggle")
def admin_toggle_comment(request: Request, comment_id: int, db: Session = Depends(get_db)):
    require_admin(request, db)
    comment = db.get(Comment, comment_id)
    if comment:
        comment.is_approved = not comment.is_approved
        db.add(comment)
        db.commit()
    return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/comments/{comment_id}/delete")
def admin_delete_comment(request: Request, comment_id: int, db: Session = Depends(get_db)):
    require_admin(request, db)
    comment = db.get(Comment, comment_id)
    if comment:
        db.delete(comment)
        db.commit()
    return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/markdown/preview", response_class=HTMLResponse)
def admin_markdown_preview(
    request: Request,
    content: str = Form(""),
    db: Session = Depends(get_db),
):
    require_user(request, db)
    return render_markdown(content)


@app.post("/admin/uploads/images")
async def admin_upload_image(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    require_user(request, db)
    if not is_r2_configured():
        return JSONResponse(
            {"error": "R2 todavía no está configurado en este entorno."},
            status_code=503,
        )
    content = await file.read()
    try:
        key = upload_image(
            content=content,
            content_type=file.content_type or "application/octet-stream",
            filename=file.filename,
        )
    except StorageUploadError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except StorageNotConfiguredError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)

    url = f"/media/{key}"
    alt_text = Path(file.filename or "imagen").stem.replace("-", " ").replace("_", " ").strip() or "imagen"
    return {
        "url": url,
        "markdown": f"![{alt_text}]({url})",
    }


@app.get("/admin/password")
def admin_password_form(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    return templates.TemplateResponse(
        request,
        "admin_password_form.html",
        build_context(request, db, user=user, target_user=user, error=None, success=None),
    )


@app.post("/admin/password")
def admin_password_submit(
    request: Request,
    current_password: str = Form(""),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    if not user.is_admin and not verify_password(current_password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "admin_password_form.html",
            build_context(request, db, user=user, target_user=user, error="La contraseña actual no coincide.", success=None),
            status_code=400,
        )
    if len(new_password.strip()) < 8:
        return templates.TemplateResponse(
            request,
            "admin_password_form.html",
            build_context(request, db, user=user, target_user=user, error="La nueva contraseña debe tener al menos 8 caracteres.", success=None),
            status_code=400,
        )
    if new_password != confirm_password:
        return templates.TemplateResponse(
            request,
            "admin_password_form.html",
            build_context(request, db, user=user, target_user=user, error="La confirmación no coincide.", success=None),
            status_code=400,
        )
    user.password_hash = hash_password(new_password.strip())
    db.add(user)
    db.commit()
    return templates.TemplateResponse(
        request,
        "admin_password_form.html",
        build_context(request, db, user=user, target_user=user, error=None, success="Contraseña actualizada."),
    )


@app.get("/admin/users/{user_id}/password")
def admin_user_password_form(request: Request, user_id: int, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    target_user = db.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return templates.TemplateResponse(
        request,
        "admin_password_form.html",
        build_context(request, db, user=user, target_user=target_user, error=None, success=None),
    )


@app.post("/admin/users/{user_id}/password")
def admin_user_password_submit(
    request: Request,
    user_id: int,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = require_admin(request, db)
    target_user = db.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if len(new_password.strip()) < 8:
        return templates.TemplateResponse(
            request,
            "admin_password_form.html",
            build_context(request, db, user=user, target_user=target_user, error="La nueva contraseña debe tener al menos 8 caracteres.", success=None),
            status_code=400,
        )
    if new_password != confirm_password:
        return templates.TemplateResponse(
            request,
            "admin_password_form.html",
            build_context(request, db, user=user, target_user=target_user, error="La confirmación no coincide.", success=None),
            status_code=400,
        )
    target_user.password_hash = hash_password(new_password.strip())
    db.add(target_user)
    db.commit()
    return templates.TemplateResponse(
        request,
        "admin_password_form.html",
        build_context(request, db, user=user, target_user=target_user, error=None, success="Contraseña actualizada."),
    )

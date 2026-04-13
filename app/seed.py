from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Entry, MenuItem, Page, Tag, User
from app.security import hash_password
from app.settings import require_env


def ensure_seed_data(db: Session) -> None:
    if db.scalar(select(User.id).limit(1)):
        return

    user = User(
        username=os.getenv("ASE_ADMIN_USERNAME", "admin"),
        display_name="Equipo A.S.E.",
        password_hash=hash_password(require_env("ASE_ADMIN_PASSWORD")),
        is_admin=True,
    )

    cuentos = Category(
        name="Cuentos", slug="cuentos", description="Historias inventadas por la A.S.E."
    )
    poemas = Category(
        name="Poemas",
        slug="poemas",
        description="Versos, canciones y juegos de palabras.",
    )
    otros = Category(
        name="Otros", slug="otros", description="Bitácoras, ideas y experimentos."
    )

    tags = [
        Tag(name="Infantil", slug="infantil"),
        Tag(name="Fantasia", slug="fantasia"),
        Tag(name="Aventura", slug="aventura"),
        Tag(name="Escuela", slug="escuela"),
        Tag(name="Amistad", slug="amistad"),
    ]

    historia = Page(
        title="Nuestra historia",
        slug="nuestra-historia",
        excerpt="Como nació la Asociación Secreta de Escritores.",
        content="""
La **Asociación Secreta de Escritores** nació en 5to grado B, en la Escuela Sarmiento de Villa Los Aromos.

Ema, Gael y Oliver descubrieron que compartían algo importante: les gustaba leer, escribir, inventar personajes y conversar sobre historias.

Entonces decidieron formar un grupo propio, con nombre misterioso y espíritu creativo: la **A.S.E.**

Desde ese día empezaron a guardar ideas, escribir cuentos, probar poemas y pensar nuevas publicaciones para compartir con sus familias, su escuela y cualquier lector curioso.
""".strip(),
        is_published=True,
    )

    bienvenida = Entry(
        title="Bienvenidos al escondite de la A.S.E.",
        slug="bienvenidos-al-escondite-de-la-ase",
        summary="La primera nota del blog donde presentamos el club y contamos qué queremos publicar.",
        content="""
Hola, somos **Ema, Gael y Oliver**.

Creamos este sitio para compartir cuentos, poemas, ideas y todo lo que vamos inventando.

Nos gusta escribir cosas misteriosas, divertidas, fantásticas y también historias de la escuela o del barrio.

Si querés volver, siempre va a haber algo nuevo para leer.
""".strip(),
        kind="blog",
        is_published=True,
        featured=True,
        author_name="Ema, Gael y Oliver",
        category=otros,
        tags=[tags[0], tags[3], tags[4]],
    )

    cuento = Entry(
        title="La biblioteca que susurraba secretos",
        slug="la-biblioteca-que-susurraba-secretos",
        summary="Un cuento breve sobre una biblioteca con libros que hablan bajito cuando cae la tarde.",
        content="""
En un rincón de la escuela había una biblioteca pequeña. A simple vista parecía normal, pero cuando el reloj marcaba la salida, los libros empezaban a susurrar.

No gritaban. No cantaban. **Susurraban**.

Ema fue la primera en escucharlos. Después llamó a Gael y a Oliver. Los tres apoyaron la oreja en una enciclopedia azul y oyeron una frase:

> *Las mejores historias se despiertan cuando alguien se anima a escribirlas.*

Desde entonces, cada tarde dejaban una hoja nueva dentro de un libro distinto. Y cada mañana encontraban una idea inesperada para seguir creando.
""".strip(),
        kind="publication",
        is_published=True,
        featured=True,
        author_name="A.S.E.",
        category=cuentos,
        tags=[tags[0], tags[1], tags[2]],
    )

    poema = Entry(
        title="Poema del recreo",
        slug="poema-del-recreo",
        summary="Un poema corto sobre correr, imaginar y volver al aula con una idea nueva.",
        content="""
Suena el timbre, corre el sol,
salta el patio alrededor,
una ronda, una misión,
y un poema en el bolsillo del guardapolvo.

Vuelve el aula, vuelve el plan,
la ventana mira al parral,
pero una idea quiere entrar:
**si jugamos con palabras, pueden volar**.
""".strip(),
        kind="publication",
        is_published=True,
        featured=False,
        author_name="A.S.E.",
        category=poemas,
        tags=[tags[0], tags[4]],
    )

    menu_items = [
        MenuItem(label="Inicio", url="/", position=1),
        MenuItem(label="Nuestra historia", url="/paginas/nuestra-historia", position=2),
        MenuItem(label="Blog", url="/blog", position=3),
        MenuItem(label="Publicaciones", url="/publicaciones", position=4),
        MenuItem(label="Etiquetas", url="/etiquetas/infantil", position=5),
    ]

    db.add_all(
        [
            user,
            cuentos,
            poemas,
            otros,
            *tags,
            historia,
            bienvenida,
            cuento,
            poema,
            *menu_items,
        ]
    )
    db.commit()

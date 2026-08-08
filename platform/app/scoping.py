"""Filtrado por pertenencia — el control que impide fugas entre propietarios.

`docs/phase2/SECURITY.md §2` lo llama "el control más importante". La idea es
simple: **el rol nunca basta**. Que alguien sea `owner` no le da derecho a ver
*cualquier* propiedad, solo las suyas. Comprobar el rol y luego consultar por
`id` es exactamente el fallo que filtra datos de un cliente a otro.

Por qué vive todo aquí y no repartido por las rutas: antes de este módulo el
filtro `Property.owner_id == current_user.id` estaba copiado cinco veces solo
en `owner.py`. Cada copia es una oportunidad de olvidarlo, y basta una para
abrir la fuga. Con un único módulo, auditar la seguridad de acceso son cuatro
funciones en vez de sesenta rutas.

Regla de respuesta: cuando algo no pertenece al usuario se devuelve **404, no
403**. Un 403 confirmaría que el objeto existe, y eso ya es información que no
le corresponde (`SECURITY.md §2`).
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Query, Session

from .models import Lease, LeaseStatusEnum, MaintenanceTicket, Property, RoleEnum, User


def _role_of(user: User) -> str:
    """Rol como cadena, tolerando enum o texto plano."""
    role = getattr(user, "role", None)
    return getattr(role, "value", role)


def is_admin(user: User) -> bool:
    return _role_of(user) == RoleEnum.admin.value


# --- Propiedades ------------------------------------------------------------


def scoped_properties(db: Session, user: User) -> Query:
    """Propiedades que este usuario puede ver, según la matriz de roles.

    - admin: todas
    - owner: las suyas
    - inquilino: aquellas donde tiene un arrendamiento activo
    """
    q = db.query(Property)
    if is_admin(user):
        return q
    if _role_of(user) == RoleEnum.owner.value:
        return q.filter(Property.owner_id == user.id)
    # Inquilino: solo la vivienda que habita, y solo mientras el contrato viva.
    return q.join(Lease, Lease.property_id == Property.id).filter(
        Lease.tenant_id == user.id,
        Lease.status == LeaseStatusEnum.active,
    )


def owned_properties(db: Session, user: User) -> Query:
    """Siempre `owner_id == user.id`, **incluso para un admin**.

    Distinta de `scoped_properties` a propósito: la usa el router de owner, que
    representa "mis propiedades como propietario". Un admin que entra por ahí
    ve las suyas, no las de todos; su capacidad de verlo todo vive en el router
    de admin. Mantener las dos semánticas separadas y con nombre evita que
    alguien "arregle" una y rompa la otra sin darse cuenta.
    """
    return db.query(Property).filter(Property.owner_id == user.id)


def get_scoped_property_or_404(db: Session, user: User, property_id: int) -> Property:
    """Una propiedad del usuario, o 404 si no existe o no le pertenece.

    Ambos casos dan la misma respuesta: no se distingue "no existe" de "no es
    tuya", porque distinguirlos revela qué identificadores están en uso.
    """
    prop = scoped_properties(db, user).filter(Property.id == property_id).first()
    if prop is None:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada")
    return prop


def get_owned_property_or_404(db: Session, user: User, property_id: int) -> Property:
    prop = owned_properties(db, user).filter(Property.id == property_id).first()
    if prop is None:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada")
    return prop


def assert_can_assign_property(db: Session, user: User, property_id: int) -> Property:
    """Valida un `property_id` que llegó en un formulario antes de usarlo.

    Es la contraparte de la regla de `DESIGN.md §11`: un propietario no puede
    colgar un inquilino, un ticket ni nada de la propiedad de otro manipulando
    un campo del formulario. Se comprueba en servidor porque el formulario lo
    controla el cliente.
    """
    if is_admin(user):
        prop = db.query(Property).filter(Property.id == property_id).first()
    else:
        prop = owned_properties(db, user).filter(Property.id == property_id).first()
    if prop is None:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada")
    return prop


# --- Arrendamientos (vínculo inquilino ↔ vivienda) --------------------------


def scoped_leases(db: Session, user: User) -> Query:
    """Arrendamientos visibles: admin todos; owner los de sus casas; inquilino los suyos."""
    q = db.query(Lease)
    if is_admin(user):
        return q
    if _role_of(user) == RoleEnum.owner.value:
        return q.join(Property, Property.id == Lease.property_id).filter(
            Property.owner_id == user.id
        )
    return q.filter(Lease.tenant_id == user.id)


def get_scoped_lease_or_404(db: Session, user: User, lease_id: int) -> Lease:
    lease = scoped_leases(db, user).filter(Lease.id == lease_id).first()
    if lease is None:
        raise HTTPException(status_code=404, detail="Arrendamiento no encontrado")
    return lease


# --- Tickets de mantenimiento -----------------------------------------------


def scoped_tickets(db: Session, user: User) -> Query:
    """Tickets visibles.

    - admin: todos
    - owner: los de sus propiedades (aunque los haya levantado otra persona)
    - inquilino: solo los que él reportó
    """
    q = db.query(MaintenanceTicket)
    if is_admin(user):
        return q
    if _role_of(user) == RoleEnum.owner.value:
        return q.join(Property, Property.id == MaintenanceTicket.property_id).filter(
            Property.owner_id == user.id
        )
    return q.filter(MaintenanceTicket.reported_by_user_id == user.id)


def get_scoped_ticket_or_404(db: Session, user: User, ticket_id: int) -> MaintenanceTicket:
    ticket = scoped_tickets(db, user).filter(MaintenanceTicket.id == ticket_id).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    return ticket


# --- Usuarios ---------------------------------------------------------------


def scoped_users(db: Session, user: User) -> Query:
    """Usuarios visibles.

    - admin: todos
    - owner: sus inquilinos (los que tienen arrendamiento en sus casas) y él mismo
    - inquilino: solo él mismo

    Un propietario **no** ve a otros propietarios ni a los inquilinos de otros:
    ese listado es justo lo que un competidor querría.
    """
    q = db.query(User)
    if is_admin(user):
        return q
    if _role_of(user) == RoleEnum.owner.value:
        tenant_ids = [
            row[0]
            for row in db.query(Lease.tenant_id)
            .join(Property, Property.id == Lease.property_id)
            .filter(Property.owner_id == user.id)
            .distinct()
            .all()
        ]
        return q.filter(User.id.in_(tenant_ids + [user.id]))
    return q.filter(User.id == user.id)


def get_scoped_user_or_404(db: Session, user: User, user_id: int) -> User:
    target = scoped_users(db, user).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return target


def owner_of_property(db: Session, property_id: int) -> Optional[User]:
    """Propietario de una vivienda — para enrutar tickets y mensajes.

    No es una función de permisos: no filtra nada. Se mantiene aquí porque
    recorre la misma cadena `Property.owner_id → User` que el resto del módulo
    (ver el hallazgo de `DESIGN.md §11` sobre esa columna sobrecargada).
    """
    prop = db.query(Property).filter(Property.id == property_id).first()
    return db.query(User).filter(User.id == prop.owner_id).first() if prop else None

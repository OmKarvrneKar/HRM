from .models import AuditLog


def log_action(actor, action, obj=None, description="", **metadata):
    """Record an important operation in the audit trail.

    Never store secrets here. `metadata` should contain small, non-sensitive
    values only (ids, status names, dates).
    """
    model_name = ""
    object_id = ""
    if obj is not None:
        model_name = obj.__class__.__name__
        object_id = str(getattr(obj, "pk", "") or "")
    return AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        model_name=model_name,
        object_id=object_id,
        description=description,
        metadata=metadata or {},
    )

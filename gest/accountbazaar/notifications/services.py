from .models import AuditLog


def record_audit(*, actor, action, obj, metadata=None):
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        object_type=obj.__class__.__name__,
        object_id=str(obj.pk),
        metadata=metadata or {},
    )
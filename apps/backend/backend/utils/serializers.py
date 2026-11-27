from bson import ObjectId
from datetime import datetime, date
from backend.utils.timezone import to_local

def serialize_doc(doc: dict, mask_sensitive: bool = True) -> dict:
    """
    Recursively serialize a MongoDB document into a JSON-friendly dict.
    """
    if doc is None:
        return None

    result = {}
    for key, value in doc.items():
        if mask_sensitive and key in ("password_hash", "token_revocation_list", "activation_token"):
            continue

        if isinstance(value, ObjectId):
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
            try:
                local_dt = to_local(value)
                result[f"{key}_local"] = local_dt.strftime("%Y-%m-%d %I:%M:%S %p")
            except Exception:
                pass
        elif isinstance(value, date):
            result[key] = value.strftime("%Y-%m-%d")
        elif isinstance(value, dict):
            result[key] = serialize_doc(value, mask_sensitive=mask_sensitive)
        elif isinstance(value, list):
            result[key] = [
                serialize_doc(item, mask_sensitive=mask_sensitive) if isinstance(item, dict)
                else (str(item) if isinstance(item, ObjectId) else (item.isoformat() if isinstance(item, (datetime, date)) else item))
                for item in value
            ]
        else:
            result[key] = value

    if "name" in result and "full_name" not in result:
        result["full_name"] = result["name"]
    elif "full_name" in result and "name" not in result:
        result["name"] = result["full_name"]

    return result


def serialize_docs(docs: list, mask_sensitive: bool = True) -> list:
    """Serializes a list of MongoDB documents."""
    return [serialize_doc(d, mask_sensitive=mask_sensitive) for d in docs]

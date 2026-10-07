import datetime as dt


def to_utc_iso(value: dt.datetime | None) -> str | None:
    """Serialize a timestamp as ISO 8601 with an explicit UTC offset.

    Naive values are the stored contract (UTC without tzinfo) and are labeled
    as UTC without shifting; aware values are normalized to UTC.
    """
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    else:
        value = value.astimezone(dt.timezone.utc)

    return value.isoformat()

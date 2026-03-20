def ustr(x):
    """Ensure a value is a unicode string."""
    if isinstance(x, str):
        return x
    if isinstance(x, bytes):
        return x.decode('utf-8', errors='replace')
    if x is None:
        return ''
    return str(x)

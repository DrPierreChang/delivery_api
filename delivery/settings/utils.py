def get_settings_dict(globals, settings_keys=None):
    """Return the dictionary of module uppercase variables.

    By default returns all variables.

    Keyword arguments:
    globals         -- globals() dict of current module
    settings_key    -- list of specified variables (default None)
    """
    if not settings_keys:
        return {k: v for k, v in globals.items() if k.isupper()}
    return {k: v for k, v in globals.items() if k in settings_keys}

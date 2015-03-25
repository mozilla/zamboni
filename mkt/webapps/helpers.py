def new_context(context, **kw):
    c = dict(context.items())
    c.update(kw)
    return c

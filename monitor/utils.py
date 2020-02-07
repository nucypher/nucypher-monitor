import click
import maya


def collector(label: str):
    def decorator(func):
        def wrapped(*args, **kwargs):
            start = maya.now()
            result = func(*args, **kwargs)
            end = maya.now()
            delta = end - start
            duration = f"{delta.total_seconds() or delta.microseconds}s"
            click.secho(f"✓ ... {label} [{duration}]", color='blue')
            return result
        return wrapped
    return decorator

from lanxang.cli.main import app


def legacy():
    """The old `atlas` command (until 1.2): same CLI, one line on stderr."""
    import sys
    print("atlas is now lanxang - the atlas command will be removed in 1.2.", file=sys.stderr)
    app()


__all__ = ["app", "legacy"]

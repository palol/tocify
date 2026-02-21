"""Root entrypoint for digest pipeline. Runs from repo root so that
'python digest.py' and 'uv run python digest.py' work as documented."""

from tocify.digest import main

if __name__ == "__main__":
    main()

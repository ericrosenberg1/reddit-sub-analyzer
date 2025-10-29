import os


def main():
    # Defer import so env can be set prior to start
    from .web_app import run

    # Allow PORT override via CLI env, default already handled in run()
    if "PORT" not in os.environ:
        os.environ["PORT"] = os.getenv("PORT", "5055")
    run()


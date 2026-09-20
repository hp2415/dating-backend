"""Background workers entrypoint (ARQ).

Docker::

    python -m workers.runner

Local::

    python -m arq workers.settings.WorkerSettings
"""

from __future__ import annotations

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> None:
    from arq.worker import create_worker

    from workers.settings import WorkerSettings

    worker = create_worker(WorkerSettings)
    worker.run()


if __name__ == "__main__":
    main()

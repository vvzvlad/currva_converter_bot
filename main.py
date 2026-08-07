import logging

from src.settings import settings


def main():
    # Configure the root logger before importing the bot: every module calls
    # logging.basicConfig() at import time, and the first call wins.
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # LOG_LEVEL applies to the root logger, so DEBUG would also switch on urllib3's
    # request logging — and the Telegram API URL embeds the bot token
    # (/bot<TOKEN>/sendMessage). Keep the HTTP client loggers at INFO or above so
    # debugging the bot never leaks credentials into the container logs.
    root_level = logging.getLogger().level
    for noisy in ("urllib3", "requests"):
        logging.getLogger(noisy).setLevel(max(logging.INFO, root_level))

    from src.bot import main as run_bot

    run_bot()


if __name__ == "__main__":
    main()

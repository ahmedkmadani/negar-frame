import logging
import logging.config


def setup_logging(cfg):
    log_file = cfg.get("file", "localizer.log")
    debug=cfg.get("debug", False)

    if debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    logging_config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'standard',
                'level': log_level,
            },
            'file': {
                'class': 'logging.FileHandler',
                'filename': log_file,
                'formatter': 'standard',
                'level': log_level,
            },
        },
        'loggers': {
            '': {
                'handlers': ['console', 'file'],
                'level': log_level,
                'propagate': True,
            },
        }
    }

    logging.config.dictConfig(logging_config)


def get_logger(name):
    return logging.getLogger(name)

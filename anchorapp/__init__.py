""" Flask app to run on a Raspberry Pi which is connected to an anchor windlass.
    This app will allow you to remotely control your anchor from your mobile phone. """

__author__ = 'Vincent Verheul'
__version__ = '2025-05-24'

import sys
import logging
# from logging.handlers import RotatingFileHandler
from flask import Flask  # current_app
from flask_sqlalchemy import SQLAlchemy
from .flaskconfig import FlaskConfig

db = SQLAlchemy()


class CustomLogFormatter(logging.Formatter):
    grey = '\x1b[90m'
    yellow = '\x1b[33;20m'
    red = '\x1b[31;20m'
    bold_red = '\x1b[31;1m'
    reset = '\x1b[0m'
    regular = reset
    log_format = '%(asctime)s %(levelname)s %(message)s'

    formats = {
        logging.DEBUG: f'{grey}{log_format}{reset}',
        logging.INFO: f'{regular}{log_format}{reset}',
        logging.WARNING: f'{yellow}{log_format}{reset}',
        logging.ERROR: f'{red}{log_format}{reset}',
        logging.CRITICAL: f'{bold_red}{log_format}{reset}'
    }

    def format(self, record):
        log_fmt = self.formats.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def set_logger():
    logger = logging.getLogger('anchorapp')  # 'werkzeug'
    logger.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler(stream=sys.stdout)
    # log_format = '%(asctime)s %(levelname)s %(message)s'
    # console_handler.setFormatter(logging.Formatter(log_format))
    console_handler.setFormatter(CustomLogFormatter())
    # file_handler = RotatingFileHandler(filename='anchorapp.log', maxBytes=1024 * 1024, backupCount=5, encoding='UTF8')
    # file_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(console_handler)
    # logger.addHandler(file_handler)
    return logger


log = set_logger()


def create_app(config_class=FlaskConfig):
    """ Instantiate the Flask application """
    log.debug(FlaskConfig.sqlite_path_and_name(as_info_message=True))
    flask_app = Flask(__name__, instance_path=FlaskConfig.sqlite_path_and_name(path_only=True))
    flask_app.config.from_object(config_class)

    db.init_app(flask_app)

    from .app_logic.main import main
    from .app_logic.error_handlers import errors

    flask_app.register_blueprint(main)
    flask_app.register_blueprint(errors)

    return flask_app

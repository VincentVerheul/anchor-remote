import platform


class FlaskConfig:
    SECRET_KEY = '5b47d09bc657f74572e39a84914a267c'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///anchorapp.db'

    # Server name and database path
    prod_server = 'rpi5'
    db_dev_path = '/Data/Vincent/AnchorRemote/pyAnchor'
    db_prod_path = '/home/vincent'

    @classmethod
    def sqlite_path_and_name(cls, path_only=False, as_info_message=False) -> str:
        """ SQLite database path & filename or info message """
        if platform.node() == cls.prod_server:
            instance_path = cls.db_prod_path
        else:
            instance_path = cls.db_dev_path
        db_file_name = cls.SQLALCHEMY_DATABASE_URI[cls.SQLALCHEMY_DATABASE_URI.find('///') + 3:]
        if as_info_message:
            result = f'SQLite database: {db_file_name} in {instance_path}'
        elif path_only:
            result = instance_path
        else:
            result = f'{instance_path}/{db_file_name}'
        return result

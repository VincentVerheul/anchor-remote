import platform


class FlaskConfig:
    SECRET_KEY = '--your-random-secret-key-used-in-CRSF-protection--'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///anchorapp.db'
    SESSION_COOKIE_SECURE = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=48)

    # Server name and database path
    prod_server = 'rpi5'                                        # update to reflect your setup! (Raspberri Pi system name)
    db_dev_path = '/user-name/development-path/project-name'    # update to reflect your setup!
    db_prod_path = '/home/user-name'                            # update to reflect your setup!

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

#!/usr/bin/python3
import os
import platform
from anchorapp import create_app, FlaskConfig, log
from anchorapp.models.db_model import create_database

app = create_app()
app.app_context().push()
db_path_and_name = FlaskConfig.sqlite_path_and_name()
if not os.path.isfile(db_path_and_name):
    create_database()
    log.info(f'Created new SQLite database {db_path_and_name}')

if __name__ == '__main__':
    if platform.system() == 'Windows':
        os.system('color')
    host_name = platform.node()
    raspberri_host_name = FlaskConfig.prod_server
    host = '10.42.0.1' if host_name == raspberri_host_name else 'localhost'
    # host = '0.0.0.0' if host_name == raspberri_host_name else 'localhost'
    app.run(host=host, port=80)

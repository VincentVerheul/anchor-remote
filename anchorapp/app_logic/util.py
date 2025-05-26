
import platform
from datetime import date, datetime, timedelta
from flask import request, flash
import subprocess
from .. import db, log
from ..flaskconfig import FlaskConfig
from ..models.db_model import ConfigApp, ConfigBoat, Site, SiteEvent, User, Action
from .windlass import WindLass


class Glob:
    """ Global variables, initialize with defaults and adjust later when the database has come online """
    initial_state = True
    new_target_set = True
    visitor_control = dict()           # visitor (IP address) has control rights True / False
    app_config = ConfigApp(id=0)       # app config database record proxy
    boat_config = ConfigBoat(id=0)     # boat config database record proxy
    anchor_site = Site(id=0, refname='-', actual_length=0.0)
    site_id = None                     # can always access, also when site is not a current db-record proxy
    site_event = SiteEvent(id=0, site_id=0, action=0)
    site_event_id = None               # can always access, also when site_event is not a current db-record proxy
    cpu_temp_monitor = False           # update from app_config, can always access
    tz_hour_adjust = 0                 # update from app_config, can always access
    cpu_temp_target = 45               # update from app_config, can always access
    cpu_temp_high = 50                 # update from app_config, can always access
    windlass = WindLass(50, 5, 15, 12)
    windlass_running = None            # thread running the windlass logic
    temp_monitor_running = None        # thread running the CPU temperature monitor and fan trigger

    @classmethod
    def ts_adjusted(cls):
        """ Current timestamp adjusted for timezone hour adjustment """
        return datetime.now() + timedelta(hours=cls.tz_hour_adjust)

    @classmethod
    def add_app_config(cls) -> bool:
        """ Add an app config record with ID 1 """
        if ConfigApp.query.get(1) is not None:
            return False
        cls.app_config = ConfigApp(id=1, boat_id=1)
        db.session.add(cls.app_config)
        db.session.commit()
        log.info('Glob.add_default_app_config: created app config record')
        return True

    @classmethod
    def add_first_boat(cls) -> bool:
        """ Add the first boat with ID 1 """
        first_boat = ConfigBoat.query.get(1)
        if first_boat is not None:
            return False
        cls.boat_config = ConfigBoat(id=1, boat_name='?', boat_draught=1.5, boat_length=10.0,
                                     chain_length=50, down_speed=15, up_speed=12)
        db.session.add(cls.boat_config)
        db.session.commit()
        log.info('Glob.add_first_boat: created first boat config record')
        flash(f'Review boat settings please', 'success')
        return True

    @classmethod
    def add_default_site(cls) -> bool:
        """ Add a default anchor site with ID 0 """
        default_site = Site.query.get(0)
        if default_site is not None:
            return False
        cls.anchor_site = Site(id=0, user_id=get_user().id, refname='-', actual_length=0.0)
        cls.site_id = 0
        db.session.add(cls.anchor_site)
        db.session.commit()
        log.info('Glob.add_default_site: created default site')
        return True

    @classmethod
    def load_master_db_records(cls):
        """ Get master-data records from the database, when not already loaded with the current records """
        if not cls.app_config.is_current:
            if ConfigApp.query.get(1) is None:
                cls.add_app_config()
            cls.app_config = ConfigApp.query.get(1)
            cls.cpu_temp_monitor = cls.app_config.cpu_temp_monitor
            cls.tz_hour_adjust = cls.app_config.tz_hour_adjust
            cls.cpu_temp_target = cls.app_config.cpu_temp_target
            cls.cpu_temp_high = cls.app_config.cpu_temp_high
            # log.debug(f'load_db_records: set app_config to {cls.app_config}')
        if cls.boat_config is None:
            cls.add_first_boat()
        if not cls.boat_config.is_current:
            if cls.app_config.boat_id:
                cls.boat_config = cls.boat_config.query.get(cls.app_config.boat_id)
                # log.debug(f'load_db_records: set boat_config to {cls.boat_config} based on '
                #           f'Glob.app_config.boat_id={cls.app_config.boat_id}')
            else:
                cls.boat_config = cls.boat_config.get_last()
                log.debug(f'load_db_records: set boat_config to {cls.boat_config} based on boat_config.get_last')
        if not cls.anchor_site.is_current:
            if cls.site_id:
                cls.anchor_site = cls.anchor_site.query.get(cls.site_id)
                # log.debug(f'load_db_records: site set to {cls.anchor_site} based on Glob.site_id={cls.site_id}')
            else:
                if cls.app_config.site_id:
                    cls.anchor_site = cls.anchor_site.query.get(cls.app_config.site_id)
                    cls.site_id = cls.app_config.site_id
                    log.debug(f'load_db_records: site set to {cls.anchor_site} based on app_config.site_id')
                else:
                    cls.add_default_site()
                    cls.anchor_site = cls.anchor_site.get_last()
                    cls.site_id = cls.anchor_site.id
                    log.debug(f'load_db_records: site set to {cls.anchor_site} based on site.get_last')


def visitor_ip() -> str:
    """ Get IP address of the incoming request """
    if request.environ.get('HTTP_X_FORWARDED_FOR') is not None:
        ip_address = request.environ['HTTP_X_FORWARDED_FOR']   # when behind a proxy
    else:
        ip_address = request.environ['REMOTE_ADDR']
    return ip_address


def set_visitor_control():
    """ Set the visitor control status to True for the first visitor to the server since startup,
        otherwise set the control status to False  """
    ip = visitor_ip()
    if not Glob.visitor_control:
        Glob.visitor_control[ip] = True
        log.debug(f"set_visitor_control - added IP {ip} with control=True")
    elif ip not in Glob.visitor_control:
        Glob.visitor_control[ip] = False
        log.debug(f"set_visitor_control - added IP {ip} with control=False")


def in_control() -> bool:
    """ Visitor is in control? (i.e. authorised to perform actions) """
    ip = visitor_ip()
    return ip in Glob.visitor_control and Glob.visitor_control[ip] is True


def get_user(ip_address='') -> User:
    """ Get user with ip_address. When no ip_address specified, the current visitor_ip is used.
        Create the user record when it does not yet exist. Return user record. """
    if not ip_address:
        ip_address = visitor_ip()
    user = User.query.filter(User.user_ip == ip_address).first()
    if not user:
        user = User(user_ip=ip_address)
        user.username = f'user {ip_address}'
        db.session.add(user)
        db.session.commit()
        log.info(f'get_user: added user {ip_address}')
    return user


def is_number(txt: str) -> bool:
    """ Check if the string txt contains only digit characters, decimal dot or minus sign  """
    return len(txt) != 0 and txt.replace('-', '').replace('.', '').isnumeric()


def write_event(action: Action):
    """ Write a new SiteEvent to the database """
    if action is None:
        return
    if not Glob.anchor_site.is_current:
        Glob.load_master_db_records()
    length = Glob.app_config.manual_range if action.name == 'SET_MAN_RANGE' else Glob.windlass.actual_length
    site_event = SiteEvent(
        start_time=Glob.ts_adjusted(),
        end_time=Glob.ts_adjusted(),
        site_id=Glob.anchor_site.id,
        boat_id=Glob.app_config.boat_id,
        user_id=get_user().id,
        action=action.value,
        target_length=Glob.windlass.target_length,
        start_actual_length=length)
    db.session.add(site_event)
    db.session.commit()
    if action.is_anchor_run():
        Glob.site_event = site_event
        Glob.site_event_id = site_event.id


def update_event():
    """ Update the current event with the actual metrics """
    if Glob.site_event is None:
        log.warning('update_event: Glob.site_event is None')
        return
    if not Glob.anchor_site.is_current:
        Glob.load_master_db_records()
    if not Glob.site_event.is_current:
        log.debug(f'update_event: reloading Glob.site_event with id={Glob.site_event_id}')
        Glob.site_event = SiteEvent.query.get(Glob.site_event_id)
    if Glob.site_event is None:
        log.error('update_event: Glob.site_event is None')
        return
    else:
        Glob.site_event.end_time = Glob.ts_adjusted()
        Glob.site_event.end_actual_length = Glob.windlass.actual_length
        db.session.add(Glob.site_event)
        db.session.commit()
    # update pause event
    pause_event = SiteEvent.query.get(Glob.site_event_id + 1)
    if pause_event and Action(pause_event.action).name == 'PAUSE':
        pause_event.start_actual_length = Glob.windlass.actual_length
        db.session.add(pause_event)
        db.session.commit()


def get_route(url: str):
    """ Get url part after the domain """
    route = ''
    if not url:
        return route
    ptr = url.find('//')
    if ptr == -1:
        return route
    ptr = url.find('/', ptr + 2)
    if ptr == -1:
        return route
    route = url[ptr+1:]
    return route


def get_form_response(table_name: str, obj):
    """ Get request.form data and map to the SQLAlchemy record object for table with table_name """
    tbl = db.metadata.tables[table_name]
    for col in tbl.columns:
        if col.refname not in request.form:
            continue
        val = request.form[col.refname].strip()
        if col.type.python_type is str:
            val = val if type(val) is str else str(val)
        elif col.type.python_type is int:
            val = int(val) if val.replace('-', '').isnumeric() else 0
        elif col.type.python_type is float:
            val = float(val) if val.replace('-', '').replace('.', '').isnumeric() else 0.0
        elif col.type.python_type is date:
            val = date.fromisoformat(val)
        elif col.type.python_type is datetime:
            val = datetime.fromisoformat(val)
        setattr(obj, col.refname, val)


# def format_str(formfield, nrdecimals=0, yesno=False):
#     if formfield is None:
#         return 'None'
#     if type(formfield) is float:
#         formt = '{:3.' + str(nrdecimals) + 'f}'
#         result = formt.format(formfield)
#     elif type(formfield) is datetime:
#         result = formfield.strftime('%d %b %Y')
#     elif type(formfield) is int and yesno:
#         result = 'yes' if formfield else 'no'
#     else:
#         result = str(formfield)
#     return result


def run_os_command(command_parts: list) -> tuple[str, str]:
    """ Run a command on the operating system. Specify the command_parts as strings.
        Each separate when in the OS separated by as space.
        Returns a tuple with output and error texts. """
    result = None
    output_text = error_text = ''

    try:
        result = subprocess.run(command_parts, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    except subprocess.CalledProcessError as err:
        error_text = f"{err} {getattr(err, 'output', 'an error occured')}"

    if result:
        if result.stdout:
            output_text = result.stdout.decode('utf-8')
    return output_text, error_text


def cpu_temperature() -> float:
    """ Get CPU temperature in degrees Celcius """
    if platform.node() != FlaskConfig.prod_server:
        return 60.0
    command_parts = ['vcgencmd', 'measure_temp']
    output_text, error_text = run_os_command(command_parts)
    if output_text:
        start_p = output_text.find('temp=') + len('temp=')
        end_p = output_text.find("'C")
        try:
            temp_c = float(output_text[start_p: end_p])
        except TypeError:
            log.error(f'cpu_temperature: TypeError for {output_text}')
            temp_c = 0.0
        return temp_c

    if error_text:
        if output_text and output_text[-1:] == '\n':
            output_text = output_text[:-1]
        log.debug(f'cpu_temperature: {output_text}')
        log.error(f'cpu_temperature: {error_text}')
    return -1.0

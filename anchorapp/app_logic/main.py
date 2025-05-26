
# import os
# import signal
import platform
import threading
from time import sleep
from decimal import Decimal
from datetime import date, datetime, timedelta
from flask import render_template, redirect, url_for, Blueprint, Response, request, flash, session  # current_app
from .. import __version__, log, db  # scheduler
from ..models.db_model import ConfigBoat, Site, SiteEvent, Action  # User, ConfigApp
from ..flaskconfig import FlaskConfig
from .util import (Glob, visitor_ip, set_visitor_control, in_control, get_user, get_route,
                   is_number, write_event, update_event, run_os_command, cpu_temperature)
from ..models.forms import ConfigAppForm, ConfigBoatForm, HomeForm, TargetForm, SiteSelectForm
from .windlass import relay


main = Blueprint('main', __name__)


def set_windlass_param():
    """ Update the relevant windlass instance parameters which originate from the boat configuration """
    Glob.windlass.quit = False
    Glob.windlass.update_param(Glob.boat_config.chain_length, Glob.app_config.min_length_up,
                               Glob.boat_config.down_speed, Glob.boat_config.up_speed)
    conf_txt = f'chain_length={Glob.windlass.chain_length}m, min_length_up={Glob.app_config.min_length_up} '\
               f'dn_speed={Glob.windlass.dn_speed}m/min, up_speed={Glob.windlass.up_speed}m/min '
    log.info(f'updated windlass parameters: {conf_txt}')


def windlass_thread():
    """ Windlass process - to run in a separate thread """
    # with scheduler.app.app_context():  # when using APScheduler
    log.info('start windlass thread')
    Glob.windlass.run_listener()
    log.info('finish windlass thread')
    Glob.windlass_running = None


def start_windlass_thread():
    """ Start the windlass listener """
    Glob.load_master_db_records()
    set_windlass_param()
    thread = threading.Thread(target=windlass_thread, daemon=True)
    thread.start()
    Glob.windlass_running = thread


def temp_monitor_thread():
    """ Monitor CPU temperature and trigger the fan as necessary """
    log.info('start temp_monitor thread')
    if not relay.connected:
        relay.connect()
    temp_c = 0.0
    while relay.connected and temp_c > -1.0:
        if not Glob.cpu_temp_monitor:
            print('cpu_temp_monitor is False, sleep 60 secs')
            sleep(60)
        temp_c = cpu_temperature()
        if temp_c >= Glob.cpu_temp_high and not relay.rpi_fan_switch.is_active:
            relay.rpi_fan_switch.on()
            log.debug(f'CPU temperature is {temp_c} with upper threshold {Glob.cpu_temp_high}, fan switched on')
        elif temp_c <= Glob.cpu_temp_target and relay.rpi_fan_switch.is_active:
            relay.rpi_fan_switch.off()
            log.debug(f'CPU temperature is {temp_c} with lower threshold {Glob.cpu_temp_target}, fan switched off')
        sleep(20)
    log.info('stop temp_monitor thread')


def start_temp_monitor():
    """ Start the CPU temperature monitor thread """
    thread = threading.Thread(target=temp_monitor_thread, daemon=True)
    thread.start()
    Glob.temp_monitor_running = thread


@main.route('/control/<string:action>')
def control(action: str):
    """ Display message 'not in control' when not the first visitor since server start.
        (with manual URL overrule action possibility) """
    if action == '_take_ctrl':
        session_ip = visitor_ip()
        Glob.visitor_control[session_ip] = True
        log.debug(f'set_visitor_control: updated IP {session_ip} changed control from False to True')
        for ip, ctrl in Glob.visitor_control.items():
            if ctrl and ip != session_ip:
                Glob.visitor_control[ip] = False
                log.debug(f'set_visitor_control: updated IP {ip} changed control from True to False')
        flash('Taken control!', 'success')
        write_event(Action.TAKE_CONTROL)
        return redirect(url_for('main.home'))
    return render_template('control.html', dark=session.get('theme') == 'dark', action=action)


@main.route('/stream_actual')
def actual_length_updater():
    """ Send a stream to the client to update the actual chain length: use an EventSource in JavaScript """
    def stream_gen():
        # log.debug(f'stream endpoint was called')
        init = True
        while not Glob.windlass.quit:
            if Glob.windlass.running:
                sleep(0.1)
                yield f'data: {round(Glob.windlass.actual_length, 1)}\n\n'
            elif init:
                yield f'data: {round(Glob.windlass.actual_length, 1)}\n\n'
                init = False
            elif Glob.windlass.signal_completed:
                yield f'data: -1000\n\n'
            else:
                sleep(0.5)
    return Response(stream_gen(), mimetype='text/event-stream')


def pauze_anchor_action():
    """ Pauze anchor action immediately via relay and set windlass status afterwards """
    if not in_control():
        return
    if relay is not None and relay.connected:
        relay.anchor_dn_switch.off()
        relay.anchor_up_switch.off()
    Glob.windlass.pause()


def run_action_type(manual=False) -> Action:
    """ Action type depending on windlass target / actual """
    direction = Glob.windlass.run_direction()
    if direction == 1:
        action = Action.DOWN_MANUAL if manual else Action.DOWN_TO_TARGET
    elif direction == -1:
        action = Action.UP_MANUAL if manual else Action.UP_TO_TARGET
    else:
        action = Action.UNDEFINED
    return action


def anchor_up_disabled_msg():
    msg = f'Anchor up is disabled (Config)'
    log.error(msg)
    flash(msg, 'danger')


@main.route('/anchor/<string:action>')
def anchor(action: str):
    """ Anchor up, down, pause, run/resume """
    if not in_control():
        return redirect(url_for('main.control', action='info'))
    log.info(f'anchor action: {action}')
    if not Glob.windlass_running:
        log.warning('windlass thread was not running')
        start_windlass_thread()
    if action == 'resume':
        Glob.load_master_db_records()
        if Glob.windlass.run_direction() == -1 and not Glob.app_config.allow_achor_up:
            anchor_up_disabled_msg()
        elif Glob.windlass.resume_enabled():
            write_event(run_action_type())
            Glob.windlass.resume()
    elif action == 'up':
        Glob.load_master_db_records()
        if not Glob.app_config.allow_achor_up:
            anchor_up_disabled_msg()
        elif Glob.windlass.go_up(meters=Glob.app_config.manual_range):
            write_event(run_action_type(manual=True))
    elif action == 'down':
        Glob.load_master_db_records()
        if Glob.windlass.go_down(meters=Glob.app_config.manual_range):
            write_event(run_action_type(manual=True))
    elif action == 'pause':
        pauze_anchor_action()
        write_event(Action.PAUSE)
    else:
        msg = f'Invalid anchor action: "{action}"'
        log.error(msg)
        flash(msg, 'danger')
    Glob.new_target_set = False
    return redirect(url_for('main.home'))


def find_existing_sites(search_for='') -> dict:
    """ Find existing sites in recent events and return a dict with site_id and refname.
        Optionally filter on search_for to be a partial string in the site refname (no wildcards). """
    oldest = datetime.now() - timedelta(weeks=25)
    recent_sites = dict()
    for event in SiteEvent.query.filter(SiteEvent.start_time >= oldest).all():
        if event.site.id not in recent_sites:
            if search_for and search_for in event.site.refname or not search_for:
                recent_sites[event.site.id] = event.site.refname
    return recent_sites


def site_choices(include_site_0=False, include_new_option=False):
    """ Choice list of sites, restricted to max 5 weeks history """
    choice_list = list()
    recent_sites = find_existing_sites()
    if include_new_option:
        choice_list.append((-2, '<new site>'))
        choice_list.append((-1, '<edit site>'))
    for site_id, site_refname in recent_sites.items():
        if not include_site_0 and site_id == 0:
            continue
        choice_list.append((site_id, site_refname))
    return choice_list


def site_switch(form: TargetForm) -> bool:
    """ Switch to a new or existing site, other than the current site, or edit existing site name """
    switched = False
    existing = dict()
    if form.refname.data:
        if form.exist_site_id.data == -1:                                                # <edit site>
            old_new_msg = f'from "{Glob.anchor_site.refname}" to "{form.refname.data}"'
            Glob.anchor_site.refname = form.refname.data
            Glob.anchor_site.time_stamp = Glob.ts_adjusted()
            db.session.add(Glob.anchor_site)
            db.session.commit()
            log.info(f'site_switch - edit site name: {old_new_msg}')
            return switched
        else:
            existing = find_existing_sites(form.refname.data)
            for site_id in existing:
                form.exist_site_id.data = site_id
    if not existing and form.exist_site_id.data == -2 and form.refname.data:             # <new site>
        if form.refname.data != Glob.anchor_site.refname:
            switched = True
            Glob.anchor_site = Site()
            log.debug(f'site_switch to new site: "{form.refname.data}"')
        form.populate_obj(Glob.anchor_site)
    elif form.exist_site_id.data >= 0 and form.exist_site_id.data != Glob.anchor_site.id:
        switched = True
        Glob.anchor_site = Site.query.get(form.exist_site_id.data)
        Glob.site_id = form.exist_site_id.data
        log.debug(f'site_switch to existing site: "{Glob.anchor_site}"')
    return switched


def save_site_selected():
    """ Save the selected site to the App Config record """
    Glob.site_id = Glob.anchor_site.id
    Glob.app_config.site_id = Glob.anchor_site.id
    db.session.add(Glob.app_config)
    db.session.commit()
    log.debug(f'save_site_selected: "{Glob.anchor_site}"')


@main.route('/target', methods=['GET', 'POST'])
def set_target():
    """ Set the target chain length based on depth """
    if not in_control():
        return redirect(url_for('main.control', action='info'))
    if Glob.windlass.running:
        flash('Anchor is running, pause first', 'warning')
        return redirect(url_for('main.home'))
    Glob.load_master_db_records()
    form = TargetForm()
    form.exist_site_id.choices = site_choices(include_new_option=True)
    if request.method == 'GET':
        log.debug('target - get')
        form.process(obj=Glob.anchor_site)
        form.refname.data = None
        if Glob.windlass.actual_length > Glob.app_config.min_length_up and \
                Glob.windlass.actual_length == Glob.windlass.target_length:
            form.go_anchor_up.data = True
            form.exist_site_id.data = Glob.anchor_site.id
        elif Glob.windlass.actual_length == 0:
            form.exist_site_id.data = -2  # new site
        else:
            form.exist_site_id.data = Glob.anchor_site.id
    elif form.validate_on_submit():
        log.debug('target - post')
        changed_site = site_switch(form)
        depth = float(form.anchor_depth.data) if is_number(str(form.anchor_depth.data)) else 0.0
        Glob.anchor_site.user_id = get_user().id
        Glob.anchor_site.anchor_depth = depth
        Glob.new_target_set = True
        if form.go_anchor_up.data:
            Glob.windlass.target_length = Glob.app_config.min_length_up
        else:
            Glob.windlass.target_length = Glob.boat_config.deploy_length(
                depth, use_safety=form.add_safety.data, min_length_remain=Glob.app_config.min_length_up)
        Glob.anchor_site.actual_length = Glob.windlass.actual_length if Glob.windlass.actual_length else 0.0
        db.session.add(Glob.anchor_site)
        db.session.commit()
        if changed_site:
            save_site_selected()
        write_event(Action.SET_TARGET)
        return redirect(url_for('main.home'))
    return render_template('target.html', dark=session.get('theme') == 'dark', form=form)


def save_site_actual_length():
    """ Save the actual deployed chain length to the current site and write to the database """
    Glob.load_master_db_records()
    Glob.anchor_site.actual_length = round(Glob.windlass.actual_length, 1)
    if Glob.app_config.site_id is None:
        Glob.app_config.site_id = Glob.anchor_site.id
        db.session.add(Glob.app_config)
    db.session.add(Glob.anchor_site)
    db.session.commit()


def get_site_actual_length():
    """ Get the actual dropped chain length from the current site, as it was saved to the database """
    Glob.load_master_db_records()
    Glob.windlass.actual_length = Glob.anchor_site.actual_length
    Glob.windlass.target_length = Glob.app_config.min_length_up if Glob.anchor_site.actual_length else 0


def init_last_site() -> bool:
    """ Get the last site actual deployed chain length after the application was started """
    if Glob.initial_state:
        Glob.load_master_db_records()
        get_site_actual_length()
        Glob.initial_state = False
        write_event(Action.INITIAL_VALUE)
        return True
    return False


def adjust_values(form: HomeForm):
    """ Adjust windlass target / actual chain length and / or manual range """
    if not Glob.windlass.running and Glob.windlass.actual_length != form.actual_length.data:
        log.debug(f'adjust_values - Adjust actual from {Glob.windlass.actual_length} to {form.actual_length.data}')
        Glob.windlass.paused = True
        Glob.windlass.actual_length = form.actual_length.data
        save_site_actual_length()
        write_event(Action.ADJUST_ACTUAL)
    if not Glob.windlass.running and Glob.windlass.target_length != int(form.target_length.data):
        log.debug(f'adjust_values - Adjust target from {Glob.windlass.target_length} to {form.target_length.data}')
        Glob.windlass.paused = True
        Glob.windlass.target_length = int(form.target_length.data)
        write_event(Action.ADJUST_TARGET)
    if form.manual_range.data != Decimal(Glob.app_config.manual_range):
        new_manual_range = float(form.manual_range.data)
        log.debug(f'adjust_values - Adjust manual range from {Glob.app_config.manual_range} to {new_manual_range}')
        Glob.app_config.manual_range = new_manual_range
        write_event(Action.SET_MAN_RANGE)
    db.session.add(Glob.app_config)
    db.session.commit()


@main.route('/home')
@main.route('/', methods=['GET', 'POST'])
def home():
    """ Anchor Remote home page """
    if 'theme' not in session:
        session['theme'] = 'light'
    set_visitor_control()
    if Glob.initial_state:
        init_last_site()
    Glob.load_master_db_records()
    if Glob.windlass.signal_completed:
        Glob.windlass.signal_completed = False
        log.debug('home - reset windlass.signal_completed from True to False')
        Glob.windlass.reset_manual_run()
        update_event()
        save_site_actual_length()
        curr_action = Action(Glob.site_event.action)
        if Glob.windlass.on_target() and curr_action.is_anchor_run(manual_run=False):
            write_event(Action.TARGET_REACHED)
    form = HomeForm()
    form.manual_range.render_kw['max'] = Decimal(Glob.app_config.max_manual_range)
    if request.method == 'GET':
        log.debug('home - get')
        form.target_length.data = int(Glob.windlass.target_length)
        form.actual_length.data = round(Glob.windlass.actual_length, 1)
        form.manual_range.data = Glob.app_config.manual_range
    elif form.validate_on_submit():
        log.debug('home - post (Adjust)')
        adjust_values(form)
    if not Glob.windlass_running:
        start_windlass_thread()
    if not Glob.temp_monitor_running:
        start_temp_monitor()
    control_status = Glob.visitor_control[visitor_ip()]
    dark = session.get('theme') == 'dark'
    set_ok = Glob.windlass.set_enabled()
    run_ok = Glob.new_target_set and not Glob.windlass.on_target()  # Glob.windlass.run_enabled()
    pause_ok = not Glob.new_target_set and Glob.windlass.pause_enabled()
    resume_ok = not Glob.new_target_set and Glob.windlass.resume_enabled()
    direction_txt = Glob.windlass.direction_msg(use_target_actual=True, idle_as_blank=True)
    image_file = f"chevrons-{'white' if dark else 'black'}-{direction_txt}.svg"
    direction_img = url_for('static', filename=image_file) if direction_txt else ''
    template = 'control_basic.html' if Glob.app_config.basic_mode else 'control_full.html'
    return render_template(template, dark=dark, control=control_status, set_ok=set_ok, run_ok=run_ok,
                           pause_ok=pause_ok, resume_ok=resume_ok, direction_img=direction_img,
                           target=form.target_length.data, site=Glob.anchor_site.refname, form=form)


@main.route('/help')
def help_text():
    log.debug('help - get')
    min_length_up = int(Glob.windlass.min_length_up)
    dark = session.get('theme') == 'dark'
    basic_mode = Glob.app_config.basic_mode
    return render_template('help.html', dark=dark, basic_mode=basic_mode, min_length_up=min_length_up)


@main.route('/about')
def about():
    log.debug('about - get')
    temp_c = cpu_temperature()
    return render_template('about.html', dark=session.get('theme') == 'dark', version=__version__, temp_c=temp_c)


def get_site_events(site_id: int) -> list:
    """ Select site events and format into a list of dicts """
    if site_id != Glob.anchor_site.id:
        site = Site.query.get(site_id)
    else:
        site = Glob.anchor_site
    site_events = list()
    day_name = ('-', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
    prev_date = date(2000, 1, 1)
    for event in site.events:
        curr_date = event.start_time.date()
        action = Action(event.action)
        if curr_date != prev_date:
            day = day_name[curr_date.isoweekday()]
            rec = {'start_time': str(curr_date), 'action': day, 'actual_length': '', 'is_date': True}
            site_events.append(rec)
            prev_date = curr_date
        if action.name in ('SET_TARGET', 'ADJUST_TARGET'):
            length = event.target_length
        elif action.name.endswith('MANUAL'):
            length = event.end_actual_length
        else:
            length = event.start_actual_length
        if event.start_time.microsecond >= 500_000:
            event.start_time += timedelta(seconds=1)
        event.start_time.replace(microsecond=0)
        site_events.append({
            'start_time': str(event.start_time)[11:19],
            'action': action.name.lower().replace('_', ' '),
            'actual_length': length if action.is_length_relevant else '',
            'is_date': False,
        })
    return site_events


@main.route('/history', methods=['GET', 'POST'])
def history():
    """ Show history per selected site """
    Glob.load_master_db_records()
    form = SiteSelectForm()
    site_choice_list = site_choices(include_site_0=True)
    form.site_id.choices = site_choice_list
    site_events = list()
    if request.method == 'GET':
        log.debug(f'history - get: site_id={Glob.anchor_site.id}')
        form.site_id.data = Glob.anchor_site.id
        site_events = get_site_events(Glob.anchor_site.id)
    elif form.validate_on_submit():
        log.debug(f'history - post: site_id={form.site_id.data}')
        site_id = int(form.site_id.data)
        site_events = get_site_events(site_id)
    return render_template('history.html', dark=session.get('theme') == 'dark', site_events=site_events, form=form)


def boat_choices():
    """ Choice list of boats from the boat config table, restricted to max 4 years history """
    oldest = datetime.now() - timedelta(weeks=210)
    choice_list = [(-1, '<add boat>')]
    for boat in ConfigBoat.query.filter(ConfigBoat.created_on >= oldest).all():
        choice_list.append((boat.id, boat.boat_name))
    return choice_list


@main.route('/config_app', methods=['GET', 'POST'])
def config_app():
    """ Edit app configuration settings """
    log.debug('config_app - get')
    set_visitor_control()
    if not in_control():
        return redirect(url_for('main.control', action='info'))
    Glob.load_master_db_records()
    boat_choice_list = boat_choices()
    form = ConfigAppForm()
    form.boat_id.choices = boat_choice_list
    if request.method == 'GET':
        form.process(obj=Glob.app_config)
    elif form.validate_on_submit():
        form.populate_obj(Glob.app_config)
        Glob.cpu_temp_monitor = Glob.app_config.cpu_temp_monitor
        Glob.tz_hour_adjust = Glob.app_config.tz_hour_adjust
        Glob.cpu_temp_target = Glob.app_config.cpu_temp_target
        Glob.cpu_temp_high = Glob.app_config.cpu_temp_high
        add_boat = Glob.app_config.boat_id < 0
        if add_boat:
            Glob.boat_config = ConfigBoat()
            Glob.boat_config.time_stamp = Glob.ts_adjusted()
            db.session.add(Glob.boat_config)
            db.session.commit()
            Glob.app_config.boat_id = Glob.boat_config.id
        if not Glob.cpu_temp_monitor:
            if relay is not None and relay.connected:
                relay.rpi_fan_switch.off()
        Glob.app_config.time_stamp = Glob.ts_adjusted()
        db.session.add(Glob.app_config)
        db.session.commit()

        Glob.boat_config = ConfigBoat.query.get_or_404(Glob.app_config.boat_id)
        set_windlass_param()
        if add_boat:
            flash(f'New boat added with default settings', 'success')
            return redirect(url_for('main.config_boat'))
        else:
            flash(f'App config was updated', 'success')
        write_event(Action.CONFIG)
    return render_template('config_app.html', dark=session.get('theme') == 'dark', form=form)


@main.route('/config_boat', methods=['GET', 'POST'])
def config_boat():
    """ Edit boat configuration settings """
    log.debug('config_boat - get')
    set_visitor_control()
    if not in_control():
        return redirect(url_for('main.control', action='info'))
    form = ConfigBoatForm()
    if request.method == 'GET':
        Glob.load_master_db_records()
        if not ConfigBoat.query.filter(ConfigBoat.id == Glob.app_config.boat_id).first():
            db.session.add(Glob.boat_config)
            db.session.commit()
        Glob.boat_config = ConfigBoat.query.get_or_404(Glob.app_config.boat_id)
        form.process(obj=Glob.boat_config)
    elif form.validate_on_submit():
        isnew = False
        Glob.boat_config = ConfigBoat.query.get_or_404(Glob.app_config.boat_id)
        form.populate_obj(Glob.boat_config)
        Glob.boat_config.id = int(Glob.boat_config.id)
        Glob.boat_config.time_stamp = Glob.ts_adjusted()
        db.session.add(Glob.boat_config)
        db.session.commit()
        msg = f'Boat config {Glob.boat_config.boat_name} was {"created" if isnew else "updated"}'
        log.info(msg)
        flash(msg, 'success')
        set_windlass_param()
        write_event(Action.BOAT_SETTINGS)
    return render_template('config_boat.html', dark=session.get('theme') == 'dark', form=form)


@main.route('/theme')
def theme():
    log.debug('theme - get')
    wreq = request.headers.environ.get('werkzeug.request')  # noqa
    if wreq:
        prev_page = get_route(wreq.referrer)
        prev_page = 'home' if prev_page == '' else prev_page
        prev_page = 'help_text' if prev_page == 'help' else prev_page
    else:
        prev_page = 'home'
    if prev_page.startswith('config'):
        log.debug(f'Ignored theme switch because data would be lost on page {prev_page}')
        return '', 204  # do not reload the current page because of user inputs
    session_theme = session.get('theme')
    session['theme'] = 'dark' if session_theme == 'light' or not session_theme else 'light'
    log.debug(f"set theme to {session['theme']}")
    return redirect(url_for(f'main.{prev_page}'))


@main.route('/quit_confirm')
def quit_confirm():
    """ Open page to ask user to confirm """
    return render_template('quit.html', dark=session.get('theme') == 'dark')


@main.route('/quit')
def quit_app():
    """ Stop Windlass thread and initiate system shutdown in 60 secs when running on Raspberri Pi """
    pauze_anchor_action()
    if Glob.windlass.anchor_is_almost_up():
        Glob.windlass.actual_length = 0.0
        save_site_actual_length()
    write_event(Action.QUIT)
    if Glob.windlass_running:
        Glob.windlass.quit_listener()
    if platform.node() == FlaskConfig.prod_server:
        log.info('initiating server shutdown in 60 seconds')
        flash('The Raspberri Pi will shut down in 60 secs', 'warning')
        run_os_command(['sudo', 'shutdown'])
    else:
        flash('Not running on a Raspberri Pi, no system shutdown initiated', 'warning')
        # sleep(2.0)
        # os.kill(os.getpid(), signal.SIGINT)
    return redirect(url_for('main.home'))

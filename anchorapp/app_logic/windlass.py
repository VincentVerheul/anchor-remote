
import platform
from datetime import datetime
from time import sleep
from flask import flash
from gpiozero import Device, DigitalOutputDevice
from .. import log
from ..flaskconfig import FlaskConfig
if platform.node() != FlaskConfig.prod_server:
    from gpiozero.pins.mock import MockFactory
    Device.pin_factory = MockFactory()


class Relay:
    """ Connection to the Raspberri Relay board """

    def __init__(self, channel1_pin=26, channel2_pin=20, channel3_pin=21):
        self. connected = False
        self.channel1_pin = channel1_pin
        self.channel2_pin = channel2_pin
        self.channel3_pin = channel3_pin
        self.anchor_up_switch = None
        self.anchor_dn_switch = None
        self.rpi_fan_switch = None

    def connect(self):
        """ Connect to relay board """
        if self.connected:
            return
        self.anchor_dn_switch = DigitalOutputDevice(self.channel1_pin, active_high=False, initial_value=False)
        self.anchor_up_switch = DigitalOutputDevice(self.channel2_pin, active_high=False, initial_value=False)
        self.rpi_fan_switch = DigitalOutputDevice(self.channel3_pin, active_high=False, initial_value=False)
        self.connected = True

    def disconnect(self):
        """ Disconnect from relay board """
        if not self.connected:
            return
        self.anchor_up_switch.close()
        self.anchor_dn_switch.close()
        self.rpi_fan_switch.close()
        self.connected = False

    def __repr__(self):
        return f'Relay(initialized={self.connected})'


relay = Relay()  # instatiate (singleton) here to make it also available to other modules


class WindLass:
    """ To control the windlass. Runs the up or down button for a period of time estimated
        to arrive at the target chain length. While running up or down it will be blocking
        the process. Run it therefore in a separate thread or process when the main process should
        still be responsive to user inputs."""

    def __init__(self, chain_length: int, min_length_up: int, down_speed: float, up_speed: float):
        self.wait_secs = 0.2                     # wait time in listener event loop
        self.threshold = 0.3                     # threshold to compare actual and target length (in meters)
        self.chain_length = chain_length         # anchor chain length
        self.target_length = 0                   # target deployed chain length
        self.actual_length = 0.0                 # actual deployed chain length
        self.min_length_up = min_length_up       # stop at this (estimated) length when pulling up
        self.dn_speed = down_speed               # down speed in meter per minute
        self.dn_speed_ms = 0.0                   # in meter per second
        self.manual_down_target = 0.0            # target after manual input to go down for n meters
        self.up_speed = up_speed                 # up speed in meter per minute
        self.up_speed_ms = 0.0                   # in meter per second
        self.manual_up_target = 0.0              # target after manual input to go up for n meters
        self.prev_was_manual = False             # previous action was a manual up / down
        self.running = False                     # windlass is active
        self.paused = True                       # run to target not yet started or interrupted
        self.direction = 0                       # 1 = down, -1 = up, 0 = idle
        self.signal_completed = False            # when action completed and client must be notified
        self.quit = False                        # to quit the event listener
        self.update_param(chain_length, min_length_up, down_speed, up_speed)

    def __repr__(self):
        return f'WindLass({self.status_msg()})'

    def update_param(self, chain_length: int, min_length_up: int, down_speed: float, up_speed: float):
        """ Update parameters after instantiation """
        self.chain_length = chain_length
        self.min_length_up = min_length_up
        self.dn_speed = down_speed
        self.dn_speed_ms = self.dn_speed / 60.0
        self.up_speed = up_speed
        self.up_speed_ms = self.up_speed / 60.0

    def status(self) -> dict:
        """ Current status as a dict """
        return {'target_length': self.target_length, 'actual_length': self.actual_length,
                'running': self.running, 'paused': self.paused, 'direction': self.direction}

    def run_direction(self) -> int:
        """ Direction at the next run or continue command """
        if self.manual_down_target:
            direction = 1
        elif self.manual_up_target:
            direction = -1
        elif self.actual_length < self.target_length:
            direction = 1
        elif self.actual_length > self.target_length:
            direction = -1
        else:
            direction = 0
        return direction

    def anchor_is_almost_up(self) -> bool:
        """ Anchor has been pulled-up to (almost) the minimum length """
        return self.target_length == self.min_length_up and self.actual_length < self.target_length * 1.5

    def direction_msg(self, use_target_actual=False, idle_as_blank=False):
        """ Current direction as a text """
        if use_target_actual:
            # direction = self.run_direction() if self.actual_length > 0 else 'idle'
            direction = self.run_direction()
        else:
            direction = self.direction
        if direction == -1:
            direction_txt = 'up'
        elif direction == 1:
            direction_txt = 'down'
        else:
            direction_txt = '' if idle_as_blank else 'idle'
        return direction_txt

    def status_msg(self) -> str:
        """ Current status as a string """
        direction_txt = self.direction_msg()
        msg = f'target_length={self.target_length}m actual_length={round(self.actual_length, 2)}m ' \
              f'running={self.running} paused={self.paused} direction={direction_txt}'
        return msg

    def pause(self) -> bool:
        """ Pause current up or down run """
        if self.running:
            self.paused = True
            log.debug('windlass.pause - pauze start')
            return True
        else:
            log.debug('windlass.pause - not running!')
            return False

    def resume(self) -> bool:
        """ Resume after being paused """
        if self.paused:
            self.paused = False
            self.reset_manual_run()
            self.direction = self.run_direction()
            self.prev_was_manual = False
            log.debug(f'windlass.resume - resumed with direction {self.direction}')
        return not self.paused

    def go_down(self, meters=0.0) -> bool:
        """ Extend down for n meters """
        status = False
        if not meters:
            return status
        if self.running:
            log.warning(f'windlass.go_down requested but windlass is currently running, ignored')
            flash('Already running, anchor-down ignored', category='warning')
            return status
        if self.actual_length >= (self.chain_length - 1):
            log.warning(f'windlass.go_down requested but actual length is (almost) at max length, ignored')
            flash(f'Already at max, anchor-down ignored', category='warning')
            return status
        if meters:
            self.manual_up_target = 0.0
            self.manual_down_target = min(round(self.actual_length + meters, 1), self.chain_length)
        self.direction = 1
        self.paused = False
        self.prev_was_manual = True
        status = True
        return status

    def go_up(self, meters=0.0) -> bool:
        """ Pull up for n meters """
        status = False
        if not meters:
            return status
        if self.running:
            log.warning('windlass.go_up requested but windlass is currently running, ignored')
            flash('Already running, anchor-up ignored', category='warning')
            return status
        if self.actual_length <= self.min_length_up:
            log.warning(f'windlass.go_up requested but actual length is below {int(self.min_length_up)}m, ignored')
            flash(f'Below {self.min_length_up}m, anchor-up ignored', category='warning')
            return status
        if meters:
            self.manual_down_target = 0.0
            self.manual_up_target = max(round(self.actual_length - meters, 1), self.min_length_up)
        self.direction = -1
        self.paused = False
        self.prev_was_manual = True
        status = True
        return status

    def reset_manual_run(self):
        self.manual_down_target = 0.0
        self.manual_up_target = 0.0

    def on_target(self) -> bool:
        """ Check of the actual chain length out is on the target length """
        target = self.target_length
        if self.manual_down_target:
            self.direction = 1
            target = self.manual_down_target
        elif self.manual_up_target:
            self.direction = -1
            target = self.manual_up_target

        if self.direction == 0:
            is_on_target = abs(round(self.actual_length - target, 1)) < self.threshold
        elif self.direction == -1:
            is_on_target = self.actual_length <= target
        elif self.direction == 1:
            is_on_target = self.actual_length >= target
        else:
            log.error(f'windlass.on_target direction={self.direction} is undefined')
            is_on_target = True
        # if not self.paused:
        #     log.debug(f'on_target={is_on_target}  {self.status_msg()}')
        return is_on_target

    def set_enabled(self) -> bool:
        """ Set button relevant to use """
        result = self.target_length < self.min_length_up
        if not result and not self.prev_was_manual:
            result = self.on_target()
        return result

    def pause_enabled(self) -> bool:
        """ Pause button relevant to use """
        return not self.paused and not self.on_target()

    def resume_enabled(self) -> bool:
        """ Resume button relevant to use """
        if not self.paused:
            return False
        relevant = (self.actual_length < self.target_length or
                    (self.actual_length > self.target_length >= self.min_length_up))
        return relevant

    def run_anchor(self):
        """ Excute an anchor action """
        solenoid_switch = None
        if not relay.connected:
            relay.connect()
        if self.direction == 1:
            solenoid_switch = relay.anchor_dn_switch
        elif self.direction == -1:
            solenoid_switch = relay.anchor_up_switch
        log.debug(f'windlass.run_anchor direction={self.direction_msg()}')
        if self.direction == -1:
            log.debug(f'windlass.run_anchor up_speed={self.up_speed} m/min  up_speed_ms={self.up_speed_ms} m/sec')
        else:
            log.debug(f'windlass.run_anchor dn_speed={self.dn_speed} m/min  dn_speed_ms={self.dn_speed_ms} m/sec')

        if self.direction != 0:
            self.running = True
            solenoid_switch.on()
            prev_time_stamp = datetime.now()
            while not self.paused and not self.on_target():
                sleep(self.wait_secs)
                time_stamp = datetime.now()
                elapsed = time_stamp - prev_time_stamp
                elapsed_seconds = elapsed.seconds + elapsed.microseconds / 1_000_000
                if self.direction == -1:
                    self.actual_length -= self.up_speed_ms * elapsed_seconds
                elif self.direction == 1:
                    self.actual_length += self.dn_speed_ms * elapsed_seconds
                else:
                    log.error(f'windlass.run_to_target running with direction={self.direction}, paused')
                    self.paused = True
                prev_time_stamp = time_stamp
            solenoid_switch.off()
            self.actual_length = round(self.actual_length, 1)
            self.signal_completed = True
            log.debug(f'windlass.run_anchor set signal_completed to True')

        self.direction = 0
        self.running = False
        self.paused = True
        log.debug(f'on_target={self.on_target()}  {self.status_msg()}')

    def run_to_target(self):
        """ Run the windlass until the Actual chain length out is on the target length
            or the user instructs a pause, which will end the call. Call the method again to resume. """
        if not self.direction:
            log.warning(f'windlass.run_to_target direction was not set!')
            self.direction = self.run_direction()

        if self.on_target():
            log.debug(f'windlass.run_to_target on_target=True direction={self.direction_msg()}')
            self.running = False
            self.paused = True
            self.direction = 0
            self.reset_manual_run()
            if not self.signal_completed:
                self.signal_completed = True
                log.debug(f'windlass.run_to_target set signal_completed to True')
        else:
            log.debug(f'windlass.run_to_target on_target=False direction={self.direction_msg()}')
            self.run_anchor()

    def quit_listener(self):
        log.debug(f'windlass.quit_listener')
        self.quit = True

    def run_listener(self):
        """ Run an event loop until the quit flag is set.
            Use this method when running the class in a
            separate process and keep it alive. """
        log.debug(f'windlass.run_listener - started')
        while not self.quit:
            if not self.paused:
                if not self.on_target():
                    self.run_to_target()
                else:
                    self.paused = True
            sleep(self.wait_secs)
        relay.disconnect()
        log.debug(f'windlass.run_listener - finished')

from flask_wtf import FlaskForm
from wtforms import (HiddenField, SubmitField, StringField, FloatField, IntegerField, BooleanField,
                     RadioField, SelectField, DecimalRangeField)
from wtforms.validators import DataRequired, NumberRange, ValidationError
from ..app_logic.util import Glob, is_number


class ConfigAppForm(FlaskForm):
    """ Edit app configuration settings """
    pull_up_range = NumberRange(5, 15, 'Pull up until must be between 5 and 15 meter')
    manual_range = NumberRange(2, 10, 'Max manual range must be between 2 and 10 meter')
    id = HiddenField(label='AppConfig_ID')
    basic_mode = BooleanField('Basic mode')
    boat_id = RadioField('Boat name', coerce=int, default=1)
    allow_achor_up = BooleanField('Allow achor-up', default=True)
    min_length_up = IntegerField('Pull up until length (m)', default=5, validators=[DataRequired(), pull_up_range])
    max_manual_range = IntegerField('Max manual range (m)', default=5, validators=[DataRequired(), manual_range])
    tz_hour_adjust = IntegerField('Timezone hour adjustment', default=0, validators=[NumberRange(-24, 24)])
    cpu_temp_monitor = BooleanField('Monitor CPU temperature', default=False)
    cpu_temp_target = IntegerField('CPU temperature target', default=50)
    cpu_temp_high = IntegerField('CPU temperature high', default=60)
    submit = SubmitField('Save')

    def validate_cpu_temp_target(self, config_id):  # noqa
        temp_target = self.cpu_temp_target.data
        temp_high = self.cpu_temp_high.data
        if not temp_target:
            temp_target = 50
        delta = temp_high - temp_target if temp_high else 9999
        if temp_target < 45:
            raise ValidationError(f'CPU temperature target must be at least 45° Celcius')
        if delta < 5:
            raise ValidationError(f'CPU temperature target must be at least 5° below high ({temp_high})')

    def validate_cpu_temp_high(self, config_id):  # noqa
        temp_target = self.cpu_temp_target.data
        temp_high = self.cpu_temp_high.data
        if not temp_high:
            temp_high = 60
        delta = temp_high - temp_target if temp_target else 9999
        if temp_high < 50:
            raise ValidationError(f'CPU temperature high must be at least 50° Celcius')
        if delta < 5:
            raise ValidationError(f'CPU temperature high must be at least 5° above target ({temp_target})')


class ConfigBoatForm(FlaskForm):
    """ Edit boat configuration settings """
    boat_draught_range = NumberRange(1.0, 6, 'Draught (depth) must be between 1 and 6 meter')
    boat_length_range = NumberRange(0.0, 30, 'Length must be between 0 and 30 meter')
    id = HiddenField(label='BoatConfig_ID')
    boat_make = StringField('Boat type', validators=None)
    boat_name = StringField('Boat name', validators=None)
    boat_draught = FloatField('Boat draught (m)', validators=[DataRequired(), boat_draught_range])
    boat_length = FloatField('Boat length (m)', validators=[DataRequired(), boat_length_range])
    chain_length = IntegerField('Anchor chain length (m)', validators=[DataRequired()])
    down_speed = FloatField('Anchor down speed (m/min)', validators=[DataRequired()])
    up_speed = FloatField('Anchor up speed (m/min)', validators=[DataRequired()])
    submit = SubmitField('Save')

    def validate_chain_length(self, config_id):  # noqa
        chain_length = self.chain_length.data
        Glob.load_master_db_records()
        max_length = round(Glob.boat_config.boat_length * 6 + 10, -1)
        if chain_length < 30 or chain_length > max_length:
            raise ValidationError(f'Length must be between 30 and {max_length} meter')


class HomeForm(FlaskForm):
    """ Target and actual anchor chain length """
    target_length = IntegerField('Target length (m)', validators=None)
    actual_length = FloatField('Actual length (m)', validators=None)
    manual_range = DecimalRangeField('Range (m)', render_kw={'min': '0.5', 'max': '5', 'step': '0.5'})
    submit = SubmitField('Adjust')

    def validate_target_length(self, target_id):  # noqa
        if not Glob.boat_config.is_current:
            Glob.load_master_db_records()
        min_length = Glob.app_config.min_length_up
        max_length = Glob.boat_config.chain_length - Glob.app_config.min_length_up
        actual_length = self.actual_length.data
        target_length = self.target_length.data
        msg = f'Length must be between {min_length} and {max_length}m'
        if max_length is None:
            max_length = 50  # default
        if target_length is None:
            target_length = 0
        if not 0 <= target_length <= max_length:
            raise ValidationError(msg)
        elif actual_length > 0 and target_length < min_length:
            raise ValidationError(msg)

    def validate_actual_length(self, actual_id):  # noqa
        if not Glob.boat_config.is_current:
            Glob.load_master_db_records()
        max_length = Glob.boat_config.chain_length
        actual_length = self.actual_length.data
        if max_length is None:
            max_length = 50  # default
        if actual_length is None:
            actual_length = 0.0
        if actual_length < 0.0 or actual_length > max_length:
            raise ValidationError(f'Length must be between 0 and {max_length}m')


class TargetForm(FlaskForm):
    """ Set the target anchor chain length """
    anchor_depth = StringField('Depth (m)', default=None, validators=[DataRequired()])
    add_safety = BooleanField('Add safety', default=False)
    go_anchor_up = BooleanField('Go anchor up', default=False)
    exist_site_id = SelectField('Existing site', coerce=int)
    refname = StringField('New site', validators=None)  # render_kw={"placeholder": "new site name"}
    comment = StringField('Comment', validators=None)
    submit = SubmitField('Set')

    def validate_anchor_depth(self, depth_id):  # noqa
        anchor_depth_str = self.anchor_depth.data
        anchor_depth = float(anchor_depth_str) if is_number(anchor_depth_str) else 0.0
        if not Glob.boat_config.is_current:
            Glob.load_master_db_records()
        min_anchor_depth = Glob.boat_config.min_anchor_depth()
        max_anchor_depth = Glob.boat_config.max_anchor_depth()
        if anchor_depth < min_anchor_depth or anchor_depth > max_anchor_depth:
            raise ValidationError(f'Depth must be between {min_anchor_depth} and {max_anchor_depth} meter')

    def validate_refname(self, name_id):  # noqa
        if self.refname.data and self.exist_site_id.data >= 0:
            raise ValidationError(f'Select <new site> or <edit site> for "Existing site" please')


class SiteSelectForm(FlaskForm):
    """ Select the anchor site """
    site_id = SelectField('Site', coerce=int)
    submit = SubmitField('Select')

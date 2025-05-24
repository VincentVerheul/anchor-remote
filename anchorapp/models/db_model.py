from enum import Enum
from .. import db
from datetime import datetime
from sqlalchemy import select, func


class DbInfo:
    """ Use as mixin with db.Model """
    @property
    def has_db_identity(self) -> bool:
        """ Return SQLAlchemy instance info: object has a (db) identity """
        return self.__dict__['_sa_instance_state'].has_identity

    @property
    def has_db_session(self) -> bool:
        """ Return SQLAlchemy instance info: object has a (db) session """
        return self.__dict__['_sa_instance_state'].session is not None

    @property
    def is_current(self) -> bool:
        """ Database current: The record has been retrieved after the last update (commit) to the database """
        return (self.__dict__['_sa_instance_state'].has_identity and
                self.__dict__['_sa_instance_state'].session is not None)

    def class_tbl_name(self):
        """ Derive the table name from the class name """
        cls_name = type(self).__name__
        tbl_name_chars = list()
        prev_ch = ''
        for ch in cls_name:
            if prev_ch.islower() and ch.isupper():
                tbl_name_chars.append('_')
            tbl_name_chars.append(ch.lower())
            prev_ch = ch
        tbl_name = ''.join(tbl_name_chars)
        return tbl_name

    @staticmethod
    def run_select(select_statement) -> list:
        """ Read table from the database based on select statement and return contents as a list of dicts """
        data = list()
        with db.engine.connect() as conn:
            for row in conn.execute(select_statement):
                data.append(dict(row._mapping))  # noqa
        return data

    def get_last(self):
        """ Get the record with the highest id (or return None when no records in the table) """
        tbl = db.metadata.tables[self.class_tbl_name()]
        data = self.run_select(select(func.max(tbl.c.id).label('max_id')))
        last_id = data[0]['max_id'] if data else None
        return self.query.get(last_id)   # noqa


class ConfigApp(db.Model, DbInfo):
    """ Application configuration parameters """
    id = db.Column(db.Integer, primary_key=True, default=1)
    time_stamp = db.Column(db.DateTime, nullable=False, default=datetime.now, comment='Last updated')
    basic_mode = db.Column(db.Boolean, default=False, comment='Anchor control basic mode')
    boat_id = db.Column(db.Integer, db.ForeignKey('config_boat.id'), comment='Selected boat')
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), comment='Last used site')
    min_length_up = db.Column(db.Integer, nullable=False, default=5, comment='Min chain length in meters, going up')
    allow_achor_up = db.Column(db.Boolean, default=True, comment='Allow anchor-up (may not be safe)')
    manual_range = db.Column(db.Float, nullable=False, default=0.5, comment='Manual up / down range in meters')
    max_manual_range = db.Column(db.Integer, nullable=False, default=5, comment='Max manual up / down range in meters')
    tz_hour_adjust = db.Column(db.Integer, nullable=False, default=0, comment='Timezone hour adjustment')
    cpu_temp_target = db.Column(db.Integer, default=50, comment='CPU temperature Celcius target to cool down to')
    cpu_temp_high = db.Column(db.Integer, default=60, comment='CPU temperature Celcius to trigger the fan')

    def __repr__(self):
        return f"ConfigApp(id={self.id}, boat_id={self.boat_id})"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class ConfigBoat(db.Model, DbInfo):
    """ Boat configuration parameters """
    id = db.Column(db.Integer, primary_key=True)
    created_on = db.Column(db.DateTime, nullable=False, default=datetime.now, comment='Date created')
    time_stamp = db.Column(db.DateTime, nullable=False, default=datetime.now, comment='Last updated')
    boat_make = db.Column(db.String(80), nullable=True, comment='For example: Jeanneau Sun Odyssey 349')
    boat_name = db.Column(db.String(80), nullable=True)
    boat_draught = db.Column(db.Float, nullable=False, default=2.0, comment='Boat draught (depth) in meters')
    boat_length = db.Column(db.Float, nullable=False, default=10.0, comment='Boat length in meters')
    chain_length = db.Column(db.Integer, nullable=False, default=50, comment='Chain length in meters')
    down_speed = db.Column(db.Float, nullable=False, default=10.0, comment='Anchor down speed meter / minute')
    up_speed = db.Column(db.Float, nullable=False, default=8.0, comment='Anchor up speed meter / minute')
    # relationships
    events = db.relationship('SiteEvent', back_populates='boat', lazy=True)

    def __repr__(self):
        return f"ConfigBoat({self.id}, '{self.boat_name}')"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def deploy_length(self, depth: int, use_safety=False, min_length_remain=5) -> float:
        """ Calculate the chain length to deploy. use_safety will add one boat length.
            min_length_remain to protect against the chain exiting the gypsy. """
        safety_factor = 2 if use_safety else 1
        length = self.boat_length * safety_factor + depth * 2
        if length > self.chain_length - min_length_remain:
            length = self.chain_length - min_length_remain
        return round(length, 0)

    def min_anchor_depth(self):
        """ Calculate the min anchor depth from the boat draught """
        return int(self.boat_draught) + 1 if self.boat_draught else 5

    def max_anchor_depth(self, min_length_remain=5) -> int:
        """ Calculate the max anchor depth from the chain length """
        return int(round((self.chain_length - min_length_remain - self.boat_length) / 2, 0))


class User(db.Model, DbInfo):
    """ Application user """
    id = db.Column(db.Integer, primary_key=True)
    time_stamp = db.Column(db.DateTime, nullable=False, default=datetime.now, comment='Last updated')
    user_ip = db.Column(db.String(20), unique=True, nullable=False, comment='User IP address')
    username = db.Column(db.String(30), unique=True, comment='User (nick) name')

    def __repr__(self):
        return f"User({self.id}, '{self.username}')"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class Site(db.Model, DbInfo):
    """ Anchor site, to relate arrival and leave events """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), default=0, nullable=False)
    time_stamp = db.Column(db.DateTime, nullable=False, default=datetime.now)
    refname = db.Column(db.String(80), nullable=False)
    comment = db.Column(db.Text, nullable=True)
    anchor_depth = db.Column(db.Integer, nullable=True)
    add_safety = db.Column(db.Boolean, default=False)
    actual_length = db.Column(db.Float, nullable=True)
    # relationships
    events = db.relationship('SiteEvent', back_populates='site', lazy=True)

    def __repr__(self):
        return f"Site(id={self.id}, name='{self.refname}')"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class Action(Enum):
    """ Enumerated event - action codes """
    UNDEFINED = 0
    CONFIG = 1
    BOAT_SETTINGS = 2
    INITIAL_VALUE = 10
    ADJUST_TARGET = 11
    ADJUST_ACTUAL = 12
    SET_MAN_RANGE = 13
    PAUSE = 15
    SET_TARGET = 20
    DOWN_TO_TARGET = 21
    UP_TO_TARGET = 22
    TARGET_REACHED = 25
    DOWN_MANUAL = 31
    UP_MANUAL = 32
    TAKE_CONTROL = 90
    QUIT = 99

    def is_anchor_run(self, target_run=True, manual_run=True) -> bool:
        """ Action represents an Anchor run, i.e. actual deployed length is changing """
        result = False
        if target_run:
            result = result or self.value in (21, 22)
        if manual_run:
            result = result or self.value in (31, 32)
        return result

    @property
    def is_length_relevant(self) -> bool:
        """ Action is relevant to report with a length """
        return self.value not in (0, 1, 2, 90, 99)


class SiteEvent(db.Model, DbInfo):
    """ Log of events related to a site """
    id = db.Column(db.Integer, primary_key=True)
    boat_id = db.Column(db.Integer, db.ForeignKey('config_boat.id'), comment='Reference to boat')
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), default=0, nullable=False)
    action = db.Column(db.Integer, default=0, comment='Numerical value of event Action')
    start_time = db.Column(db.DateTime, default=datetime.now)
    end_time = db.Column(db.DateTime, default=datetime.now)
    target_length = db.Column(db.Float, comment='Target chain deployed length at start of action')
    start_actual_length = db.Column(db.Float, comment='Actual chain deployed length at start of action')
    end_actual_length = db.Column(db.Float, comment='Actual chain deployed length at end of action')
    # relationships
    boat = db.relationship('ConfigBoat', back_populates='events', lazy=True)
    site = db.relationship('Site', back_populates='events', lazy=True)

    def __repr__(self):
        return f"SiteEvent(id={self.id}, site_id={self.site_id}, action={Action(self.action).name})"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


def create_database():
    """ (re) create database - deletes existing data! """
    #  db.drop_all()
    db.create_all()

#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime
from pony.orm import *

botDB = Database()
class Chat(botDB.Entity):
    primary_id = PrimaryKey(int, auto=True)

    # Telegram info
    chat_id = Required(int, size=64, unique=True)
    user_id = Required(int)
    username = Optional(str)
    first_name = Optional(str)
    last_name = Optional(str)

    # datetimes
    open_date = Required(datetime)
    last_message_date = Optional(datetime)

    # Parameters
    silent_mode = Required(bool)
    deleted = Required(bool)
    group_id = Optional(str)
    realname = Optional(str)

    # State
    state = Required(str)

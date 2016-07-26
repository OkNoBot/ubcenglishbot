#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import telegram
import sys
from pyslack import SlackClient
import json
import argparse
import time
import timepad
import os
import traceback
import urllib3
urllib3.disable_warnings()
import itertools
from datetime import datetime
from pony.orm import db_session, select
from db import granumDB, Chat


LAST_UPDATE_ID = None
MESSAGE_START = 'Добро пожаловать! Я бот UBC English. Пожалуйста, введите "I am ...", где "..." -- выданное Вам кодовое слово, чтобы я понял, из какой Вы группы.'
MESSAGE_STOP = "Я умолкаю в этом чате! Наберите /start, чтобы вновь подписаться на рассылку анонсов."
MESSAGE_HELP = "/homework -- прислать домашнее задание\n/schedule -- прислать расписание\n/results -- прислать результат тестирования\n/teacher -- чат с учителем\n/group_chat -- чат с одногруппниками\n/news -- прислать последние новости"
MESSAGE_START = "{}\nДоступные команды:\n{}".format(MESSAGE_START, MESSAGE_HELP)
KEYBOARD = '{"keyboard" : [["/homework", "/schedule", "/results"], ["/teacher", "/group_chat", "/news"]], "resize_keyboard" : true}'
KEYBOARD_ADMIN = '{"keyboard" : [["/homework", "/schedule", "/results"], ["/teacher", "/group_chat", "/news"], ["/user_list", "/google_sheet", "/send"]], "resize_keyboard" : true}'
MESSAGE_HELP_ADMIN = MESSAGE_HELP + "\n/user_list - list of user\n/google_sheet - get google sheed link\n/send - send message to different users"
#MESSAGE_HELP_ADMIN = MESSAGE_HELP + "\n/user_list - list of user\n/google_sheet - get google sheed link\n/send_broad <message> - send message to all users\n/send <user_id> <message> - send <message> to <user_id>"
MESSAGE_ALARM = "Аларм! Аларм!"
CHAT_ID_ALARM = 79031498
BOT_ID = 136777319
GROUP1_CHAT_LINK = 'Нажмите, чтобы добавиться в групповой чат: https://telegram.me/joinchat/BLXsyj9Qyw345JsKEVBFNQ'
GROUP2_CHAT_LINK = 'Нажмите, чтобы добавиться в групповой чат: https://telegram.me/joinchat/BLXsyj95-Y2APYkG70_l7A'
PROMO_MESSAGE = 'Человек, вот твой промокод: promo_{}_{}\n\nИспользуй его при заказе билета на любое из предстоящих мероприятий, чтобы получить скидку в 150 рублей (по отношению к самому дешевому билету). Срок действия промокода неограничен, но доступен он станет не сразу. Я оповещу тебя, когда он начнёт действовать.'
NEWS_TEXT = "Пока новостей нет..."
TEACHER_TEXT = "Ваш учитель: @christina19"
RESULTS_TEXT = "Пока результатов нет"
HOMEWORK_TEXT = "Пока домашнего задания нет"
REGISTER_TEXT = 'Пожалуйста, введите "I am ...", где "..." -- выданное Вам кодовое слово, чтобы я понял, из какой Вы группы.'
HOMEWORK_CMD = '/homework'
SCHEDULE_CMD = '/schedule'
RESULTS_CMD = '/results'
GROUP_CHAT_CMD = '/group_chat'
TEACHER_CMD = '/teacher'
NEWS_CMD = '/news'
#SEND_BROAD_CMD = '/send_broad'
SEND_MSG_CMD = '/send'
START_CMD = '/start'
STOP_CMD = '/stop'
SECRET_LIST_CMD = '/secret_list'
USER_LIST_CMD = '/user_list'
GOOGLE_SHEET_CMD = '/google_sheet'
GOOGLE_SHEET = 'https://docs.google.com/spreadsheets/d/1HfJqGuRlTJB0yL3WRodMlRKX7kZoE7MyqLV6Wdk1AFE'
HELLO_CMD = '/hello'
HELP_CMD = '/help'
NEXT_CMD = '/next'
GROUP_CHAT_CMD = '/group_chat'
PROMO_CMD = '/promo'
IAM_CMD = "I am "
TELEGRAM_MSG_CHANNEL = '#telegram-messages'


def main():
    global LAST_UPDATE_ID

    parser = argparse.ArgumentParser(description="Telegram bot for GranumSalis")
    parser.add_argument("--logfile", type=str, default='log', help="Path to log file")
    parser.add_argument("--dbfile", type=str, default='ubcenglish.sqlite', help="Path to sqlite DB file")
    args = parser.parse_args()

    granumDB.bind('sqlite', args.dbfile, create_db=True)
    granumDB.generate_mapping(create_tables=True)

    with open('.admin_ids') as f:
        admin_ids = f.read().splitlines() 
    if admin_ids == None:
        admin_ids = list()

    # TODO: use it
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    telegram_token = open('.telegram_token').readline().strip()
    slack_token = open('.slack_token').readline().strip()
    bot = telegram.Bot(telegram_token)
    slackbot = SlackClient(slack_token)

    try:
        LAST_UPDATE_ID = bot.getUpdates()[-1].update_id
    except IndexError:
        LAST_UPDATE_ID = None

    while True:
        try:
            run(bot, args.logfile, slackbot)
        except telegram.TelegramError as error:
            print "TelegramError", error
            time.sleep(1)
        #except urllib2.URLError as error:
        #    print "URLError", error
        #    time.sleep(1)
        except:
            traceback.print_exc()
            try:
                bot.sendMessage(chat_id=CHAT_ID_ALARM, text=MESSAGE_ALARM)
            except:
                pass
            time.sleep(100) # 100 seconds


def log_update(update, logfile, slackbot, primary_id):
    message = update.message
    slack_text = u'{} {} ({}, GSid: {}): {{}}\n'.format(message.from_user.first_name,
                                                        message.from_user.last_name,
                                                        message.from_user.name,
                                                        primary_id)
    if message.left_chat_member:
        slack_text = slack_text.format('left bot chat')
    elif message.new_chat_member:
        slack_text = slack_text.format('joined bot chat')
    else:
        slack_text = slack_text.format(message.text)
    log_text = update.to_json().decode('unicode-escape').encode('utf-8') + '\n'

    slackbot.chat_post_message(TELEGRAM_MSG_CHANNEL, slack_text, as_user=True)
    with open(logfile, 'a') as log:
        log.write(log_text)


def update_chat_db(message):
    with db_session:
        chat = Chat.get(chat_id=message.chat.id)
        if chat == None:
            chat = Chat(chat_id=message.chat.id, user_id=message.from_user.id, open_date=datetime.now(), \
                            last_message_date=datetime.now(), username=message.from_user.username, \
                            first_name=message.from_user.first_name, last_name=message.from_user.last_name, \
                            silent_mode=False, deleted=False, group_id="nobody", state="MAIN_STATE")
        else:
            chat.last_message_date = datetime.now()
            chat.username = message.from_user.username
            chat.first_name = message.from_user.first_name
            chat.last_name = message.from_user.last_name


        if chat.state == "MAIN_STATE":
            if message.text == STOP_CMD:
                chat.silent_mode = True
            elif message.left_chat_member != None:
                if message.left_chat_member.id == BOT_ID:
                    chat.deleted = True
            elif message.new_chat_member != None:
                if message.new_chat_member.id == BOT_ID:
                    chat.deleted = False
            elif message.text == START_CMD:
                chat.silent_mode = False
                chat.deleted = False
            elif message.text.startswith(IAM_CMD):
                password = message.text[len(IAM_CMD):]
                group_id = "nobody"
                if password == "umbrella":
                    group_id = "group1"
                if password == "butterfly":
                    group_id = "group2"
                if password == "god":
                    group_id = "teacher"
                if password == "boss":
                    group_id = "admin"
                chat.group_id = group_id
            elif message.text == "/send":
                if chat.group_id == "admin" or chat.group_id == "teacher":
                    chat.state = "SEND_STATE"

        elif chat.state.startswith("SEND_STATE"):
            if "confirm" in chat.state or "cancel" in chat.state:
                chat.state = "MAIN_STATE"
            elif message.text == "/cancel":
                chat.state += " cancel"
            elif message.text == "/group1":
                chat.state += " group1"
            elif message.text == "/group2":
                chat.state += " group2"
            elif message.text == "/all":
                chat.state += " all"
            elif message.text == "/news":
                chat.state += " news"
            elif message.text == "/homework":
                chat.state += " homework"
            elif message.text == "/confirm":
                chat.state += " confirm"
            elif len(chat.state.split()) == 3: # State waiting for message to confirm
                chat.state += " " + str(message.message_id)

        return chat.primary_id, chat.silent_mode, chat.group_id, chat.state


def send_broad(bot, text, group):
    with db_session:
        for chat in select(chat for chat in Chat if not (chat.silent_mode or chat.deleted) and \
                           (chat.group_id == group or group == "all")):
            try:
                #is_admin = 
                #reply_markup = KEYBOARD_ADMIN if is_admin else KEYBOARD
                bot.sendMessage(chat_id=chat.chat_id, text=text)#, reply_markup=reply_markup)
            except telegram.TelegramError as error:
                print "TelegramError", error


def forward_broad(bot, from_chat_id, message_id, group):
    with db_session:
        for chat in select(chat for chat in Chat if not (chat.silent_mode or chat.deleted) and \
                           (chat.group_id == group or group == "all")):
            try:
                #is_admin = 
                #reply_markup = KEYBOARD_ADMIN if is_admin else KEYBOARD
                #bot.sendMessage(chat_id=chat.chat_id, text=text)#, reply_markup=reply_markup)
                bot.forwardMessage(chat_id=chat.chat_id, from_chat_id=from_chat_id, message_id=message_id)
            except telegram.TelegramError as error:
                print "TelegramError", error


def send_large_message(bot, chat_id, text):
    MAX_LINES = 100

    def grouper(iterable, n, fillvalue=None):
        "Collect data into fixed-length chunks or blocks"
        # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx
        args = [iter(iterable)] * n
        return itertools.izip_longest(fillvalue=fillvalue, *args)

    lines = text.splitlines()
    for block in grouper(lines, MAX_LINES, ''):
        bot.sendMessage(chat_id=chat_id, text='\n'.join(block))


def print_userlist(bot, message):
    with db_session:
        chats_str = ''
        for chat in select(chat for chat in Chat):
            chats_str += u'{}. {} {} (@{}, {})'.format(chat.primary_id, chat.first_name, chat.last_name, \
                                                     chat.username, chat.group_id)
            if chat.silent_mode:
                chats_str += ' (silent mode)'
            if chat.deleted:
                chats_str += ' (deleted)'
            chats_str += '\n'

        try:
            send_large_message(bot, message.chat_id, chats_str)
        except telegram.TelegramError as error:
            print "TelegramError", error


        group1_str = 'Group 1:\n'
        for chat in select(chat for chat in Chat if chat.group_id == "group1"):
            group1_str += u'{}. {} {} (@{})'.format(chat.primary_id, chat.first_name, chat.last_name, \
                                                     chat.username)
            if chat.silent_mode:
                group1_str += ' (silent mode)'
            if chat.deleted:
                group1_str += ' (deleted)'
            group1_str += '\n'

        try:
            send_large_message(bot, message.chat_id, group1_str)
        except telegram.TelegramError as error:
            print "TelegramError", error


        group2_str = 'Group 2:\n'
        for chat in select(chat for chat in Chat if chat.group_id == "group2"):
            group2_str += u'{}. {} {} (@{})'.format(chat.primary_id, chat.first_name, chat.last_name, \
                                                     chat.username)
            if chat.silent_mode:
                group2_str += ' (silent mode)'
            if chat.deleted:
                group2_str += ' (deleted)'
            group2_str += '\n'

        try:
            send_large_message(bot, message.chat_id, group2_str)
        except telegram.TelegramError as error:
            print "TelegramError", error



def send_message(bot, message):
    with db_session:
        cmd = text = ''
        primary_id = 0
        params = message.text.split(' ', 2)
        if len(params) > 0:
            cmd = params[0]
        if len(params) > 1:
            try:
                primary_id = int(params[1])
            except ValueError:
                bot.sendMessage(chat_id=message.chat_id, text='cannot find user')
                return False
        if len(params) > 2:
            text = params[2]
        if primary_id == 0:
            bot.sendMessage(chat_id=message.chat_id, text='cannot send message to empty user')
        elif len(text) == 0:
            bot.sendMessage(chat_id=message.chat_id, text='cannot send empty message')
        else:
            chat = Chat.get(primary_id=primary_id)
            if chat == None:
                bot.sendMessage(chat_id=message.chat_id, text='cannot find user')
            elif chat.deleted:
                bot.sendMessage(chat_id=message.chat_id, text='this user marked as deleted')
            else:
                bot.sendMessage(chat_id=chat.chat_id, text=text)


def get_schedule_message():
    DOC = "{}/export?format=tsv&id={}&gid={}".format(GOOGLE_SHEET, '1eBh9w0WRRJleBQd7eVHFKBQgc5V_w0TYymMkKHL6598', '1758330787')
    CMD = "curl -s '{}' | sed -e 's/[[:space:]]$//g' | awk 'NF > 1 {{print }}'".format(DOC)
    return os.popen(CMD).read()


def get_news_message():
    DOC = "{}/export?format=tsv&id={}&gid={}".format(GOOGLE_SHEET, '1eBh9w0WRRJleBQd7eVHFKBQgc5V_w0TYymMkKHL6598', '1907552920')
    CMD = "curl -s '{}' | tail -1".format(DOC)
    return os.popen(CMD).read()


def run(bot, logfile, slackbot):
    global LAST_UPDATE_ID
    for update in bot.getUpdates(offset=LAST_UPDATE_ID, timeout=10):
        message = update.message
        primary_id, silent_mode, group_id, state = update_chat_db(message)
        log_update(update, logfile, slackbot, primary_id)

        if group_id == "nobody":
            bot.sendMessage(chat_id=message.chat_id, text=REGISTER_TEXT)

            LAST_UPDATE_ID = update.update_id + 1
            continue

        is_admin = (group_id == "admin")
        is_teacher = (group_id == 'teacher')
        if is_teacher:
            is_admin = is_teacher

        reply_markup = KEYBOARD_ADMIN if (is_admin or is_teacher) else KEYBOARD
        if not silent_mode:
            reply_markup = reply_markup.replace(START_CMD, STOP_CMD)

        if state.startswith("SEND_STATE"):
            if state.endswith("cancel"):
                bot.sendMessage(chat_id=message.chat_id, text="Рассылка отменена", reply_markup=reply_markup)

            if len(state.split()) == 1:
                reply_markup = '{"keyboard" : [["/news", "/homework", "/cancel"]], "resize_keyboard" : true}'
                bot.sendMessage(chat_id=message.chat_id, text="Отослать новость (/news) или домашнее задание (/homework)?", reply_markup=reply_markup)
            elif len(state.split()) == 2:
                reply_markup = '{"keyboard" : [["/group1", "/group2", "/all", "/cancel"]], "resize_keyboard" : true}'
                bot.sendMessage(chat_id=message.chat_id, text="Выберите группу для рассылки:", reply_markup=reply_markup)
            elif len(state.split()) == 3:
                reply_markup = '{"keyboard" : [["/cancel"]], "resize_keyboard" : true}'
                bot.sendMessage(chat_id=message.chat_id, text="Напишите сообщение для рассылки (или файл/картинку):", reply_markup=reply_markup)
            elif len(state.split()) == 4:
                reply_markup = '{"keyboard" : [["/confirm", "/cancel"]], "resize_keyboard" : true}'
                bot.sendMessage(chat_id=message.chat_id, text="Подтвердите отправку (/confirm):", reply_markup=reply_markup)
            elif len(state.split()) == 5:
                _, _, group, message_id, _ = state.split()
                forward_broad(bot, from_chat_id=message.chat_id, message_id=message_id, group=group)
                bot.sendMessage(chat_id=message.chat_id, text="Отправлено!", reply_markup=reply_markup)

        if state == "MAIN_STATE":
            if message.left_chat_member:
                pass
            elif message.text == HELP_CMD:
                    bot.sendMessage(chat_id=message.chat_id, \
                                    text=MESSAGE_HELP_ADMIN if is_admin else MESSAGE_HELP)
            elif message.text == START_CMD:
                bot.sendMessage(chat_id=message.chat_id, text=MESSAGE_START, reply_markup=reply_markup)
            elif message.text == STOP_CMD:
                bot.sendMessage(chat_id=message.chat_id, text=MESSAGE_STOP, reply_markup=reply_markup)
            elif message.text.startswith(IAM_CMD):
                if group_id == "admin":
                    bot.sendMessage(chat_id=message.chat_id, text="Вы администратор!", reply_markup=reply_markup)
                elif group_id == "teacher":
                    bot.sendMessage(chat_id=message.chat_id, text="Вы учитель!", reply_markup=reply_markup)
                elif group_id == "group1":
                    bot.sendMessage(chat_id=message.chat_id, text="Спасибо, вы в группе 1!", reply_markup=reply_markup)
                elif group_id == "group2":
                    bot.sendMessage(chat_id=message.chat_id, text="Спасибо, вы в группе 2!", reply_markup=reply_markup)
            elif message.text == GROUP_CHAT_CMD:
                if group_id == 'group1':
                    bot.sendMessage(chat_id=message.chat_id, text=GROUP1_CHAT_LINK, reply_markup=reply_markup)
                elif group_id == 'group2':
                    bot.sendMessage(chat_id=message.chat_id, text=GROUP2_CHAT_LINK, reply_markup=reply_markup)
                elif group_id == 'admin' or group_id == 'teacher':
                    bot.sendMessage(chat_id=message.chat_id, text=GROUP1_CHAT_LINK, reply_markup=reply_markup)
                    bot.sendMessage(chat_id=message.chat_id, text=GROUP2_CHAT_LINK, reply_markup=reply_markup)
            elif message.text == NEWS_CMD:
                news_message = get_news_message()
                bot.sendMessage(chat_id=message.chat_id, text=news_message, reply_markup=reply_markup)
            elif message.text == TEACHER_CMD:
                bot.sendMessage(chat_id=message.chat_id, text=TEACHER_TEXT, reply_markup=reply_markup)
            elif message.text == HOMEWORK_CMD:
                bot.sendMessage(chat_id=message.chat_id, text=HOMEWORK_TEXT, reply_markup=reply_markup)
            elif message.text == RESULTS_CMD:
                bot.sendMessage(chat_id=message.chat_id, text=RESULTS_TEXT, reply_markup=reply_markup)
            elif message.text.lower() == SCHEDULE_CMD:
                if group_id == "group1":
                    bot.sendMessage(chat_id=message.chat_id, text="Среда, с 18:00 до 19:30", reply_markup=reply_markup)
                elif group_id == "group2":
                    bot.sendMessage(chat_id=message.chat_id, text="Среда, с 19:30 до 20:00", reply_markup=reply_markup)
                else:
                    schedule_message = get_schedule_message()
                    bot.sendMessage(chat_id=message.chat_id, text=schedule_message, reply_markup=reply_markup)
            #elif is_admin and message.text.startswith(SEND_BROAD_CMD):
            #    send_broad(bot, message.text[len(SEND_BROAD_CMD) + 1:], admin_list)
            #elif is_admin and message.text.startswith(SEND_MSG_CMD):
            #    send_message(bot, message)
            elif is_admin and message.text == USER_LIST_CMD:
                print_userlist(bot, message)
            elif is_admin and message.text == GOOGLE_SHEET_CMD:
                bot.sendMessage(chat_id=message.chat_id, text='Your google sheet: {}'.format(GOOGLE_SHEET), reply_markup=reply_markup)
            else:
                pass
            
        LAST_UPDATE_ID = update.update_id + 1


if __name__ == '__main__':
    main()

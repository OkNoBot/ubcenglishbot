#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import telegram
import sys
from pyslack import SlackClient
import json
import argparse
import time
import os
import traceback
import certifi
import urllib3
import itertools
from datetime import datetime
from pony.orm import db_session, select
from db import botDB, Chat


LAST_UPDATE_ID = None
BOT_DESCRIPTION = "Telegram bot for English courses"
MESSAGE_START = 'Добро пожаловать! Я бот UBC English. Пожалуйста, введите "I am ...", где "..." -- выданное Вам кодовое слово, чтобы я понял, из какой Вы группы.'
MESSAGE_STOP = "Я умолкаю в этом чате! Наберите /start, чтобы вновь подписаться на рассылку анонсов."
MESSAGE_HELP = "/homework -- прислать домашнее задание\n/schedule -- прислать расписание\n/results -- прислать результат тестирования\n/teacher -- чат с учителем\n/group_chat -- чат с одногруппниками\n/news -- прислать последние новости"
MESSAGE_START = "{}\nДоступные команды:\n{}".format(MESSAGE_START, MESSAGE_HELP)
MAIN_KEYBOARD = '{"keyboard" : [["/homework", "/schedule", "/results"], ["/teacher", "/group_chat", "/news"]], "resize_keyboard" : true}'
MAIN_KEYBOARD_ADMIN = '{"keyboard" : [["/homework", "/schedule", "/results"], ["/teacher", "/group_chat", "/news"], ["/user_list", "/google_sheet", "/send"]], "resize_keyboard" : true}'
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
REGISTER_TEXT = 'Пожалуйста, введите выданное Вам кодовое слово, чтобы я понял, из какой Вы группы:'
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
TELEGRAM_MSG_CHANNEL = '#telegram-messages'



def main():
    global LAST_UPDATE_ID

    parser = argparse.ArgumentParser(description=BOT_DESCRIPTION)
    parser.add_argument("--logfile", type=str, default='log', help="Path to log file")
    parser.add_argument("--dbfile", type=str, default='ubcenglish.sqlite', help="Path to sqlite DB file")
    args = parser.parse_args()

    botDB.bind('sqlite', args.dbfile, create_db=True)
    botDB.generate_mapping(create_tables=True)

    # TODO: use it
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    http = urllib3.PoolManager(cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())

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
                        silent_mode=False, deleted=False, group_id="nobody", state="REGISTER_STATE", \
                        realname="")
        else:
            chat.last_message_date = datetime.now()
            chat.username = message.from_user.username
            chat.first_name = message.from_user.first_name
            chat.last_name = message.from_user.last_name

        return chat


def send_broad(bot, text, group):
    with db_session:
        for chat in select(chat for chat in Chat if not (chat.silent_mode or chat.deleted) and \
                           (chat.group_id == group or group == "all")):
            try:
                #is_admin = 
                #reply_markup = MAIN_KEYBOARD_ADMIN if is_admin else MAIN_KEYBOARD
                bot.sendMessage(chat_id=chat.chat_id, text=text)#, reply_markup=reply_markup)
            except telegram.TelegramError as error:
                print "TelegramError", error


def forward_broad(bot, from_chat_id, message_id, group):
    with db_session:
        for chat in select(chat for chat in Chat if not (chat.silent_mode or chat.deleted) and \
                           (chat.group_id == group or group == "all")):
            try:
                #is_admin = 
                #reply_markup = MAIN_KEYBOARD_ADMIN if is_admin else MAIN_KEYBOARD
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
            chats_str += u'{}. {} (@{}, {})'.format(chat.primary_id, chat.realname, \
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
            group1_str += u'{}. {} (@{})'.format(chat.primary_id, chat.realname, chat.username)

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
            group2_str += u'{}. {} (@{})'.format(chat.primary_id, chat.realname, chat.username)

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

        chat = update_chat_db(message)
        primary_id, group_id, state, silent_mode, deleted, realname = \
            chat.primary_id, chat.group_id, chat.state, chat.silent_mode, chat.deleted, chat.realname

        log_update(update, logfile, slackbot, primary_id)

        #automata_step(message, chat)

        reply_markup = MAIN_KEYBOARD_ADMIN if ((group_id == "admin") or (group_id == 'teacher')) else MAIN_KEYBOARD

        print(u"State: {}. Message: {}".format(state, message.text))

        if state.startswith("REGISTER_STATE"):
            if len(state.split()) == 1:
                reply_markup = '{"keyboard" : [["/confirm"]], "resize_keyboard" : true, "one_time_keyboard" : true}'
                realname = u"{} {}".format(message.from_user.first_name, message.from_user.last_name)
                text = u"Ваше имя и фамилия в Телеграме: {}. Подтвердите его (/confirm) или введите Вашe имя и фамилию для использования в этом боте:".format(realname)
                bot.sendMessage(chat_id=message.chat_id, text=text, reply_markup=reply_markup)
                state = "REGISTER_STATE password"
            elif len(state.split()) == 2:
                if message.text != "/confirm":
                    realname = message.text
                bot.sendMessage(chat_id=message.chat_id, text=u"Ваше имя: {}".format(realname), reply_markup=telegram.ReplyKeyboardHide())

                bot.sendMessage(chat_id=message.chat_id, text=REGISTER_TEXT)
                state = "REGISTER_STATE password realname"
            elif len(state.split()) == 3:
                password = message.text
                if password == "umbrella":
                    group_id = "group1"
                    bot.sendMessage(chat_id=message.chat_id, text="Спасибо, вы в группе 1!", reply_markup=MAIN_KEYBOARD)
                    state = "MAIN_STATE"
                elif password == "butterfly":
                    group_id = "group2"
                    bot.sendMessage(chat_id=message.chat_id, text="Спасибо, вы в группе 2!", reply_markup=MAIN_KEYBOARD)
                    state = "MAIN_STATE"
                elif password == "god":
                    group_id = "teacher"
                    bot.sendMessage(chat_id=message.chat_id, text="Вы учитель!", reply_markup=MAIN_KEYBOARD_ADMIN)
                    state = "MAIN_STATE"
                elif password == "boss":
                    group_id = "admin"
                    bot.sendMessage(chat_id=message.chat_id, text="Вы администратор!", reply_markup=MAIN_KEYBOARD_ADMIN)
                    state = "MAIN_STATE"
                else:
                    bot.sendMessage(chat_id=message.chat_id, text="Кодовое слово мне неизвестно :(")
                    bot.sendMessage(chat_id=message.chat_id, text=REGISTER_TEXT)

        elif state == "MAIN_STATE":
            if message.left_chat_member != None:
                if message.left_chat_member.id == BOT_ID:
                    deleted = True
            elif message.new_chat_member != None:
                if message.new_chat_member.id == BOT_ID:
                    deleted = False
            elif message.text == HELP_CMD:
                    bot.sendMessage(chat_id=message.chat_id, \
                                    text=MESSAGE_HELP_ADMIN if ((group_id == "admin") or (group_id == 'teacher')) else MESSAGE_HELP)
            elif message.text == START_CMD:
                silent_mode = False
                deleted = False
                bot.sendMessage(chat_id=message.chat_id, text=MESSAGE_START, reply_markup=reply_markup)
            elif message.text == STOP_CMD:
                silent_mode = True
                bot.sendMessage(chat_id=message.chat_id, text=MESSAGE_STOP, reply_markup=reply_markup)
            elif message.text == GROUP_CHAT_CMD:
                if group_id == 'group1':
                    bot.sendMessage(chat_id=message.chat_id, text=GROUP1_CHAT_LINK, reply_markup=reply_markup)
                elif group_id == 'group2':
                    bot.sendMessage(chat_id=message.chat_id, text=GROUP2_CHAT_LINK, reply_markup=reply_markup)
                elif group_id == 'admin' or group_id == 'teacher':
                    bot.sendMessage(chat_id=message.chat_id, text=GROUP1_CHAT_LINK, reply_markup=reply_markup)
                    bot.sendMessage(chat_id=message.chat_id, text=GROUP2_CHAT_LINK, reply_markup=reply_markup)
            elif message.text == NEWS_CMD:
                #news_message = get_news_message()
                #bot.sendMessage(chat_id=message.chat_id, text=news_message, reply_markup=reply_markup)
                bot.forwardMessage(chat_id=message.chat_id, from_chat_id=237288447, message_id=1468)
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
            elif (group_id == "admin" or group_id == "teacher") and message.text == "/send" :
                state = "SEND_STATE"
                reply_markup = '{"keyboard" : [["/news", "/homework", "/cancel"]], "resize_keyboard" : true}'
                bot.sendMessage(chat_id=message.chat_id, text="Отослать новость (/news) или домашнее задание (/homework)?", reply_markup=reply_markup)
            elif ((group_id == "admin") or (group_id == 'teacher')) and message.text == USER_LIST_CMD:
                print_userlist(bot, message)
            elif ((group_id == "admin") or (group_id == 'teacher')) and message.text == GOOGLE_SHEET_CMD:
                bot.sendMessage(chat_id=message.chat_id, text='Your google sheet: {}'.format(GOOGLE_SHEET), reply_markup=reply_markup)
            else:
                pass

        elif state.startswith("SEND_STATE"):
            if message.text == "/cancel":
                bot.sendMessage(chat_id=message.chat_id, text="Рассылка отменена", reply_markup=reply_markup)
                state = "MAIN_STATE"
            elif len(state.split()) == 1:
                if message.text == "/news":
                    state += " news"
                    reply_markup = '{"keyboard" : [["/group1", "/group2", "/all", "/cancel"]], "resize_keyboard" : true}'
                    bot.sendMessage(chat_id=message.chat_id, text="Выберите группу для рассылки:", reply_markup=reply_markup)
                elif message.text == "/homework":
                    state += " homework"
                    reply_markup = '{"keyboard" : [["/group1", "/group2", "/all", "/cancel"]], "resize_keyboard" : true}'
                    bot.sendMessage(chat_id=message.chat_id, text="Выберите группу для рассылки:", reply_markup=reply_markup)
                else:
                    reply_markup = '{"keyboard" : [["/news", "/homework", "/cancel"]], "resize_keyboard" : true}'
                    bot.sendMessage(chat_id=message.chat_id, text="Отослать новость (/news) или домашнее задание (/homework)?", reply_markup=reply_markup)
            elif len(state.split()) == 2:
                if message.text == "/group1":
                    state += " group1"
                    reply_markup = '{"keyboard" : [["/cancel"]], "resize_keyboard" : true}'
                    bot.sendMessage(chat_id=message.chat_id, text="Введите сообщение для рассылки (или файл/картинку):", reply_markup=reply_markup)
                elif message.text == "/group2":
                    state += " group2"
                    reply_markup = '{"keyboard" : [["/cancel"]], "resize_keyboard" : true}'
                    bot.sendMessage(chat_id=message.chat_id, text="Введите сообщение для рассылки (или файл/картинку):", reply_markup=reply_markup)
                elif message.text == "/all":
                    state += " all"
                    reply_markup = '{"keyboard" : [["/cancel"]], "resize_keyboard" : true}'
                    bot.sendMessage(chat_id=message.chat_id, text="Введите сообщение для рассылки (или файл/картинку):", reply_markup=reply_markup)
                else:
                    reply_markup = '{"keyboard" : [["/group1", "/group2", "/all", "/cancel"]], "resize_keyboard" : true}'
                    bot.sendMessage(chat_id=message.chat_id, text="Выберите группу для рассылки:", reply_markup=reply_markup)
            elif len(state.split()) == 3:
                state += " " + str(message.message_id)
                reply_markup = '{"keyboard" : [["/confirm", "/cancel"]], "resize_keyboard" : true}'
                bot.sendMessage(chat_id=message.chat_id, text="Подтвердите отправку (/confirm):", reply_markup=reply_markup)
            elif len(state.split()) == 4:
                if message.text == "/confirm":
                    _, _, group, message_id = state.split()
                    forward_broad(bot, from_chat_id=message.chat_id, message_id=message_id, group=group)
                    bot.sendMessage(chat_id=message.chat_id, text="Отправлено!", reply_markup=reply_markup)
                    state = "MAIN_STATE"
                else:
                    reply_markup = '{"keyboard" : [["/confirm", "/cancel"]], "resize_keyboard" : true}'
                    bot.sendMessage(chat_id=message.chat_id, text="Подтвердите отправку (/confirm):", reply_markup=reply_markup)


        with db_session:
            chat = Chat.get(chat_id=message.chat.id)
            chat.group_id, chat.state, chat.silent_mode, chat.deleted = \
                group_id, state, silent_mode, deleted

        LAST_UPDATE_ID = update.update_id + 1



if __name__ == '__main__':
    main()

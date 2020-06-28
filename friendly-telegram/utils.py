#    Friendly Telegram (telegram userbot)
#    Copyright (C) 2018-2019 The Authors

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.

#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Utility functions to help modules do stuff"""

import os
import logging
import asyncio
import functools
import shlex

from telethon.tl.types import PeerUser, PeerChat, PeerChannel
from telethon.extensions import html

from . import __main__


def get_args(message):
    """Get arguments from message (str or Message), return list of arguments"""
    try:
        message = message.message
    except AttributeError:
        pass
    if not message:
        return False
    return list(filter(lambda x: len(x) > 0, shlex.split(message)))[1:]


def get_args_raw(message):
    """Get the parameters to the command as a raw string (not split)"""
    try:
        message = message.message
    except AttributeError:
        pass
    if not message:
        return False
    args = message.split(maxsplit=1)
    if len(args) > 1:
        return args[1]
    return ""


def get_args_split_by(message, sep):
    """Split args with a specific sep"""
    raw = get_args_raw(message)
    mess = raw.split(sep)
    return [section.strip() for section in mess]


def get_chat_id(message):
    """Get the chat ID, but without -100 if its a channel"""
    chat = message.to_id
    if isinstance(chat, PeerUser):
        return message.chat_id
    attrs = vars(chat)
    if len(attrs) != 1:
        return None
    return next(iter(attrs.values()))


def escape_html(text):
    """Pass all untrusted/potentially corrupt input here"""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def escape_quotes(text):
    """Escape quotes to html quotes"""
    return escape_html(text).replace('"', "&quot;")


def get_base_dir():
    """Get directory of this file"""
    return get_dir(__main__.__file__)


def get_dir(mod):
    """Get directory of given module"""
    return os.path.abspath(os.path.dirname(os.path.abspath(mod)))


async def get_user(message):
    """Get user who sent message, searching if not found easily"""
    try:
        return await message.client.get_entity(message.from_id)
    except ValueError:  # Not in database. Lets go looking for them.
        logging.debug("user not in session cache. searching...")
    if isinstance(message.to_id, PeerUser):
        await message.client.get_dialogs()
        return await message.client.get_entity(message.from_id)
    if isinstance(message.to_id, (PeerChannel, PeerChat)):
        async for user in message.client.iter_participants(message.to_id, aggressive=True):
            if user.id == message.from_id:
                return user
        logging.error("WTF! user isn't in the group where they sent the message")
        return None
    logging.error("WTF! to_id is not a user, chat or channel")
    return None


def run_sync(func, *args, **kwargs):
    """Run a non-async function in a new thread and return an awaitable"""
    # Returning a coro
    return asyncio.get_event_loop().run_in_executor(None, functools.partial(func, *args, **kwargs))


def run_async(loop, coro):
    """Run an async function as a non-async function, blocking till it's done"""
    # When we bump minimum support to 3.7, use run()
    return asyncio.run_coroutine_threadsafe(coro, loop).result()


def censor(obj, to_censor=["phone"], replace_with="redacted_{count}_chars"):  # pylint: disable=W0102
    # Safe to disable W0102 because we don't touch to_censor, mutably or immutably.
    """May modify the original object, but don't rely on it"""
    for k, v in vars(obj).items():
        if k in to_censor:
            setattr(obj, k, replace_with.format(count=len(v)))
        elif k[0] != "_" and hasattr(v, "__dict__"):
            setattr(obj, k, censor(v, to_censor, replace_with))
    return obj


def _fix_entities(ent, cont_msg, initial=False):
    for entity in ent:
        entity.offset -= 4096
        if initial:
            entity.offset += len(cont_msg)
        else:
            entity.length += len(cont_msg)
        if entity.offset + entity.length > 0:
            if entity.offset < 0:
                entity.offset = entity.offset + 4096
                entity.length = entity.length - 4096
        elif entity.offset < 0:
            entity.length = 0  # We don't need this one, it doesn't reach.


async def answer(message, response, **kwargs):
    """Use this to give the response to a command"""
    ret = [message]
    if isinstance(response, str) and not kwargs.get("asfile", False):
        txt, ent = html.parse(response)
        await message.edit(html.unparse(txt[:4096], ent))
        txt = txt[4096:]
        cont_msg = "[continued]\n"
        _fix_entities(ent, cont_msg, True)
        while len(txt) > 0:
            txt = cont_msg + txt
            message.message = txt[:4096]
            message.entities = ent
            message.text = html.unparse(message.message, message.entities)
            txt = txt[4096:]
            _fix_entities(ent, cont_msg)
            ret.append(await message.respond(message, parse_mode="HTML", **kwargs))
    else:
        if message.media is not None:
            await message.edit(file=response, **kwargs)
        else:
            await message.edit("<code>Loading media...</code>")
            ret = [await message.client.send_file(message.to_id, response, reply_to=message.reply_to_msg_id, **kwargs)]
            await message.delete()
    return ret

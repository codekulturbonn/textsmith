"""
Tests for the parser that defines how to process user input.

Copyright (C) 2020 Nicholas H.Tollervey
"""
import pytest  # type: ignore
import quart_flask_patch  # type: ignore # noqa
import html
from unittest import mock
from uuid import uuid4
from textsmith.parser import Parser
from textsmith.verbs import UnknownVerb
from textsmith.logic import Logic
from textsmith.datastore import DataStore
from textsmith import constants


EMAIL_HOST = "email.host.com"
EMAIL_PORT = 1234
EMAIL_FROM = "hello@textsmith.com"
EMAIL_PASSWORD = "secret123"


@pytest.fixture
def datastore(mocker):
    return DataStore(mocker.MagicMock())


@pytest.fixture
def logic(datastore):
    return Logic(datastore, EMAIL_HOST, EMAIL_PORT, EMAIL_FROM, EMAIL_PASSWORD)


@pytest.fixture
def parser(logic):
    return Parser(logic)


@pytest.fixture
def user_id():
    return 1234


@pytest.fixture
def room_id():
    return 5678


@pytest.fixture
def connection_id():
    return str(uuid4())


@pytest.fixture
def message_id():
    return str(uuid4())


@pytest.fixture
def message():
    return "Hello, World!"


def test_init(logic):
    """
    Ensure the parser object is initialised with a reference to the logic
    layer.
    """
    parser = Parser(logic)
    assert parser.logic == logic


@pytest.mark.asyncio
async def test_eval(parser, user_id, connection_id, message_id, message):
    """
    Evaluating the user's input causes it to be parsed.
    """
    parser.parse = mock.AsyncMock()
    with mock.patch("textsmith.parser.uuid4", return_value=message_id):
        await parser.eval(user_id, connection_id, message)
    parser.parse.assert_called_once_with(
        user_id, connection_id, message_id, message
    )


@pytest.mark.asyncio
async def test_eval_escape(
    parser, user_id, connection_id, message_id, message
):
    """
    Before any parsing happens the user's input is escaped to to remove any
    injected HTML.
    """
    bad_message = '<a href="#" onclick="alert(\'I am a popup!\');">Link</a>'
    expected = html.escape(bad_message)
    parser.parse = mock.AsyncMock()
    with mock.patch("textsmith.parser.uuid4", return_value=message_id):
        await parser.eval(user_id, connection_id, bad_message)
    parser.parse.assert_called_once_with(
        user_id, connection_id, message_id, expected
    )


@pytest.mark.asyncio
async def test_eval_fail(parser, user_id, connection_id, message_id, message):
    """
    The exception handling method is called to gracefully recover from any
    exceptions encountered whilst parsing the user's input.
    """
    ex = Exception("boom!")
    parser.parse = mock.AsyncMock(side_effect=ex)
    parser.handle_exception = mock.AsyncMock()
    with mock.patch("textsmith.parser.uuid4", return_value=message_id):
        await parser.eval(user_id, connection_id, message)
    assert parser.parse.call_count == 1
    parser.handle_exception.assert_called_once_with(
        user_id, connection_id, message_id, message, ex
    )


@pytest.mark.asyncio
async def test_handle_exception(
    parser, user_id, connection_id, message_id, message
):
    """
    A suitable error message is added to the user's message queue to indicate
    something has gone wrong. The exception is logged.
    """
    parser.logic.emit_to_user = mock.AsyncMock()
    ex = Exception("boom!")
    mock_logger = mock.MagicMock()
    with mock.patch("textsmith.parser.logger.msg", mock_logger):
        await parser.handle_exception(
            user_id, connection_id, message_id, message, ex
        )
    mock_logger.assert_called_once_with(
        "Exception.",
        user_id=user_id,
        connection_id=connection_id,
        message_id=message_id,
        message=message,
        exc_info=ex,
    )
    expected = " ".join(
        [
            "Sorry. Something went wrong when processing your command.",
            f"id: {message_id}",
        ]
    )
    parser.logic.emit_to_user.assert_called_once_with(
        user_id, constants.SYSTEM_OUTPUT.format(expected)
    )


@pytest.mark.asyncio
async def test_parse_only_whitespace(
    parser, user_id, connection_id, message_id
):
    """
    A message containing only whitespace has no side-effect.
    """
    parser.logic.emit_to_user = mock.AsyncMock()
    await parser.parse(user_id, connection_id, message_id, "     ")
    assert parser.logic.emit_to_user.call_count == 0


@pytest.mark.asyncio
async def test_parse_shortcut_say(parser, user_id, connection_id, message_id):
    """
    If the message starts with a double quote, it's a built-in short cut for
    saying something in the current location.
    """
    parser.verbs._say = mock.AsyncMock()
    await parser.parse(user_id, connection_id, message_id, '"Hello')
    parser.verbs._say.assert_called_once_with(
        user_id, connection_id, message_id, "Hello"
    )


@pytest.mark.asyncio
async def test_parse_shortcut_shout(
    parser, user_id, connection_id, message_id
):
    """
    If the message starts with an exclamation mark, it's a built-in short cut
    for shouting something in the current location.
    """
    parser.verbs._shout = mock.AsyncMock()
    await parser.parse(user_id, connection_id, message_id, "!Hello")
    parser.verbs._shout.assert_called_once_with(
        user_id, connection_id, message_id, "Hello"
    )


@pytest.mark.asyncio
async def test_parse_shortcut_emote(
    parser, user_id, connection_id, message_id
):
    """
    If the message starts with a colon, it's a built-in short cut for emoting
    something in the current location.
    """
    parser.verbs._emote = mock.AsyncMock()
    await parser.parse(user_id, connection_id, message_id, ":waves")
    parser.verbs._emote.assert_called_once_with(
        user_id, connection_id, message_id, "waves"
    )


@pytest.mark.asyncio
async def test_parse_shortcut_tell(parser, user_id, connection_id, message_id):
    """
    If the message starts with an "at" sign , it's a built-in short cut for
    saying something to someone specific in the current location.
    """
    parser.verbs._tell = mock.AsyncMock()
    await parser.parse(user_id, connection_id, message_id, "@user hello")
    parser.verbs._tell.assert_called_once_with(
        user_id, connection_id, message_id, "user hello"
    )


@pytest.mark.asyncio
async def test_parse_built_in_verb(parser, user_id, connection_id, message_id):
    """
    If the message starts with a single word built-in verb, this is immediately
    evaluated with the message after the verb used for further verb-specific
    processing.
    """
    parser.verbs = mock.AsyncMock()
    await parser.parse(user_id, connection_id, message_id, "foo bar")
    parser.verbs.assert_called_once_with(
        user_id, connection_id, message_id, "foo", "bar"
    )


@pytest.mark.asyncio
async def test_parse_last_resort(parser, user_id, connection_id, message_id):
    """
    If the parser cannot parse anything meaningful from the user's message,
    ensure a fun response is put onto the user's message queue.
    """
    parser.logic.emit_to_user = mock.AsyncMock()
    parser.verbs = mock.AsyncMock(side_effect=UnknownVerb())
    await parser.parse(user_id, connection_id, message_id, "foo")
    parser.verbs.assert_called_once_with(
        user_id, connection_id, message_id, "foo", ""
    )
    assert parser.logic.emit_to_user.call_count == 1
    assert parser.logic.emit_to_user.await_args_list[0][0][0] == user_id
    msg = parser.logic.emit_to_user.await_args_list[0][0][1]
    assert msg.startswith('"foo", ')
    response = msg.replace('"foo", ', "")
    assert response in constants.HUH

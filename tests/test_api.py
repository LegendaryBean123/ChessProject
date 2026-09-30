from unittest import mock

import pytest
import requests

from chessstats.api import ChessComClient, PlayerNotFound


def response(status, json_data=None, etag=None):
    r = mock.Mock(status_code=status, headers={"etag": etag} if etag else {})
    r.json.return_value = json_data
    if status >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(response=r)
    return r


@pytest.fixture
def client():
    return ChessComClient("tests")


def test_user_agent_is_sent(client):
    assert client.session.headers["User-Agent"] == "tests"


def test_get_archives_lowercases_username(client):
    with mock.patch.object(client.session, "get", return_value=response(200, {"archives": ["a"]})) as get:
        assert client.get_archives("LegendaryBean123") == ["a"]
    assert get.call_args.args[0] == "https://api.chess.com/pub/player/legendarybean123/games/archives"


def test_get_profile(client):
    with mock.patch.object(client.session, "get", return_value=response(200, {"username": "x"})):
        assert client.get_profile("x") == {"username": "x"}


@pytest.mark.parametrize("method", ["get_profile", "get_archives"])
def test_404_raises_player_not_found(client, method):
    with mock.patch.object(client.session, "get", return_value=response(404)):
        with pytest.raises(PlayerNotFound, match="nobody"):
            getattr(client, method)("Nobody")


def test_other_http_errors_pass_through(client):
    with mock.patch.object(client.session, "get", return_value=response(500)):
        with pytest.raises(requests.HTTPError):
            client.get_archives("x")


def test_get_month_sends_etag_and_handles_304(client):
    with mock.patch.object(client.session, "get", return_value=response(304)) as get:
        assert client.get_month("https://example/2024/05", '"abc"') == (None, '"abc"')
    assert get.call_args.kwargs["headers"] == {"if-none-match": '"abc"'}


def test_get_month_returns_data_and_new_etag(client):
    with mock.patch.object(client.session, "get", return_value=response(200, {"games": []}, '"new"')):
        assert client.get_month("https://example/2024/05") == ({"games": []}, '"new"')


def test_429_retries_then_succeeds(client):
    replies = [response(429), response(429), response(200, {"archives": []})]
    with mock.patch.object(client.session, "get", side_effect=replies), mock.patch("time.sleep") as sleep:
        assert client.get_archives("x") == []
    assert [c.args[0] for c in sleep.call_args_list] == [1, 2]


def test_429_gives_up_after_retries(client):
    with mock.patch.object(client.session, "get", return_value=response(429)), mock.patch("time.sleep"):
        with pytest.raises(RuntimeError, match="rate-limited"):
            client.get_profile("x")

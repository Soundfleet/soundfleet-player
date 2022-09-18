import pytest

from unittest import mock

from soundfleet_player import client


@pytest.mark.parametrize(
    ["method"],
    [("get",), ("post",), ("put",), ("patch",), ("options",)],
)
def test_make_request(method):
    class MyResponse:
        def __init__(self, status_code):
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code not in [200, 201, 202, 204]:
                raise Exception()

    with mock.patch(
        "soundfleet_player.client.requests.{}".format(method)
    ) as request:
        request.return_value = MyResponse(200)
        client.make_request("http://127.0.0.1", method)
        assert request.called

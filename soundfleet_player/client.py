import jwt
import logging
import requests

from .conf import settings


logger = logging.getLogger("soundfleet_player")


def _get_auth_headers():
    payload = {"device": settings.DEVICE_ID}
    return {
        "AUTHORIZATION": jwt.encode(
            payload, settings.API_KEY, algorithm="HS512"
        )
    }


def make_request(
    url,
    method,
    params=None,
    data=None,
    json=None,
    headers=None,
    request_timeout=None,
    response_timeout=None,
):
    timeout = request_timeout or 5, response_timeout or 10
    func = getattr(requests, method)
    headers = _get_auth_headers() if headers is None else headers
    try:
        response = func(
            url,
            params=params,
            headers=headers,
            data=data,
            json=json,
            timeout=timeout,
        )
        response.raise_for_status()
        return response
    except requests.HTTPError as e:
        logger.error(e)
    except Exception as e:
        logger.critical(e)

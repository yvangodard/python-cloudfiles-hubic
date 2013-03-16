"""
authentication operations

Authentication instances are used to interact with the remote
authentication service, retreiving storage system routing information
and session tokens.

See COPYING for license information.
"""

from httplib  import HTTPSConnection, HTTPConnection
from utils    import parse_url, THTTPConnection, THTTPSConnection
from errors   import ResponseError, AuthenticationError, AuthenticationFailed
from consts   import user_agent, us_authurl, uk_authurl
from sys      import version_info


class BaseAuthentication(object):
    """
    The base authentication class from which all others inherit.
    """
    def __init__(self, username, api_key, authurl=us_authurl, timeout=15,
                 useragent=user_agent):
        self.authurl = authurl
        self.headers = dict()
        self.headers['x-auth-user'] = username
        self.headers['x-auth-key'] = api_key
        self.headers['User-Agent'] = useragent
        self.timeout = timeout
        (self.host, self.port, self.uri, self.is_ssl) = parse_url(self.authurl)
        if version_info[0] <= 2 and version_info[1] < 6:
            self.conn_class = self.is_ssl and THTTPSConnection or \
                THTTPConnection
        else:
            self.conn_class = self.is_ssl and HTTPSConnection or HTTPConnection

    def authenticate(self):
        """
        Initiates authentication with the remote service and returns a
        two-tuple containing the storage system URL and session token.

        Note: This is a dummy method from the base class. It must be
        overridden by sub-classes.
        """
        return (None, None, None)


class MockAuthentication(BaseAuthentication):
    """
    Mock authentication class for testing
    """
    def authenticate(self):
        return ('http://localhost/v1/account', None, 'xxxxxxxxx')


class Authentication(BaseAuthentication):
    """
    Authentication, routing, and session token management.
    """
    def authenticate(self):
        """
        Initiates authentication with the remote service and returns a
        two-tuple containing the storage system URL and session token.
        """
        conn = self.conn_class(self.host, self.port, timeout=self.timeout)
        #conn = self.conn_class(self.host, self.port)
        conn.request('GET', '/' + self.uri, headers=self.headers)
        response = conn.getresponse()
        response.read()

        # A status code of 401 indicates that the supplied credentials
        # were not accepted by the authentication service.
        if response.status == 401:
            raise AuthenticationFailed()

        # Raise an error for any response that is not 2XX
        if response.status // 100 != 2:
            raise ResponseError(response.status, response.reason)

        storage_url = cdn_url = auth_token = None

        for hdr in response.getheaders():
            if hdr[0].lower() == "x-storage-url":
                storage_url = hdr[1]
            if hdr[0].lower() == "x-cdn-management-url":
                cdn_url = hdr[1]
            if hdr[0].lower() == "x-storage-token":
                auth_token = hdr[1]
            if hdr[0].lower() == "x-auth-token":
                auth_token = hdr[1]

        conn.close()

        if not (auth_token and storage_url):
            raise AuthenticationError("Invalid response from the " \
                    "authentication service.")

        return (storage_url, cdn_url, auth_token)

class HubicAuthentication(BaseAuthentication):
    """
    Authentication for OVH's hubiC cloud storage service
    """
    SESSIONHANDLER='https://ws.ovh.com/sessionHandler/r4/'
    HUBIC='https://ws.ovh.com/hubic/r5/'
    def __init__(self, username, api_key, timeout=15, useragent=None):
        self.username = username
        self.api_key = api_key
        self.timeout = timeout

    def _rpc(self, url, method, params=None):
        import urllib
        import json
        host, port, uri, is_ssl = parse_url(url)
        conn = HTTPSConnection(host, port, timeout=self.timeout)
        uri+='/rest.dispatcher/'+method
        if params:
            uri+= '?' + urllib.urlencode({'params': json.dumps(params)})
        conn.request('GET', '/' + uri)
        response = conn.getresponse()
        data=response.read()
        if response.status != 200:
            raise AuthenticationError("Invalid response from hubiC")
        conn.close()
        return json.loads(data)

    def _sessionHandler(self, method, params=None):
        return self._rpc(self.SESSIONHANDLER, method, params)

    def _hubic(self, method, params=None):
        return self._rpc(self.HUBIC, method, params)

    def authenticate(self):
        r = self._sessionHandler('getAnonymousSession')['answer']

        r = self._hubic('getHubics', {'sessionId': r['session']['id'], 'email': self.username})
        if not r['answer']:
            raise AuthenticationFailed('Unknown username')
        nic = r['answer'][0]['nic']
        hubicId = r['answer'][0]['id']

        r = self._sessionHandler('login', {'login': nic, 'password': self.api_key, 'context': 'hubic'})
        if r['error'] or not r['answer']:
            raise AuthenticationFailed('Invalid username/password')
        r = r['answer']

        r = self._hubic('getHubic', {'sessionId': r['session']['id'], 'hubicId': hubicId})['answer']
        return r['credentials']['username'].decode('base64'), None, r['credentials']['secret']

# vim:set ai ts=4 sw=4 tw=0 expandtab:
